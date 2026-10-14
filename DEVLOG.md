# DEVLOG

## 2026-10-14 — Spike v1 (scaffold + offline loop)

Built the complete spike for **Sieve**, an automated prompt-injection red-team
for tool-using agents. Goal of v1: prove the core TAP loop end to end.

Done:
- Project scaffold: MIT license, `.gitignore`, `.env.example`, requirements.
- `sieve/` package: Nebius client (Token Factory, OpenAI-compatible) with
  Nemotron quirk handling; per-call metering to JSONL (tokens/latency/cost);
  synthetic email-exfiltration scenario with a deterministic state check;
  tool-calling target agent; TAP attacker; orchestration loop with budget guard;
  report renderer.
- Offline fakes so the full pipeline runs with no key and no spend.

Verified (dry-run):
- Baseline (benign email) stays safe; agent does not leak.
- Adaptive attacker escalates; leak found at attempt 4.
- Report prints the exact winning injection + the agent's tool calls + the
  exfil email. Metering logged 16 calls to `runs/metrics.jsonl`.

Next:
- First **live** run on Nebius with Nemotron (Ultra attacker, Lightning target);
  confirm the quirk workarounds against the real API and fill FRICTION_LOG.
- Slice 2: AgentDojo (MIT) suites behind the same loop for comparable numbers.
