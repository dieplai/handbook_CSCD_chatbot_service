"""Observability: structured request logging + in-memory metrics.

Deliberately tiny — no logging framework, no metrics backend. One JSON line per request
(NEVER the question/answer text — police domain, sensitive) and counters you can read at
/v1/metrics to see if failover is firing and what TTFT looks like, without standing up
Prometheus/Grafana for a single VPS.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import deque

_logger = logging.getLogger("handbook_cscd")
if not _logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)


def log_request(**fields) -> None:
    """Emit one JSON log line. Callers pass only non-sensitive fields (model, provider,
    ttft_s, total_s, tokens, status) — never message/answer content."""
    _logger.info(json.dumps(fields, ensure_ascii=False))


class Metrics:
    """Process-local counters. Resets on restart — fine for a liveness signal."""

    def __init__(self, window: int = 200):
        self.total = 0
        self.errors = 0
        self.by_provider: dict[str, int] = {}
        self._ttft = deque(maxlen=window)

    def record(self, *, provider: str | None, ttft_s: float | None, ok: bool) -> None:
        self.total += 1
        if not ok:
            self.errors += 1
        if provider:
            self.by_provider[provider] = self.by_provider.get(provider, 0) + 1
        if ttft_s is not None:
            self._ttft.append(ttft_s)

    def _pct(self, p: float) -> float | None:
        if not self._ttft:
            return None
        vals = sorted(self._ttft)
        idx = min(len(vals) - 1, int(p * len(vals)))
        return round(vals[idx], 3)

    def snapshot(self) -> dict:
        return {
            "total_requests": self.total,
            "errors": self.errors,
            "by_provider": dict(self.by_provider),
            "ttft_p50_s": self._pct(0.50),
            "ttft_p95_s": self._pct(0.95),
        }
