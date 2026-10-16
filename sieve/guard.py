"""Spend and abuse guard for the hosted demo.

The demo spends real Token Factory credit, and Token Factory has no spend cap
(HTTP 402 arrives mid-call). So every live run is gated, in this order:

  1. kill switch      DEMO_LIVE_ENABLED=0 turns live runs off entirely
  2. access tier      a judge code (DEMO_ACCESS_CODE) or the public pool
  3. rate limit       public runs per IP per hour
  4. budget reserve   the run's max cost is reserved against the daily and
                      lifetime caps *before* it starts, then settled to the real
                      metered cost afterwards — so concurrent runs cannot overspend

Counters live in Redis (Upstash REST, set by the Vercel Marketplace integration).
Without a shared store the public pool fails closed: only judge-code runs are
allowed, capped by a per-instance in-memory counter.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Limits:
    run_budget: float      # hard cap per live campaign (USD)
    max_attempts: int      # attack attempts per live campaign
    daily_public: float    # public pool per UTC day (USD)
    daily_total: float     # everything per UTC day, judges included (USD)
    lifetime_total: float  # all-time demo spend cap (USD)
    ip_per_hour: int       # public runs per IP per hour

    @classmethod
    def from_env(cls) -> "Limits":
        return cls(
            run_budget=_env_float("DEMO_RUN_BUDGET_USD", 0.10),
            max_attempts=_env_int("DEMO_MAX_ATTEMPTS", 6),
            daily_public=_env_float("DEMO_DAILY_PUBLIC_USD", 0.50),
            daily_total=_env_float("DEMO_DAILY_BUDGET_USD", 1.50),
            lifetime_total=_env_float("DEMO_TOTAL_BUDGET_USD", 15.00),
            ip_per_hour=_env_int("DEMO_IP_RUNS_PER_HOUR", 3),
        )


class MemoryStore:
    """Per-instance fallback. Not shared across instances — see module doc."""
    shared = False

    def __init__(self) -> None:
        self._d: dict[str, tuple[float, float]] = {}  # key -> (value, expires_at)
        self._lock = threading.Lock()

    def _get(self, key: str) -> float:
        v, exp = self._d.get(key, (0.0, 0.0))
        if exp and exp < time.time():
            self._d.pop(key, None)
            return 0.0
        return v

    def get(self, key: str) -> float:
        with self._lock:
            return self._get(key)

    def incr(self, key: str, amount: float, ttl_s: int) -> float:
        with self._lock:
            v = self._get(key) + amount
            # Redis TTL=0 means persistent. Do not expire the lifetime counter
            # immediately, or extend an existing daily counter on settlement.
            exp = self._d[key][1] if key in self._d else (time.time() + ttl_s if ttl_s else 0.0)
            self._d[key] = (v, exp)
            return v


class UpstashStore:
    """Redis over Upstash's REST API — stdlib only, no extra dependency."""
    shared = True

    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._token = token

    def _cmd(self, *args):
        req = urllib.request.Request(
            self._url, data=json.dumps([str(a) for a in args]).encode(),
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())["result"]

    def get(self, key: str) -> float:
        v = self._cmd("GET", key)
        return float(v) if v is not None else 0.0

    def incr(self, key: str, amount: float, ttl_s: int) -> float:
        if ttl_s:  # create with a TTL only if absent, so the expiry never slides
            self._cmd("SET", key, "0", "EX", ttl_s, "NX")
        return float(self._cmd("INCRBYFLOAT", key, f"{amount:.6f}"))


def make_store():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return UpstashStore(url, token)
    return MemoryStore()


class Denied(Exception):
    def __init__(self, code: str, message: str, status: int = 429) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


DAY_S = 26 * 3600      # a little over a day so a key never expires mid-day
LIFETIME_S = 0         # no expiry


def _day() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


