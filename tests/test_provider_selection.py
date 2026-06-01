"""build_provider strategy selection."""
import httpx

from app.main import build_provider
from app.providers.failover import FailoverProvider
from app.providers.ninerouter import NineRouter
from app.providers.openai_direct import OpenAIDirect
from tests.conftest import make_settings


def _client():
    return httpx.AsyncClient()


def test_openai_only_returns_openai_direct():
    s = make_settings(provider="openai", openai_api_key="sk-test")
    assert isinstance(build_provider(s, _client()), OpenAIDirect)


def test_openai_only_uses_configured_model():
    s = make_settings(provider="openai", openai_api_key="sk-test",
                      openai_failover_model="gpt-4o")
    p = build_provider(s, _client())
    assert p._model == "gpt-4o"


def test_ninerouter_with_failover_when_openai_key_present():
    s = make_settings(provider="ninerouter", openai_api_key="sk-test")
    assert isinstance(build_provider(s, _client()), FailoverProvider)


def test_ninerouter_only_when_no_openai_key():
    # no openai key → no failover, bare NineRouter (make_settings defaults key to "")
    s = make_settings(provider="ninerouter")
    assert isinstance(build_provider(s, _client()), NineRouter)
