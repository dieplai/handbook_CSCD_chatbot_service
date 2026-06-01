"""Security primitives: constant-time API-key check + in-memory token-bucket rate limiter."""
from app.core import security


def test_verify_api_key_accepts_match():
    assert security.verify_api_key("secret-abc", "secret-abc") is True


def test_verify_api_key_rejects_mismatch():
    assert security.verify_api_key("secret-abc", "wrong") is False


def test_verify_api_key_rejects_empty_provided():
    assert security.verify_api_key("", "secret-abc") is False


def test_verify_api_key_rejects_none():
    assert security.verify_api_key(None, "secret-abc") is False


def test_rate_limiter_allows_under_limit():
    rl = security.RateLimiter(per_min=3)
    assert rl.allow("client-1") is True
    assert rl.allow("client-1") is True
    assert rl.allow("client-1") is True


def test_rate_limiter_blocks_over_limit():
    rl = security.RateLimiter(per_min=2)
    assert rl.allow("client-1") is True
    assert rl.allow("client-1") is True
    assert rl.allow("client-1") is False


def test_rate_limiter_is_per_key():
    rl = security.RateLimiter(per_min=1)
    assert rl.allow("client-1") is True
    assert rl.allow("client-2") is True  # different key, own bucket
    assert rl.allow("client-1") is False


def test_rate_limiter_refills_over_time():
    now = [1000.0]
    rl = security.RateLimiter(per_min=60, clock=lambda: now[0])
    for _ in range(60):  # drain the full burst capacity
        assert rl.allow("c") is True
    assert rl.allow("c") is False
    now[0] += 1.1  # 60/min = 1 token/sec; >1s elapsed refills one
    assert rl.allow("c") is True
