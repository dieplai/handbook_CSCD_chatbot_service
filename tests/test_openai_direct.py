"""OpenAIDirect error handling — the real HTTP-error path (not exercised by fake providers)."""
import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.openai_direct import OpenAIDirect


async def _drain(provider):
    async for _ in provider.stream("sys", [], "q", "gpt-4.1-mini",
                                   temperature=0.2, max_tokens=10):
        pass


async def test_http_429_raises_provider_error():
    def handler(request):
        return httpx.Response(429, text="rate limit exceeded")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIDirect("sk-test-key", "gpt-4.1-mini", client)
    with pytest.raises(ProviderError) as exc:
        await _drain(provider)
    assert exc.value.status == 429
    await client.aclose()


async def test_transport_error_raises_provider_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIDirect("sk-test-key", "gpt-4.1-mini", client)
    with pytest.raises(ProviderError):
        await _drain(provider)
    await client.aclose()
