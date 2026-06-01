"""9Router provider (primary). httpx async streaming over the OpenAI-compatible API.

9Router has NO prompt caching (fan-out proxy), so TTFT is floored ~3-4s; the win here
is async I/O — hundreds of concurrent SSE streams stay cheap, unlike the demo's blocking
urllib. The handbook lives in the system message once; history is prior turns; the new
question is the final user message (multi-turn behavior identical to the demo).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import Msg, ProviderError, StreamDelta


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url[:-3].rstrip("/") if url.endswith("/v1") else url


def is_retryable(status: int, body: str) -> bool:
    """Whether an upstream HTTP error should trigger failover.

    5xx + classic transient codes (408/409/425/429) -> yes. A plain 403 is a real
    auth/permission failure -> no. BUT 9Router overloads 403 for transient rate-limits
    ("reset after Ns"); that case SHOULD failover rather than surface as a hard error.
    """
    if status >= 500 or status in (408, 409, 425, 429):
        return True
    if status == 403 and "reset after" in body.lower():
        return True
    return False


class NineRouter:
    name = "9router"

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient,
                 model_map: dict[str, str] | None = None,
                 ttft_timeout_s: float = 15.0, read_timeout_s: float = 120.0):
        self._base = _normalize_url(base_url)
        self._key = api_key
        self._client = client
        self._model_map = model_map or {}
        self._ttft_timeout_s = ttft_timeout_s
        self._read_timeout_s = read_timeout_s

    def _resolve_model(self, public_id: str) -> str:
        """Public id ('sonnet-4.5') -> 9Router real id ('kr/claude-sonnet-4.5').
        Unmapped ids pass through (already a real id, or caller knows best)."""
        return self._model_map.get(public_id, public_id)

    def _build_messages(self, system, history, query):
        msgs = [{"role": "system", "content": system}]
        msgs += [{"role": m.role, "content": m.content} for m in history]
        msgs.append({"role": "user", "content": query})
        return msgs

    async def stream(self, system: str, history: list[Msg], query: str, model: str,
                     *, temperature: float, max_tokens: int) -> AsyncIterator[StreamDelta]:
        payload = {
            "model": self._resolve_model(model),
            "messages": self._build_messages(system, history, query),
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream_options": {"include_usage": True},
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"}
        timeout = httpx.Timeout(self._read_timeout_s, connect=10.0, read=self._read_timeout_s)
        url = self._base + "/v1/chat/completions"

        usage: dict = {}
        try:
            async with self._client.stream("POST", url, json=payload, headers=headers,
                                           timeout=timeout) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise ProviderError(f"9router {resp.status_code}: {body}",
                                        retryable=is_retryable(resp.status_code, body),
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
            raise ProviderError(f"9router transport: {exc}", retryable=True) from exc

        yield StreamDelta(done=True, provider=self.name,
                          prompt_tokens=usage.get("prompt_tokens"),
                          completion_tokens=usage.get("completion_tokens"))
