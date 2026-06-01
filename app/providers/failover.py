"""FailoverProvider: primary -> backup with a circuit breaker.

Implements LLMProvider itself (Composite pattern), so callers see one provider and
never know failover exists. Rules enforced here:
  - Switch to backup ONLY before the first token (a mid-stream failure raises, because
    the client already holds a partial answer — restarting would corrupt it).
  - Switch only on retryable errors; non-retryable (400/401) raise immediately.
  - A circuit breaker skips the primary after `breaker_threshold` consecutive failures,
    for `breaker_cooldown_s`, so users don't eat the primary's timeout every request.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable

from app.providers.base import LLMProvider, Msg, ProviderError, StreamDelta


class FailoverProvider:
    name = "failover"

    def __init__(
        self,
        primary: LLMProvider,
        backup: LLMProvider,
        *,
        breaker_threshold: int = 5,
        breaker_cooldown_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._primary = primary
        self._backup = backup
        self._breaker_threshold = breaker_threshold
        self._breaker_cooldown_s = breaker_cooldown_s
        self._clock = clock
        self._consecutive_failures = 0
        self._open_until = 0.0

    def _breaker_open(self) -> bool:
        return self._clock() < self._open_until

    def _record_primary_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._breaker_threshold:
            self._open_until = self._clock() + self._breaker_cooldown_s

    def _record_primary_success(self) -> None:
        self._consecutive_failures = 0
        self._open_until = 0.0

    async def stream(
        self,
        system: str,
        history: list[Msg],
        query: str,
        model: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamDelta]:
        kwargs = dict(temperature=temperature, max_tokens=max_tokens)

        if not self._breaker_open():
            emitted = False
            try:
                async for delta in self._primary.stream(
                    system, history, query, model, **kwargs
                ):
                    emitted = emitted or bool(delta.token)
                    yield delta
                self._record_primary_success()
                return
            except ProviderError as exc:
                if emitted or not exc.retryable:
                    # tokens already sent, or a non-retryable error -> do NOT failover
                    raise
                self._record_primary_failure()
            # fall through to backup (failed before first token)

        async for delta in self._backup.stream(system, history, query, model, **kwargs):
            yield delta
