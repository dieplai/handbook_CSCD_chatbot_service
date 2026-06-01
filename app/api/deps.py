"""FastAPI dependencies: auth, rate limiting, and accessors for shared state.

Provider + corpus live on app.state (built once at startup); these injectors pull them
out so routes stay free of globals and tests can override with fakes.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.security import RateLimiter, verify_api_key


def get_settings(request: Request):
    return request.app.state.settings


def get_corpus(request: Request):
    return request.app.state.corpus


def get_provider(request: Request):
    return request.app.state.provider


def get_metrics(request: Request):
    return request.app.state.metrics


def _rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    """Reject missing/invalid service key (401) and over-limit clients (429).

    Single-tenant: one shared SERVICE_API_KEY. Rate-limit bucket is keyed by the caller
    IP so one misbehaving client can't starve others.
    """
    settings = get_settings(request)
    if not verify_api_key(x_api_key, settings.service_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter(request).allow(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="rate limit exceeded")


AuthDep = Depends(require_api_key)
