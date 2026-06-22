"""build_provider wiring."""
import httpx

from app.main import build_provider
from app.providers.openai_direct import OpenAIDirect
from tests.conftest import make_settings


def _client():
    return httpx.AsyncClient()


def test_build_provider_returns_openai_direct():
    p = build_provider(make_settings(), _client())
    assert isinstance(p, OpenAIDirect)


def test_build_provider_uses_configured_model():
    p = build_provider(make_settings(openai_model="gpt-4o"), _client())
    assert p._model == "gpt-4o"
