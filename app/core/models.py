"""Public model id -> per-provider real model id.

The website asks for a public id (e.g. 'sonnet-4.5'); 9Router maps it to its own id, and
failover always uses the configured OpenAI model regardless. Mirrors the demo MODEL_MAP.
"""
from __future__ import annotations

from app.providers.base import ModelRoute

MODEL_ROUTES: dict[str, ModelRoute] = {
    "opus-4.5": ModelRoute(ninerouter="kr/claude-opus-4.5", label="Opus 4.5"),
    "sonnet-4.5": ModelRoute(ninerouter="kr/claude-sonnet-4.5", label="Sonnet 4.5"),
    "haiku-4.5": ModelRoute(ninerouter="kr/claude-haiku-4.5", label="Haiku 4.5"),
}


def resolve_ninerouter_model(public_id: str) -> str | None:
    route = MODEL_ROUTES.get(public_id)
    return route.ninerouter if route else None
