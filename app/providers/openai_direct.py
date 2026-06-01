"""OpenAI-direct provider (failover).

Runs only when 9Router is down, so its cost in normal operation is ~0 — which is why
we use a quality model here, not the cheapest one (the design note: optimizing the
failover model for price saves a near-zero bill while risking quality during an outage,
exactly when reliability matters most). OpenAI auto-caches the static prefix (the 74k
handbook) so failover TTFT is actually LOWER than the primary; `prompt_cache_key` pins
routing for better hit rate.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import Msg, ProviderError, StreamDelta

_API = "https://api.openai.com/v1/chat/completions"
_CACHE_KEY = "handbook-cscd-v1"  # stable -> routes repeat calls to the same cache shard


class OpenAIDirect:
    name = "openai"

    def __init__(self, api_key: str, model: str, client: httpx.AsyncClient,
                 read_timeout_s: float = 120.0):
        self._key = api_key
        self._model = model
        self._client = client
        self._read_timeout_s = read_timeout_s

    def _build_messages(self, system, history, query):
        msgs = [{"role": "system", "content": system}]
        msgs += [{"role": m.role, "content": m.content} for m in history]
        msgs.append({"role": "user", "content": query})
        return msgs

    async def stream(self, system: str, history: list[Msg], query: str, model: str,
                     *, temperature: float, max_tokens: int) -> AsyncIterator[StreamDelta]:
        # `model` is the public id; failover always uses the configured OpenAI model.
        payload = {
            "model": self._model,
            "messages": self._build_messages(system, history, query),
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream_options": {"include_usage": True},
            "prompt_cache_key": _CACHE_KEY,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"}
        timeout = httpx.Timeout(self._read_timeout_s, connect=10.0, read=self._read_timeout_s)

        usage: dict = {}
        try:
            async with self._client.stream("POST", _API, json=payload, headers=headers,
                                           timeout=timeout) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise ProviderError(f"openai {resp.status_code}: {body}",
                                        retryable=resp.status_code in (408, 409, 429)
                                        or resp.status_code >= 500,
                                        status=resp.status_code)
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        usage = obj["usage"]
                    choices = obj.get("choices") or [{}]
                    delta = (choices[0].get("delta") or {}) if choices else {}
                    tok = delta.get("content") or ""
                    if tok:
                        yield StreamDelta(token=tok)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderError(f"openai transport: {exc}", retryable=True) from exc

        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        yield StreamDelta(done=True, provider=self.name,
                          prompt_tokens=usage.get("prompt_tokens"),
                          completion_tokens=usage.get("completion_tokens"),
                          cache_read_tokens=cached)
