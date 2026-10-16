# FRICTION LOG

Everything that rubbed wrong with Nebius Token Factory / NVIDIA Nemotron, with
time, step and error. This is the required hackathon feedback — keep it specific.

## Anticipated quirks coded against (to confirm on the first live run)

These are documented Token Factory/Nemotron behaviours we already wrote defenses
for. Each needs to be verified against the real API and turned into a concrete
entry (with the actual response) once we run `--live`:

- **Tool-call XML leaking into `content`** — `sieve/nebius.py` strips
  `<tool_call>…</tool_call>` from message content. Verify it actually appears and
  that the regex matches the real format.
- **Reasoning toggle** — we send
  `extra_body.chat_template_kwargs.enable_thinking`. Confirm Token Factory passes
  it through and that `completion_tokens_details.reasoning_tokens` comes back.
- **`force_nonempty_content`** — set for agent calls. Confirm it's honored.
- **`max_tokens` ≥ 8192 for Lightning** on multi-step tool calls — set in the
  target agent. Watch for truncated tool-call turns if it's too low.
- **Tool arguments as a JSON string** — we parse them back to a dict before the
  checker sees them. Confirm the model returns a string (not already an object).
- **No spend cap / HTTP 402 mid-call** — budget guard in `sieve/loop.py` stops
  before `BUDGET_USD`. Confirm 402 behaviour and that the guard triggers first.

## Live-run entries

### 2026-10-14 — first live runs (Ultra attacker, Lightning target)

Confirmed against the real API:
- **Reasoning passthrough works.** `extra_body.chat_template_kwargs.enable_thinking`
  is honored — responses came back with `completion_tokens_details.reasoning_tokens`
  populated (186–2478 depending on run). The Ultra attacker used reasoning.
- **Usage is returned normally** (prompt/completion tokens present); the None-guard
  never had to fire.
- **`force_nonempty_content` accepted** on tool-calling agent calls; no error.
- **`max_tokens=8192` on Lightning** multi-step tool calls: fine.
- **Both model ids valid:** `nvidia/Nemotron-3-Ultra-550b-a55b` (us-central1) and
  `nvidia/Nemotron-3_5-Lightning` (eu-north1).
- **No HTTP 402**; balance was ample. Budget guard never needed to trip.
- **No visible tool-call XML leakage** in `content` this run; sanitizer kept on
  as a precaution.

Minor friction:
- Nothing blocking. Onboarding (key -> first successful call) was quick once the
  key was in `.env`. Watch: confirm whether `reasoning_tokens` is already counted
  inside `completion_tokens` for billing (affects whether cost double-counts).

### 2026-10-16: secret scanning does not know Token Factory keys

- **Step:** ran gitleaks 8.30.1 (default rules) over the repo before pushing the
  web demo.
- **Observed:** it flagged our *fake* fixture token, but **not** the real Nebius
  Token Factory key sitting in `.env` (a ~230-character dotted token).
- **Impact:** anyone relying on default secret scanning (gitleaks, likely also
  GitHub push protection) could push a Token Factory key without a warning. With
  no spend cap on the account, a leaked key is directly billable.
- **Workaround:** custom rule in `.gitleaks.toml`, plus a direct search of the
  history for the key value.
- **Ask:** publish a recognisable key prefix/format and register it with GitHub
  secret scanning and gitleaks; offer per-key spend limits.

### 2026-10-16: no spend cap shapes the whole demo design

- No account- or key-level spend limit, and HTTP 402 arrives mid-call. A public
  demo that must stay up until 15 Dec therefore needs its own reservation-based
  budget ledger (Redis), per-run caps and a kill switch: about 200 lines of
  code and tests that a per-key limit would make unnecessary.
