"""The demo spend guard must fail closed: no shared store means judge-only,
caps are reserved before a run and settled to the real cost after."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sieve.guard import Denied, Guard, Limits, MemoryStore  # noqa: E402


class SharedMemory(MemoryStore):
    shared = True  # stands in for Redis in tests


class BrokenStore:
    shared = True

    def get(self, key):
        raise ConnectionError("down")

    def incr(self, key, amount, ttl_s):
        raise ConnectionError("down")


def limits(**kw):
    base = dict(run_budget=0.10, max_attempts=6, daily_public=0.25, daily_total=0.50,
                lifetime_total=5.0, ip_per_hour=3)
    base.update(kw)
    return Limits(**base)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", "judge-123")
    monkeypatch.delenv("DEMO_LIVE_ENABLED", raising=False)


def test_without_shared_store_public_is_closed():
    g = Guard(MemoryStore(), limits())
    with pytest.raises(Denied) as e:
        g.reserve(None, "1.2.3.4")
    assert e.value.code == "judge_only"
    assert g.reserve("judge-123", "1.2.3.4")["judge"] is True


def test_wrong_code_is_rejected():
    g = Guard(SharedMemory(), limits())
    with pytest.raises(Denied) as e:
        g.reserve("nope", "1.2.3.4")
    assert e.value.code == "bad_code" and e.value.status == 403


def test_public_pool_and_settle():
    g = Guard(SharedMemory(), limits())
    t1 = g.reserve(None, "a")
    t2 = g.reserve(None, "b")
    with pytest.raises(Denied) as e:      # 0.10 + 0.10 + 0.10 > 0.25 public pool
        g.reserve(None, "c")
    assert e.value.code == "budget"
    g.settle(t1, 0.02)
    g.settle(t2, 0.02)                    # real cost frees the reservation
    g.reserve(None, "c")
    assert g.status()["spent_today_usd"] == pytest.approx(0.14)


def test_daily_total_caps_judges_too():
    g = Guard(SharedMemory(), limits(daily_total=0.25))
    g.reserve("judge-123", "x")
    g.reserve("judge-123", "x")
    with pytest.raises(Denied):
        g.reserve("judge-123", "x")


def test_ip_rate_limit():
    g = Guard(SharedMemory(), limits(daily_public=10, daily_total=10, ip_per_hour=2))
    g.reserve(None, "ip")
    g.reserve(None, "ip")
    with pytest.raises(Denied) as e:
        g.reserve(None, "ip")
    assert e.value.code == "rate_limited"
    g.reserve("judge-123", "ip")          # judges are not rate limited


def test_store_outage_fails_closed():
    g = Guard(BrokenStore(), limits())
    with pytest.raises(Denied) as e:
        g.reserve("judge-123", "x")
    assert e.value.code == "store_error"
    assert g.status()["judge_open"] is False


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("DEMO_LIVE_ENABLED", "0")
    g = Guard(SharedMemory(), limits())
    with pytest.raises(Denied) as e:
        g.reserve("judge-123", "x")
    assert e.value.code == "live_disabled"


def test_lifetime_counter_has_no_expiry(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("sieve.guard.time.time", lambda: clock[0])
    store = MemoryStore()
    store.incr("lifetime", 0.1, 0)
    clock[0] += 3600
    assert store.get("lifetime") == pytest.approx(0.1)
    store.incr("lifetime", 0.1, 0)
    clock[0] += 86400
    assert store.get("lifetime") == pytest.approx(0.2)


def test_lifetime_cap_survives_new_day(monkeypatch):
    g = Guard(SharedMemory(), limits(daily_total=1, lifetime_total=0.15))
    g.reserve("judge-123", "x")
    monkeypatch.setattr("sieve.guard._day", lambda: "20990101")
    with pytest.raises(Denied) as err:
        g.reserve("judge-123", "x")
    assert err.value.code == "budget"
