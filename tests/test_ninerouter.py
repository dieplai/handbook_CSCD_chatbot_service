"""NineRouter model-id resolution (public id -> 9Router real id).

The route passes the public model id ('sonnet-4.5'); the provider must translate it to
9Router's real id ('kr/claude-sonnet-4.5') before sending. Sending the public id raw makes
9Router misroute it (observed: 404 'No active credentials for provider: openai').
"""
import httpx

from app.providers.ninerouter import NineRouter

MODEL_MAP = {"sonnet-4.5": "kr/claude-sonnet-4.5", "haiku-4.5": "kr/claude-haiku-4.5"}


def _provider():
    return NineRouter("http://x/v1", "key", httpx.AsyncClient(), model_map=MODEL_MAP)


def test_resolves_public_id_to_real_id():
    assert _provider()._resolve_model("sonnet-4.5") == "kr/claude-sonnet-4.5"


def test_unknown_id_passes_through():
    # already a real id, or unmapped -> send as-is rather than dropping the request
    assert _provider()._resolve_model("kr/claude-opus-4.5") == "kr/claude-opus-4.5"


# --- retryable classification (decides whether failover triggers) ---
from app.providers.ninerouter import is_retryable  # noqa: E402


def test_5xx_is_retryable():
    assert is_retryable(503, "") is True


def test_429_is_retryable():
    assert is_retryable(429, "") is True


def test_400_not_retryable():
    assert is_retryable(400, "bad request") is False


def test_plain_403_not_retryable():
    # a genuine auth/permission 403 must NOT failover (the key is wrong everywhere)
    assert is_retryable(403, "forbidden") is False


def test_9router_403_rate_limit_is_retryable():
    # 9Router overloads 403 for transient rate-limits ("reset after 57s") — that SHOULD
    # failover, not surface as a hard error to the website.
    body = '{"error":{"message":"[kiro/claude-sonnet-4.5] [403]: HTTP 403 (reset after 57s)"}}'
    assert is_retryable(403, body) is True
