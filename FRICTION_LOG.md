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

_(none yet — first live run pending)_
