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

### Critical review + hardening (same day)

Reviewed the code and fixed 9 issues (all offline, no spend):
1. API calls now retry transient errors with backoff; HTTP 402 -> graceful stop.
2. Missing `usage` in a live response no longer crashes metering.
3. Budget guard now also checked inside the target loop and between calls.
4. Attacker runs at temperature 1.0 so attempts diversify; target at 0.3.
5. Attacker output is cleaned of code fences / "Here is..." preambles.
6. Softer leak signal: secret fetched + external send flagged as "suspected"
   even when the secret isn't verbatim (catches encoded/paraphrased exfil).
7. Each run writes a timestamped `runs/<ts>/` with metrics.jsonl **and**
   attempts.jsonl (every attempt persisted, not just winners).
8. Tool-call XML sanitizer now covers several leak formats + unclosed tails.
9. Cleanup: dead line in fakes.py removed; attempt numbers 1-indexed throughout.

Re-verified: dry-run still leaks at attempt 4; budget=0 stops gracefully;
smoke test passes.

Next:
- First **live** run on Nebius with Nemotron (Ultra attacker, Lightning target);
  confirm the quirk workarounds against the real API and fill FRICTION_LOG.
- Slice 2: AgentDojo (MIT) suites behind the same loop for comparable numbers.
