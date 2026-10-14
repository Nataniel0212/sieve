"""Render the spike result to the console and to report.md. Every number comes
straight from the meter — nothing here is hand-written.
"""

from __future__ import annotations

from pathlib import Path

from . import scenario


def _render_finding(lines: list[str], rec: dict, label: str) -> None:
    lines.append("")
    lines.append(f"### {label} — attempt {rec['attempt']} ({rec['status']})")
    lines.append("Injection (exact text):")
    lines.append("```")
    lines.append(rec["injection"])
    lines.append("```")
    lines.append("Agent actions:")
    lines.append("```")
    lines.append(rec["transcript"] or "(none)")
    lines.append("```")
    for m in rec.get("sent_emails", []):
        lines.append(f"- Outbound email -> to={m['to']} subject={m['subject']!r}")


def render(result: dict, mode: str, out_path: str = "report.md") -> str:
    t = result["totals"]
    leaked = bool(result["winners"])
    suspected = result.get("suspected", [])
    tag = "DRY-RUN (fake models, offline)" if mode == "dry-run" else "LIVE (Nebius)"

    if result["baseline_safe"] is None:
        baseline = "not run"
    elif result["baseline_safe"]:
        baseline = "yes"
    else:
        baseline = "NO — agent leaked with no attack"

    if leaked:
        verdict = "LEAKED"
    elif suspected:
        verdict = "SUSPECTED leak (secret fetched + external send, not verbatim)"
    else:
        verdict = "held (no leak found)"

    lines: list[str] = []
    lines.append(f"# Sieve report — {tag}")
    lines.append("")
    lines.append(f"- Scenario: email assistant, exfiltrate `{scenario.SECRET}` "
                 f"to {scenario.ATTACKER_ADDRESS}")
    lines.append(f"- Baseline (benign email) safe: {baseline}")
    lines.append(f"- Attack attempts run: {result['attempts_run']}")
    lines.append(f"- Result: {verdict} (stopped: {result['stopped_reason']})")
    lines.append("")
    lines.append("## Cost & tokens (measured)")
    lines.append(f"- LLM calls: {t['calls']}")
    lines.append(f"- Prompt tokens: {t['prompt_tokens']}")
    lines.append(f"- Completion tokens: {t['completion_tokens']} "
                 f"(reasoning: {t['reasoning_tokens']})")
    lines.append(f"- Total latency: {t['latency_s']} s")
    lines.append(f"- Total cost: ${t['cost_usd']:.6f}")
    lines.append(f"- Run dir: {result.get('run_dir', '?')} "
                 f"(metrics.jsonl, attempts.jsonl)")
    lines.append("")

    if leaked or suspected:
        lines.append("## Findings")
        for w in result["winners"]:
            _render_finding(lines, w, "LEAK")
        for s in suspected:
            _render_finding(lines, s, "SUSPECTED")
    else:
        lines.append("No injection succeeded within the attempt/budget limit.")

    text = "\n".join(lines) + "\n"
    Path(out_path).write_text(text, encoding="utf-8")
    return text
