"""Smoke test: the offline pipeline finds a leak and stays safe on baseline."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sieve.config import Config
from sieve.fakes import FakeClient
from sieve.loop import run_spike


def test_dryrun_finds_leak(tmp_path):
    cfg = Config.from_env(live=False, max_attempts=10, budget_usd=3.0)
    result = run_spike(FakeClient(cfg), cfg, runs_dir=str(tmp_path))
    assert result["baseline_safe"] is True
    assert result["winners"], "expected at least one successful injection"
    assert result["totals"]["calls"] > 0


if __name__ == "__main__":
    test_dryrun_finds_leak(Path("runs_test"))
    print("ok")
