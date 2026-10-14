"""Sieve CLI.

    py -3.12 run.py              # offline dry-run (no key, no cost)
    py -3.12 run.py --live       # real run against Nebius Token Factory
    py -3.12 run.py --attempts 15 --budget 2.0

Dry-run is the default on purpose: it never spends money and never needs a key.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sieve import html_report
from sieve.config import Config
from sieve.loop import run_spike
from sieve.report import render


def main() -> None:
    ap = argparse.ArgumentParser(description="Sieve — prompt-injection red-team spike")
    ap.add_argument("--live", action="store_true",
                    help="use Nebius Token Factory (needs NEBIUS_API_KEY)")
    ap.add_argument("--attempts", type=int, default=None, help="max attack attempts")
    ap.add_argument("--budget", type=float, default=None, help="USD budget cap")
    args = ap.parse_args()

    cfg = Config.from_env(live=args.live, max_attempts=args.attempts,
                          budget_usd=args.budget)

    if args.live:
        cfg.require_live_ready()
        from sieve.nebius import LiveClient
        client = LiveClient(cfg)
        mode = "live"
    else:
        from sieve.fakes import FakeClient
        client = FakeClient(cfg)
        mode = "dry-run"

    result = run_spike(client, cfg)
    result["mode"] = mode
    result["models"] = {"attacker": cfg.model_attacker, "target": cfg.model_target}

    text = render(result, mode)            # writes ./report.md
    html_doc = html_report.standalone(result)
    Path("report.html").write_text(html_doc, encoding="utf-8")

    run_dir = result.get("run_dir")
    if run_dir:
        rd = Path(run_dir)
        (rd / "report.md").write_text(text, encoding="utf-8")
        (rd / "report.html").write_text(html_doc, encoding="utf-8")
        (rd / "summary.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(text)
    print(f"\nHTML report: report.html  (and {run_dir}\\report.html)")


if __name__ == "__main__":
    main()
