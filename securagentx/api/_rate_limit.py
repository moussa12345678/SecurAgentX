"""In-memory per-key rate limiter (token bucket) for H-004 mitigation.

Single-process only — for multi-worker deployments, swap the dict for
Redis. Sufficient for brute-force login + flow-spam prevention.
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class _TokenBucket:
    __slots__ = ("capacity", "refill_rate", "tokens", "last_refill")

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(
            self.capacity, self.tokens + (now - self.last_refill) * self.refill_rate
        )
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-route, per-key token bucket (H-004).

    Config: ``app.state.rate_limit_routes = {
        ("POST", "/api/v1/auth/login"):  {"capacity": 5,  "refill_rate": 5/60,  "key": "ip"},
        ("POST", "/api/v1/flows"):        {"capacity": 10, "refill_rate": 10/60, "key": "user"},
    }``

    Returns 429 + error envelope when the bucket is empty.
    """

    def __init__(
        self, app: Any, routes: Optional[dict[tuple[str, str], dict[str, Any]]] = None
    ) -> None:
        super().__init__(app)
        self._routes = routes or {}
        self._buckets: dict[tuple[str, str], _TokenBucket] = {}
        self._lock = Lock()

    async def dispatch(
        self, request: Request, call_next: Callable[..., Any]
    ) -> Any:
        cfg = self._routes.get((request.method, request.url.path))
        if cfg is None:
            return await call_next(request)
        key = self._derive_key(request, cfg.get("key", "ip"))
        bucket_key = (request.method + request.url.path, key)
        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = _TokenBucket(cfg["capacity"], cfg["refill_rate"])
                self._buckets[bucket_key] = bucket
            allowed = bucket.take()
        if not allowed:
            retry_after = int(60 / cfg["refill_rate"]) if cfg["refill_rate"] > 0 else 60
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "code": "rate_limited",
                    "msg": "Too many requests. Slow down.",
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    @staticmethod
    def _derive_key(request: Request, scheme: str) -> str:
        if scheme == "user":
            identity = getattr(request.state, "identity", None)
            if identity is not None:
                uid = getattr(identity, "user_id", None)
                if uid is not None:
                    return f"u:{uid}"
        # Fallback: client IP
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return f"ip:{fwd.split(',')[0].strip()}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"
