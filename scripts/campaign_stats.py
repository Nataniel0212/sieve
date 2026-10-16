"""Per-campaign cost and latency, summarised per target model, from the
metrics.jsonl files that every run writes.

    py -3.12 scripts/campaign_stats.py runs/20261015-* > results/campaign-stats-2026-10-15.json

Only token counts, latencies and metered cost are read; no attack text.
"""
from __future__ import annotations

import glob
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path


def main(patterns: list[str]) -> None:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for pat in patterns:
        for d in sorted(glob.glob(pat)):
            p = Path(d) / "metrics.jsonl"
            if not p.exists():
                continue
            rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            target = [r for r in rows if r["phase"] != "attacker"]
            if not target:
                continue
            by_model[target[0]["model"]].append({
                "cost_usd": sum(r["cost_usd"] for r in rows),
                "model_time_s": sum(r["latency_s"] for r in rows),
                "attempts": max(r["attempt"] for r in rows),
                "calls": len(rows),
                "attacker_call_s": st.median([r["latency_s"] for r in rows if r["phase"] == "attacker"] or [0]),
                "target_call_s": st.median([r["latency_s"] for r in target]),
            })
    out = {}
    for model, cs in by_model.items():
        out[model] = {
            "campaigns": len(cs),
            "median_cost_usd": round(st.median(c["cost_usd"] for c in cs), 5),
            "median_model_time_s": round(st.median(c["model_time_s"] for c in cs), 2),
            "median_cost_per_attempt_usd": round(st.median(c["cost_usd"] / max(1, c["attempts"]) for c in cs), 5),
            "median_attacker_call_s": round(st.median(c["attacker_call_s"] for c in cs), 2),
            "median_target_call_s": round(st.median(c["target_call_s"] for c in cs), 2),
            "total_cost_usd": round(sum(c["cost_usd"] for c in cs), 4),
        }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or ["runs/*"])
