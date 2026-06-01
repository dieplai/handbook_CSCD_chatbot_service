"""POST /v1/chat — SSE streaming answer over the full handbook.

Flow: validate -> assemble system(handbook) + history + question -> stream from the
provider (failover transparent) -> forward tokens -> emit a `done` event with metrics +
parsed citations. The SSE contract reserves space for a future `guard` event without
breaking clients (guard is intentionally out of scope this round).
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import AuthDep, get_corpus, get_metrics, get_provider, get_settings
from app.core import corpus as corpus_mod
from app.core import prompt as prompt_mod
from app.core.models import MODEL_ROUTES
from app.core.observability import log_request
from app.providers.base import Msg, ProviderError
from app.schemas import ChatRequest

router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat", dependencies=[AuthDep])
async def chat(req: ChatRequest, request: Request):
    settings = get_settings(request)
    corpus = get_corpus(request)
    provider = get_provider(request)
    metrics = get_metrics(request)

    model = req.model or settings.default_model
    if model not in MODEL_ROUTES:
        model = settings.default_model

    # Enforce limits at the boundary (untrusted client-supplied history).
    if len(req.message) > settings.max_message_chars:
        req.message = req.message[: settings.max_message_chars]
    history = [Msg(m.role, m.content) for m in req.history][-settings.max_history_msgs :]

    system = prompt_mod.build_system(corpus["full_ctx"])

    async def gen():
        t0 = time.perf_counter()
        ttft = None
        parts: list[str] = []
        served_by = None
        prompt_tokens = completion_tokens = cache_read = None
        try:
            async for delta in provider.stream(
                system, history, req.message, model,
                temperature=settings.temperature, max_tokens=settings.max_tokens,
            ):
                if delta.token:
                    if ttft is None:
                        ttft = round(time.perf_counter() - t0, 3)
                    parts.append(delta.token)
                    yield _sse("token", {"text": delta.token})
                if delta.done:
                    served_by = delta.provider
                    prompt_tokens = delta.prompt_tokens
                    completion_tokens = delta.completion_tokens
                    cache_read = delta.cache_read_tokens
        except ProviderError as exc:
            metrics.record(provider=served_by, ttft_s=ttft, ok=False)
            log_request(event="chat", model=model, provider=served_by, status="error",
                        error=str(exc)[:200])
            yield _sse("error", {"message": str(exc)[:200]})
            return

        total = round(time.perf_counter() - t0, 3)
        answer = "".join(parts)
        citations = corpus_mod.parse_citations(answer)
        tps = round(completion_tokens / total, 1) if completion_tokens and total else None
        metrics.record(provider=served_by, ttft_s=ttft, ok=True)
        log_request(event="chat", model=model, provider=served_by, status="ok",
                    ttft_s=ttft, total_s=total, prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens, cache_read_tokens=cache_read,
                    n_citations=len(citations))
        yield _sse("done", {
            "ttft_s": ttft, "total_s": total, "tokens_per_s": tps,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "cache_read_tokens": cache_read, "provider": served_by,
            "answer": answer, "citations": citations,
        })

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
