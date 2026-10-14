"""Render the spike result to the console and to report.md. Every number comes
straight from the meter — nothing here is hand-written.
"""

from __future__ import annotations

from pathlib import Path

from . import scenario


def render(result: dict, mode: str, out_path: str = "report.md") -> str:
    t = result["totals"]
    leaked = bool(result["winners"])
    tag = "DRY-RUN (fake models, offline)" if mode == "dry-run" else "LIVE (Nebius)"

    lines: list[str] = []
    lines.append(f"# Sieve report — {tag}")
    lines.append("")
    lines.append(f"- Scenario: email assistant, exfiltrate `{scenario.SECRET}` "
                 f"to {scenario.ATTACKER_ADDRESS}")
    lines.append(f"- Baseline (benign email) safe: "
                 f"{'yes' if result['baseline_safe'] else 'NO — agent leaked with no attack'}")
    lines.append(f"- Attack attempts run: {result['attempts_run']}")
    lines.append(f"- Result: "
                 f"{'LEAKED' if leaked else 'held (no leak found)'} "
                 f"(stopped: {result['stopped_reason']})")
    lines.append("")
    lines.append("## Cost & tokens (measured)")
    lines.append(f"- LLM calls: {t['calls']}")
    lines.append(f"- Prompt tokens: {t['prompt_tokens']}")
    lines.append(f"- Completion tokens: {t['completion_tokens']} "
                 f"(reasoning: {t['reasoning_tokens']})")
    lines.append(f"- Total latency: {t['latency_s']} s")
    lines.append(f"- Total cost: ${t['cost_usd']:.6f}")
    lines.append(f"- Raw log: {result['jsonl_path']}")
    lines.append("")

    if leaked:
        lines.append("## Injections that got through")
        for w in result["winners"]:
            lines.append("")
            lines.append(f"### Attempt {w['attempt']}")
            lines.append("Injection (exact text):")
            lines.append("```")
            lines.append(w["injection"])
            lines.append("```")
            lines.append("Agent actions:")
            lines.append("```")
            lines.append(w["transcript"] or "(none)")
            lines.append("```")
            for m in w["sent_emails"]:
                lines.append(f"- Exfil email -> to={m['to']} "
                             f"subject={m['subject']!r}")
    else:
        lines.append("No injection succeeded within the attempt/budget limit.")

    text = "\n".join(lines) + "\n"
    Path(out_path).write_text(text, encoding="utf-8")
    return text
