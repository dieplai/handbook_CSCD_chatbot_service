"""Public model id -> real OpenAI model id."""
from __future__ import annotations

from app.providers.base import ModelRoute

MODEL_ROUTES: dict[str, ModelRoute] = {
    "gpt-4.1-mini": ModelRoute(openai="gpt-4.1-mini", label="GPT-4.1 Mini"),
}
