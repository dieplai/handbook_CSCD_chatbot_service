"""LLM provider contract.

The provider implements the `stream` coroutine yielding `StreamDelta`s. Routes depend
ONLY on this Protocol, so they never touch a concrete provider — which keeps fakes
trivial to inject in tests.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class Msg:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class StreamDelta:
    """One streamed event from a provider.

    - token: text chunk to forward to the client (None on the final usage-only delta).
    - done: True on the terminal delta, which carries usage + which provider served it.
    """

    token: str | None = None
    done: bool = False
    provider: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cache_read_tokens: int | None = None  # OpenAI cache hits


class ProviderError(Exception):
    """Upstream failure surfaced to the client as an SSE `error` event."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def stream(
        self,
        system: str,
        history: list[Msg],
        query: str,
        model: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamDelta]: ...


@dataclass
class ModelRoute:
    """Maps a public model id to the real OpenAI model id."""

    openai: str = ""
    label: str = ""
