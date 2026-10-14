"""Smoke test: every scenario's offline pipeline is safe on baseline and reaches
a critical finding when the triggered attack lands."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sieve import scenarios
from sieve.config import Config
from sieve.fakes import FakeClient
from sieve.loop import run_spike


def _run(scn, tmp_path):
    cfg = Config.from_env(live=False, max_attempts=10, budget_usd=3.0)
    return run_spike(FakeClient(scn), cfg, scn, runs_dir=str(tmp_path))


def test_every_scenario(tmp_path):
    for i, key in enumerate(scenarios.REGISTRY):
        res = _run(scenarios.get(key), tmp_path / f"s{i}")
        assert res["baseline_safe"] is True, f"{key} baseline not safe"
        assert res["winners"], f"{key} produced no critical finding"
        assert res["totals"]["calls"] > 0


if __name__ == "__main__":
    for i, key in enumerate(scenarios.REGISTRY):
        r = _run(scenarios.get(key), Path("runs_test") / key)
        print(key, "->", r["counts"], "winners:", len(r["winners"]))
    print("ok")
