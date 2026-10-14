"""Per-call measurement. Every LLM call is logged to JSONL with the real
token counts, latency and computed cost. These numbers feed the report, the
README and the demo video — none of them are hand-written.

Only the *price per token* is a stored constant (a published Token Factory
rate). Cost is always real_tokens * published_rate.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

# USD per 1M tokens (in, out). Token Factory catalog as of 2026-10-13;
# verify in the live catalog before the demo. Override is not needed for the
# spike, but keep this the single source of truth for rates.
PRICES: dict[str, tuple[float, float]] = {
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
}

_warned_models: set[str] = set()


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate = PRICES.get(model)
    if rate is None:
        if model not in _warned_models:
            print(f"[meter] WARNING: no price for '{model}'; cost logged as 0.")
            _warned_models.add(model)
        return 0.0
    cin, cout = rate
    return prompt_tokens / 1e6 * cin + completion_tokens / 1e6 * cout


@dataclass
class Meter:
    path: Path
    rows: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Fresh file per run.
        self.path.write_text("", encoding="utf-8")

    def record(self, phase: str, attempt: int, result) -> dict:
        u = result.usage
        pt = int(u.get("prompt_tokens", 0) or 0)
        ct = int(u.get("completion_tokens", 0) or 0)
        rt = int(u.get("reasoning_tokens", 0) or 0)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "phase": phase,             # "attacker" | "target" | "baseline"
            "attempt": attempt,
            "model": result.model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "reasoning_tokens": rt,
            "latency_s": round(result.latency_s, 3),
            "cost_usd": round(cost_usd(result.model, pt, ct), 6),
        }
        self.rows.append(row)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return row

    def total_cost(self) -> float:
        return sum(r["cost_usd"] for r in self.rows)

    def totals(self) -> dict:
        return {
            "calls": len(self.rows),
            "prompt_tokens": sum(r["prompt_tokens"] for r in self.rows),
            "completion_tokens": sum(r["completion_tokens"] for r in self.rows),
            "reasoning_tokens": sum(r["reasoning_tokens"] for r in self.rows),
            "latency_s": round(sum(r["latency_s"] for r in self.rows), 3),
            "cost_usd": round(self.total_cost(), 6),
        }
