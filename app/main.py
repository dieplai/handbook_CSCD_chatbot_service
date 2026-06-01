"""FastAPI app factory + lifespan.

Startup builds the corpus (173 chunks -> full_ctx + ck_map) and the provider ONCE, plus
a single shared httpx.AsyncClient (connection pooling). Shutdown closes the client so
in-flight streams end cleanly on redeploy. No CORS: this is a server-to-server API (the
website's backend calls it with the secret key) — a browser must never hit it directly.
"""
from __future__ import annotations

import contextlib

import httpx
from fastapi import FastAPI

from app.api import chat, meta
from app.config import Settings
from app.core import corpus as corpus_mod
from app.core.models import MODEL_ROUTES
from app.core.observability import Metrics
from app.core.security import RateLimiter
from app.providers.failover import FailoverProvider
from app.providers.ninerouter import NineRouter
from app.providers.openai_direct import OpenAIDirect


def build_corpus(data_dir) -> dict:
    chunks = corpus_mod.load_chunks(data_dir)
    return {
        "n_chunks": len(chunks),
        "full_ctx": corpus_mod.build_full_context(chunks),
        "ck_map": corpus_mod.build_ck_map(chunks),
    }


def build_provider(settings: Settings, client: httpx.AsyncClient):
    model_map = {pid: r.ninerouter for pid, r in MODEL_ROUTES.items()}
    primary = NineRouter(settings.ninerouter_url, settings.ninerouter_key, client,
                         model_map=model_map,
                         ttft_timeout_s=settings.ttft_timeout_s,
                         read_timeout_s=settings.read_timeout_s)
    if not settings.failover_enabled:
        return primary
    backup = OpenAIDirect(settings.openai_api_key, settings.openai_failover_model, client,
                          read_timeout_s=settings.read_timeout_s)
    return FailoverProvider(primary, backup,
                            breaker_threshold=settings.breaker_threshold,
                            breaker_cooldown_s=settings.breaker_cooldown_s)


def create_app(settings: Settings | None = None, data_dir=None) -> FastAPI:
    from pathlib import Path

    settings = settings or Settings()
    data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        client = httpx.AsyncClient()
        app.state.settings = settings
        app.state.corpus = build_corpus(data_dir)
        app.state.provider = build_provider(settings, client)
        app.state.metrics = Metrics()
        app.state.rate_limiter = RateLimiter(per_min=settings.rate_limit_per_min)
        app.state.http_client = client
        print(f"[startup] {app.state.corpus['n_chunks']} chunks, "
              f"provider={app.state.provider.name}", flush=True)
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(title="Handbook CSCĐ Service", version="1.0.0", lifespan=lifespan)
    app.include_router(meta.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    return app


def get_app() -> FastAPI:
    """ASGI entrypoint for uvicorn (`app.main:get_app` with --factory).

    Built lazily so importing this module (e.g. in tests) doesn't require env vars —
    Settings() is only constructed when the server actually boots.
    """
    return create_app()
