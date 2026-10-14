"""Run the spike several times and report an attack-success RATE.

A single run is noisy: the same attacker/target pair can leak on attempt 1 in
one run and hold for 10 in the next (temperature 1.0). A rate over N independent
trials is the honest, stable metric. The total budget is shared across trials.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from . import loop

RANK = ["leak", "exfil", "secret_access", "unauthorized_send"]


def _sev_idx(status: str) -> int:
    return RANK.index(status) if status in RANK else len(RANK)


def _top_status(result: dict) -> str:
    present = {f["status"] for f in result.get("findings", [])}
    for s in RANK:
        if s in present:
            return s
    return "safe"


def _empty_result(reason: str) -> dict:
    return {"baseline_safe": None, "attempts_run": 0, "findings": [], "winners": [],
            "counts": {}, "stopped_reason": reason, "run_dir": "",
            "totals": {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                       "reasoning_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0}}


def run_trials(client, cfg, trials: int, runs_dir: str = "runs") -> dict:
    spent = 0.0
    per: list[dict] = []
    results: list[tuple[str, dict]] = []

    for i in range(trials):
        remaining = cfg.budget_usd - spent
        if remaining <= 0.002:
            break
        res = loop.run_spike(client, replace(cfg, budget_usd=remaining),
                             runs_dir=runs_dir)
        cost = res["totals"]["cost_usd"]
        spent += cost
        top = _top_status(res)
        per.append({"trial": i + 1, "top_status": top,
                    "attempts": res["attempts_run"], "cost": cost,
                    "run_dir": res["run_dir"]})
        results.append((top, res))

    if results:
        # Showcase the most severe trial (ties: the earliest).
        best = min(results, key=lambda tr: _sev_idx(tr[0]))[1]
    else:
        best = _empty_result("budget")

    counts = Counter(p["top_status"] for p in per)
    n = len(per)
    rates = {
        "leak": (counts.get("leak", 0) / n) if n else 0.0,
        "compromise": (sum(v for k, v in counts.items() if k != "safe") / n) if n else 0.0,
    }
    best["aggregate"] = {
        "trials": n,
        "rates": rates,
        "status_counts": dict(counts),
        "per_trial": per,
        "total_cost": round(spent, 6),
        "total_attempts": sum(p["attempts"] for p in per),
    }
    return best
