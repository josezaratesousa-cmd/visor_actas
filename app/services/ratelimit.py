"""Per-address throttling, sized for an election night.

    THE CONSTRAINT THAT SHAPES THIS

    Peruvian mobile carriers run carrier-grade NAT: tens of thousands of
    subscribers share one public address. A limit tight enough to stop an
    abuser would, on the night this matters, lock out an entire city's worth
    of citizens who are simply checking their tally sheet. There is no way to
    tell them apart from the address alone, so the limits here are deliberately
    generous and the answer is never a ban.

    The real defence is the cache: an attested record does not change, so a
    sheet that goes viral is fetched from the upstream service once and served
    from memory after that. Throttling is the backstop, not the strategy.

A refused request answers 429 with Retry-After, which is a wait rather than a
door closing. Nothing is remembered beyond the window, so an address that
stops knocking is immediately welcome again.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class Bucket:
    tokens: float
    updated: float


@dataclass
class RateLimiter:
    """Token bucket per client address.

    `rate` is sustained requests per second; `burst` is how many may arrive
    at once. A citizen opening a sheet spends four or five requests in a
    second - page, stylesheet, dictionary, record, image - so the burst has
    to comfortably absorb a normal visit.
    """

    rate: float
    burst: int
    _buckets: dict[str, Bucket] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    _last_sweep: float = field(default_factory=time.monotonic)

    def check(self, key: str) -> float | None:
        """Return None when allowed, or the seconds to wait when not."""
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = Bucket(tokens=self.burst - 1, updated=now)
                return None

            bucket.tokens = min(
                self.burst, bucket.tokens + (now - bucket.updated) * self.rate)
            bucket.updated = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return None
            return round((1 - bucket.tokens) / self.rate, 1)

    def _sweep(self, now: float) -> None:
        """Drop idle buckets so memory does not grow with unique addresses.

        Without this, a night of national traffic leaves one entry per address
        for as long as the process lives.
        """
        if now - self._last_sweep < 60:
            return
        idle = self.burst / self.rate + 60
        self._buckets = {
            key: bucket for key, bucket in self._buckets.items()
            if now - bucket.updated < idle
        }
        self._last_sweep = now


def client_address(scope_client, headers) -> str:
    """The address to throttle on.

    uvicorn already resolves X-Forwarded-For against its trusted proxies, so
    the connection address is the client's. The header is read here only as a
    fallback, and never as the client sends it: a value a caller can choose is
    a limit a caller can escape.
    """
    if scope_client:
        return scope_client[0]
    forwarded = headers.get("x-forwarded-for", "")
    return forwarded.split(",")[-1].strip() or "unknown"
