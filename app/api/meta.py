"""Meta endpoints: health (liveness), ready (provider reachable), models, chunks, metrics."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import AuthDep, get_corpus, get_metrics, get_provider, get_settings
from app.core.models import MODEL_ROUTES
from app.schemas import HealthResponse, ModelsResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    """Liveness only: corpus loaded. Cheap, no upstream call — safe for nginx polling."""
    corpus = get_corpus(request)
    return HealthResponse(status="ok", n_chunks=corpus["n_chunks"],
                          full_ctx_chars=len(corpus["full_ctx"]))


@router.get("/ready", response_model=ReadyResponse)
def ready(request: Request):
    """Readiness: which provider is wired and whether failover is configured.

    Honest about scope — it does NOT make a live upstream call (that would cost a token
    round-trip on every poll); it reports configuration so a green /health can't hide a
    totally unconfigured provider.
    """
    settings = get_settings(request)
    provider = get_provider(request)
    return ReadyResponse(ready=True, provider=provider.name,
                         failover_enabled=settings.failover_enabled)


@router.get("/models", response_model=ModelsResponse)
def models(request: Request):
    settings = get_settings(request)
    return ModelsResponse(default=settings.default_model, models=list(MODEL_ROUTES))


@router.get("/chunks", dependencies=[AuthDep])
def chunks(request: Request):
    """[Ck] -> {section, section_full, anchors, text} so the website can render citation hovers."""
    return get_corpus(request)["ck_map"]


@router.get("/metrics", dependencies=[AuthDep])
def metrics(request: Request):
    return get_metrics(request).snapshot()
