"""Model comparison: run the benchmark with different NVIDIA Nemotron models as
the agent under test, to see whether a stronger target resists prompt injection
better. Attacker stays Nemotron Ultra. Writes runs/compare.json.
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

from sieve import benchmark, scenarios
from sieve.config import Config
from sieve.nebius import LiveClient

MODELS = [
    ("Lightning", "nvidia/Nemotron-3_5-Lightning"),
    ("Nano-30B", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    ("Ultra-550B", "nvidia/Nemotron-3-Ultra-550b-a55b"),
]
TRIALS = 10
TOTAL_BUDGET = 6.0

cfg = Config.from_env(live=True)
cfg.require_live_ready()
make_client = lambda _scn: LiveClient(cfg)  # noqa: E731
scens = list(scenarios.REGISTRY)

out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "trials_per": TRIALS,
       "attacker": cfg.model_attacker, "scenarios": [s for s in scens], "models": []}
spent = 0.0
for name, mid in MODELS:
    remaining = TOTAL_BUDGET - spent
    if remaining <= 0.05:
        print(f"skip {name}: budget exhausted")
        break
    b = benchmark.run_benchmark(make_client, replace(cfg, model_target=mid,
                                budget_usd=remaining), scens, trials_per=TRIALS)
    spent += b["total_cost"]
    row = {"name": name, "id": mid, "cost": b["total_cost"],
           "scenarios": {s["key"]: {
               "critical": s["exceedance"]["critical"],
               "refusal": s.get("attacker_refusal_rate", 0),
               "valid": s.get("valid_trials"), "trials": s["trials"]}
               for s in b["scenarios"]}}
    out["models"].append(row)
    print(name, {k: f"{v['critical']['p']*100:.0f}%" for k, v in row["scenarios"].items()},
          f"(${b['total_cost']:.2f})")

out["total_cost"] = round(spent, 4)
Path("runs").mkdir(exist_ok=True)
Path("runs/compare.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"total spent ${spent:.4f} -> runs/compare.json")
