"""LLM provider contract.

Every provider (9Router, OpenAI-direct, the failover composite) implements the same
`stream` coroutine yielding `StreamDelta`s. Routes depend ONLY on this Protocol, so they
never know which provider served a request — that's what makes failover transparent and
fakes trivial to inject in tests.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
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
    cache_read_tokens: int | None = None  # OpenAI/Anthropic-direct cache hits; None on 9Router


class ProviderError(Exception):
    """Upstream failure. `retryable` decides whether failover should try the next provider.

    429/5xx/timeout/connection -> retryable (transient). 400/401/403 -> not retryable
    (the request or auth is wrong; trying another provider won't help).
    """

    def __init__(self, message: str, *, retryable: bool, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
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
    """Maps a public model id (e.g. 'sonnet-4.5') to each provider's real model id."""

    ninerouter: str
    openai: str = ""
    label: str = field(default="")
