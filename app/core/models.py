"""Public model id -> per-provider real model id.

Current production provider is PROVIDER=openai (OpenAI-direct). The openai field is the
real model id sent to OpenAI; ninerouter is kept for if/when the service switches back.
"""
from __future__ import annotations

from app.providers.base import ModelRoute

MODEL_ROUTES: dict[str, ModelRoute] = {
    "gpt-4.1-mini": ModelRoute(ninerouter="", openai="gpt-4.1-mini", label="GPT-4.1 Mini"),
    # Uncomment to re-enable Claude via 9Router (requires PROVIDER=ninerouter):
    # "sonnet-4.5": ModelRoute(ninerouter="kr/claude-sonnet-4.5", openai="", label="Sonnet 4.5"),
    # "haiku-4.5":  ModelRoute(ninerouter="kr/claude-haiku-4.5",  openai="", label="Haiku 4.5"),
    # "opus-4.5":   ModelRoute(ninerouter="kr/claude-opus-4.5",   openai="", label="Opus 4.5"),
}


def resolve_ninerouter_model(public_id: str) -> str | None:
    route = MODEL_ROUTES.get(public_id)
    return route.ninerouter if route else None
