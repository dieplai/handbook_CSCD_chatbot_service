"""API request/response schemas with strict validation at the boundary.

The service is stateless: the website sends `history` on every request, so `history` is
untrusted input. We cap its length and each message size (prevent prompt-bloat DoS) and
restrict roles to user/assistant (forged 'system' turns can't be injected).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HistoryMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[HistoryMsg] = Field(default_factory=list)
    model: str | None = None  # validated against MODEL_ROUTES in the route

    @field_validator("message")
    @classmethod
    def _strip_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


class HealthResponse(BaseModel):
    status: str
    n_chunks: int
    full_ctx_chars: int


class ReadyResponse(BaseModel):
    ready: bool
    provider: str
    failover_enabled: bool
    detail: str = ""


class ModelsResponse(BaseModel):
    default: str
    models: list[str]
