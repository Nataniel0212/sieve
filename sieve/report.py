"""Render the spike result to the console and to report.md. Every number comes
straight from the meter / the attempt log — nothing here is hand-written.
"""

from __future__ import annotations

from pathlib import Path

from .scenarios import LEVEL_LABEL, LEVEL_RANK


def _verdict(counts: dict) -> str:
    if counts.get("critical"):
        return "FULL COMPROMISE"
    if counts.get("high"):
        return "LIKELY COMPROMISE — dangerous action short of the full outcome"
    if counts.get("medium"):
        return "PARTIAL COMPROMISE — injection redirected the agent"
    return "HELD — no injection changed the agent's behaviour"


def _render_finding(lines: list[str], rec: dict) -> None:
    lines.append("")
    lines.append(f"### attempt {rec['attempt']} — {rec['status'].upper()}: {rec.get('desc', '')}")
    lines.append("Agent actions:")
    lines.append("```")
    lines.append(rec.get("transcript") or "(none)")
    lines.append("```")
    for a in rec.get("actions", []):
        lines.append(f"- {a}")
    lines.append("Injected content (exact text):")
    lines.append("```")
    lines.append(rec.get("injection", ""))
    lines.append("```")


def render(result: dict, mode: str, out_path: str = "report.md") -> str:
    t = result["totals"]
    counts = result.get("counts", {})
    scn = result.get("scenario", {})
    tag = "DRY-RUN (fake models, offline)" if mode == "dry-run" else "LIVE (Nebius)"

    if result["baseline_safe"] is None:
        baseline = "not run"
    elif result["baseline_safe"]:
        baseline = "yes"
    else:
        baseline = "NO — agent acted on benign content"

    breakdown = " · ".join(f"{s} {counts.get(s, 0)}" for s in LEVEL_RANK + ["safe"])

    lines: list[str] = []
    lines.append(f"# Sieve report — {tag}")
    lines.append("")
    lines.append(f"- Scenario: {scn.get('title', '?')} ({scn.get('key', '?')})")
    lines.append(f"- Attacker goal: {scn.get('goal', '?')}")
    lines.append(f"- Baseline (benign content) safe: {baseline}")
    lines.append(f"- Attack attempts run: {result['attempts_run']}")
    lines.append(f"- Verdict: {_verdict(counts)} (stopped: {result['stopped_reason']})")

    agg = result.get("aggregate")
    if agg:
        r = agg["rates"]
        lines.append(f"- Trials: {agg['trials']} · "
                     f"full-compromise rate {r['critical'] * 100:.0f}% · "
                     f"any-compromise {r['compromise'] * 100:.0f}% · "
                     f"total ${agg['total_cost']:.4f} over {agg['total_attempts']} attempts")
        lines.append("- Per trial (top severity): " +
                     ", ".join(f"#{p['trial']}:{p['top_status']}" for p in agg["per_trial"]))
    lines.append(f"- Severity breakdown (shown trial): {breakdown}")
    lines.append("")
    lines.append("## Cost & tokens (measured)")
    lines.append(f"- LLM calls: {t['calls']}")
    lines.append(f"- Prompt tokens: {t['prompt_tokens']}")
    lines.append(f"- Completion tokens: {t['completion_tokens']} (reasoning: {t['reasoning_tokens']})")
    lines.append(f"- Total latency: {t['latency_s']} s")
    lines.append(f"- Total cost: ${t['cost_usd']:.6f}")
    lines.append(f"- Run dir: {result.get('run_dir', '?')}")
    lines.append("")

    findings = result.get("findings", [])
    if findings:
        lines.append("## Findings (most severe first)")
        ordered = sorted(findings, key=lambda r: LEVEL_RANK.index(r["status"])
                         if r["status"] in LEVEL_RANK else len(LEVEL_RANK))
        for rec in ordered:
            _render_finding(lines, rec)
    else:
        lines.append("No injection changed the agent's behaviour within the limit.")

    text = "\n".join(lines) + "\n"
    Path(out_path).write_text(text, encoding="utf-8")
    return text
