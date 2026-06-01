"""Shared fixtures: a test app wired with a scriptable fake provider (no network)."""
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.observability import Metrics
from app.core.security import RateLimiter
from app.main import build_corpus, create_app
from app.providers.base import StreamDelta

TEST_KEY = "test-service-key-123"


class ScriptedProvider:
    name = "fake"

    def __init__(self, tokens=("Xin ", "chào"), completion_tokens=2):
        self._tokens = tokens
        self._completion_tokens = completion_tokens

    async def stream(self, system, history, query, model, *, temperature, max_tokens
                     ) -> AsyncIterator[StreamDelta]:
        for t in self._tokens:
            yield StreamDelta(token=t)
        yield StreamDelta(done=True, provider=self.name,
                          prompt_tokens=100, completion_tokens=self._completion_tokens)


def make_settings(**over) -> Settings:
    base = dict(
        service_api_key=TEST_KEY,
        ninerouter_url="http://example.invalid/v1",
        ninerouter_key="x",
        openai_api_key="",  # default: no failover unless a test opts in
    )
    base.update(over)
    # _env_file=None → ignore a real .env so tests are deterministic everywhere.
    return Settings(_env_file=None, **base)


@pytest.fixture
def app_factory():
    """Returns a builder so a test can inject its own provider/settings."""
    def _build(provider=None, settings=None):
        settings = settings or make_settings()
        app = create_app(settings=settings)

        # Replace lifespan wiring with deterministic test state.
        app.state.settings = settings
        app.state.corpus = build_corpus(_data_dir())
        app.state.provider = provider or ScriptedProvider()
        app.state.metrics = Metrics()
        app.state.rate_limiter = RateLimiter(per_min=settings.rate_limit_per_min)
        app.state.http_client = httpx.AsyncClient()
        return app
    return _build


def _data_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def client(app_factory):
    app = app_factory()
    # Bypass lifespan (we set state manually) so the fake provider stays wired.
    return TestClient(app)


def auth_headers():
    return {"X-API-Key": TEST_KEY}