class Guard:
    def __init__(self, store=None, limits: Limits | None = None) -> None:
        self.store = store or make_store()
        self.limits = limits or Limits.from_env()

    @staticmethod
    def live_enabled() -> bool:
        return os.environ.get("DEMO_LIVE_ENABLED", "1") not in ("0", "false", "no")

    @staticmethod
    def is_judge(code: str | None) -> bool:
        expected = os.environ.get("DEMO_ACCESS_CODE", "")
        return bool(expected) and bool(code) and hmac.compare_digest(
            code.strip().encode(), expected.encode())

    def _keys(self) -> dict:
        d = _day()
        return {"day_total": f"sieve:spend:{d}:total",
                "day_public": f"sieve:spend:{d}:public",
                "lifetime": "sieve:spend:lifetime"}

    def status(self) -> dict:
        k, lim = self._keys(), self.limits
        try:
            day_total = self.store.get(k["day_total"])
            day_public = self.store.get(k["day_public"])
            lifetime = self.store.get(k["lifetime"])
            ok = True
        except Exception:  # noqa: BLE001 - a store outage must not crash /health
            day_total = day_public = lifetime = 0.0
            ok = False
        public_open = (self.live_enabled() and ok and self.store.shared
                       and day_public + lim.run_budget <= lim.daily_public
                       and day_total + lim.run_budget <= lim.daily_total
                       and lifetime + lim.run_budget <= lim.lifetime_total)
        judge_open = (self.live_enabled() and ok and bool(os.environ.get("DEMO_ACCESS_CODE"))
                      and day_total + lim.run_budget <= lim.daily_total
                      and lifetime + lim.run_budget <= lim.lifetime_total)
        return {"live_enabled": self.live_enabled(), "public_open": public_open,
                "judge_open": judge_open, "shared_store": self.store.shared,
                "run_budget_usd": lim.run_budget, "max_attempts": lim.max_attempts,
                "spent_today_usd": round(day_total, 4),
                "public_left_today_usd": round(max(0.0, lim.daily_public - day_public), 4)}

    def reserve(self, code: str | None, ip: str) -> dict:
        """Admit a run or raise Denied. Returns a ticket for settle()."""
        lim = self.limits
        if not self.live_enabled():
            raise Denied("live_disabled", "Live runs are switched off right now.", 503)
        judge = self.is_judge(code)
        if code and not judge:
            raise Denied("bad_code", "That judge code is not valid.", 403)
        if not judge and not self.store.shared:
            raise Denied("judge_only", "Live runs need a judge code on this deployment.", 403)

        k = self._keys()
        try:
            if not judge:
                hour = time.strftime("%Y%m%d%H", time.gmtime())
                n = self.store.incr(f"sieve:ip:{ip}:{hour}", 1, 3700)
                if n > lim.ip_per_hour:
                    raise Denied("rate_limited",
                                 f"Limit is {lim.ip_per_hour} live runs per hour. "
                                 "Replays are unlimited.")
            reserved = lim.run_budget
            total = self.store.incr(k["day_total"], reserved, DAY_S)
            life = self.store.incr(k["lifetime"], reserved, LIFETIME_S)
            pub = self.store.incr(k["day_public"], reserved, DAY_S) if not judge else 0.0
        except Denied:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed on store errors
            raise Denied("store_error", "Budget store unavailable, so live runs are "
                         "paused (fail-closed).", 503) from exc

        over = (total > lim.daily_total or life > lim.lifetime_total
                or (not judge and pub > lim.daily_public))
        ticket = {"judge": judge, "reserved": reserved, "keys": k}
        if over:
            self.settle(ticket, 0.0)
            raise Denied("budget", "Today's live-demo budget is used up. "
                         "Recorded runs are still available.")
        return ticket

    def settle(self, ticket: dict, actual_cost: float) -> None:
        """Replace the reservation with the real metered cost."""
        delta = actual_cost - ticket["reserved"]
        k = ticket["keys"]
        try:
            self.store.incr(k["day_total"], delta, DAY_S)
            self.store.incr(k["lifetime"], delta, LIFETIME_S)
            if not ticket["judge"]:
                self.store.incr(k["day_public"], delta, DAY_S)
        except Exception:  # noqa: BLE001 - over-reservation is the safe failure
            pass
