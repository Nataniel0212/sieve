"""Record a real live campaign as a replay for the web demo.

    py -3.12 scripts/record_replay.py --scenario bank --target lightning

Runs one genuine campaign on Nebius Token Factory and saves the exact event
stream the live endpoint would have sent (with real timings and metered cost)
to public/data/replays/<scenario>-<target>.json. The UI labels these as
recorded runs; they are the fallback when live credit is unavailable.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import TARGETS  # noqa: E402
from sieve import scenarios  # noqa: E402
from sieve.config import Config  # noqa: E402
from sieve.loop import run_spike  # noqa: E402
from sieve.nebius import LiveClient  # noqa: E402
from sieve.replays import public_recording  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="inbox", choices=list(scenarios.REGISTRY))
    ap.add_argument("--target", default="lightning", choices=list(TARGETS))
    ap.add_argument("--attempts", type=int, default=6)
    ap.add_argument("--budget", type=float, default=0.10)
    args = ap.parse_args()

    cfg = Config.from_env(live=True)
    cfg.require_live_ready()
    cfg = replace(cfg, model_target=TARGETS[args.target][1],
                  max_attempts=args.attempts, budget_usd=args.budget, model_fallback="")
    scn = scenarios.get(args.scenario)

    events: list[dict] = []
    t0 = time.time()
    res = run_spike(LiveClient(cfg), cfg, scn, runs_dir=str(ROOT / "runs"),
                    on_event=lambda e: events.append({**e, "t": round(time.time() - t0, 3)}))

    out = {"recorded": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "scenario": args.scenario, "target": args.target,
           "models": {"attacker": cfg.model_attacker, "target": cfg.model_target},
           "events": events}
    dest = ROOT / "public" / "data" / "replays" / f"{args.scenario}-{args.target}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    published = json.dumps(public_recording(out), ensure_ascii=False)
    if cfg.api_key in published:
        raise RuntimeError("Refusing to publish a recording containing the configured API key")
    dest.write_text(published, encoding="utf-8")
    print(f"{args.scenario}/{args.target}: {res['stopped_reason']}, "
          f"{res['attempts_run']} attempts, ${res['totals']['cost_usd']:.4f} -> {dest}")


if __name__ == "__main__":
    main()
