"""FailoverProvider behavior.

The hard rules from the design:
  1. Only switch providers when NO token has been emitted yet. If 9Router fails
     mid-stream (after tokens), we must NOT silently restart on OpenAI — the client
     already received half an answer. Raise instead.
  2. Only retryable errors (429/5xx/timeout) trigger failover. 400/401 fail fast.
  3. Circuit breaker: after N consecutive primary failures, skip the primary and go
     straight to failover for a cool-off window.
"""
from collections.abc import AsyncIterator

import pytest

from app.providers.base import LLMProvider, Msg, ProviderError, StreamDelta
from app.providers.failover import FailoverProvider


class FakeProvider:
    """Scriptable provider. `script` is a list of either str (token) or Exception."""

    def __init__(self, name: str, script: list, usage: dict | None = None):
        self.name = name
        self._script = script
        self._usage = usage or {}
        self.calls = 0

    async def stream(self, system, history, query, model, *, temperature, max_tokens
                     ) -> AsyncIterator[StreamDelta]:
        self.calls += 1
        for item in self._script:
            if isinstance(item, Exception):
                raise item
            yield StreamDelta(token=item)
        yield StreamDelta(done=True, provider=self.name,
                          completion_tokens=self._usage.get("completion_tokens"))


async def _collect(provider: LLMProvider) -> list[StreamDelta]:
    out = []
    async for d in provider.stream("sys", [Msg("user", "hi")], "q", "sonnet-4.5",
                                   temperature=0.2, max_tokens=100):
        out.append(d)
    return out


async def test_primary_success_no_failover():
    primary = FakeProvider("9router", ["Xin ", "chào"], {"completion_tokens": 2})
    backup = FakeProvider("openai", ["should not run"])
    fo = FailoverProvider(primary, backup)

    deltas = await _collect(fo)

    assert "".join(d.token for d in deltas if d.token) == "Xin chào"
    assert deltas[-1].done and deltas[-1].provider == "9router"
    assert backup.calls == 0


async def test_failover_when_primary_fails_before_first_token():
    primary = FakeProvider("9router", [ProviderError("503", retryable=True, status=503)])
    backup = FakeProvider("openai", ["Câu ", "trả lời"], {"completion_tokens": 2})
    fo = FailoverProvider(primary, backup)

    deltas = await _collect(fo)

    assert "".join(d.token for d in deltas if d.token) == "Câu trả lời"
    assert deltas[-1].provider == "openai"
    assert backup.calls == 1


async def test_no_failover_after_tokens_emitted():
    # primary emits a token THEN dies — must raise, not restart on backup
    primary = FakeProvider("9router", ["Xin ", ProviderError("hang", retryable=True)])
    backup = FakeProvider("openai", ["different answer"])
    fo = FailoverProvider(primary, backup)

    with pytest.raises(ProviderError):
        await _collect(fo)
    assert backup.calls == 0


async def test_non_retryable_error_does_not_failover():
    primary = FakeProvider("9router", [ProviderError("bad request", retryable=False, status=400)])
    backup = FakeProvider("openai", ["x"])
    fo = FailoverProvider(primary, backup)

    with pytest.raises(ProviderError):
        await _collect(fo)
    assert backup.calls == 0


async def test_circuit_opens_after_consecutive_failures():
    # 2 consecutive primary failures open the breaker; the 3rd call skips primary entirely
    primary = FakeProvider("9router", [ProviderError("503", retryable=True, status=503)])
    backup = FakeProvider("openai", ["ok"], {"completion_tokens": 1})
    fo = FailoverProvider(primary, backup, breaker_threshold=2)

    await _collect(fo)  # primary fail #1 -> backup
    await _collect(fo)  # primary fail #2 -> backup, breaker now OPEN
    primary.calls = 0
    await _collect(fo)  # breaker open -> should NOT touch primary

    assert primary.calls == 0


async def test_circuit_resets_on_primary_success():
    # a primary success must clear the consecutive-failure count
    primary = FakeProvider("9router", ["good"], {"completion_tokens": 1})
    backup = FakeProvider("openai", ["x"])
    fo = FailoverProvider(primary, backup, breaker_threshold=2)

    await _collect(fo)
    assert fo._consecutive_failures == 0
