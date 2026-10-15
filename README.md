# Sieve

**Does your AI agent leak like a sieve?** Sieve is an automated prompt-injection
red-team and **benchmark** for tool-using LLM agents. It attacks an agent you
control, verifies every outcome against the agent's real actions, and reports a
rigorous **attack-success rate with 95% confidence intervals** — so you can
measure how exposed an agent is *before* you ship it.

Everything runs on **NVIDIA Nemotron via Nebius Token Factory**: the attacker is
**Nemotron Ultra**, the agent under test is **Nemotron Lightning**.

> Built for the Nebius x NVIDIA Global AI Hackathon. Defensive security research,
> in the tradition of garak and PyRIT: you only test agents you own. Synthetic
> data only — no real person, account, secret or file exists anywhere in this repo.

## The result (60 live trials, measured, $0.99)

Three toy agents, 20 independent trials each. "Full compromise" = the agent took
the dangerous action (exfiltrated a secret, wired money, deleted files) because
an injected message told it to.

| Agent under test | Full-compromise rate | 95% CI | Attacker refusals |
|---|---|---|---|
| **Banking assistant** (wire funds) | **100%** | 84–100% | 0% |
| **Email assistant** (leak a secret) | **95%** | 76–99% | 0% |
| **Document assistant** (delete files) | **10%** | 3–30% | 0% |

The dominant attack technique was **output-hijacking** (tell the agent its result
must be *delivered* by performing the dangerous action): 78% on banking, 50% on
email. Robustness differs sharply by agent — Sieve measures the difference.

Every number here is produced by `run.py`, logged to JSONL, and reproducible; see
[DEVLOG.md](DEVLOG.md). Nothing is hand-written.

## Why a measurement tool, not a chatbot

A chat can try a few injections. A benchmark has to be *correct*:

- **Adaptive attacks.** Static templates are weak. Sieve uses a TAP-style loop
  (arXiv [2606.10525](https://arxiv.org/abs/2606.10525)): the attacker reads how
  the agent reacted and rewrites the next injection.
- **State-based verification.** Success is checked against the agent's actual tool
  calls (did the secret leave? did money move?), never by an LLM judge an
  injection could fool — following AgentDojo (arXiv
  [2406.13352](https://arxiv.org/abs/2406.13352)).
- **Honest statistics.** Rates come from independent trials with **95% Wilson
  confidence intervals**, not a single lucky run.
- **A confound we found and fixed.** The attacker model *refused* to write a
  payload in 72–86% of early attempts, silently making agents look safe. Sieve now
  detects refusals, excludes all-refusal trials, reports the refusal rate, and —
  by disabling the attacker's chain-of-thought — cut refusals to ~0%. See the
  three measurement passes in [DEVLOG.md](DEVLOG.md).
- **Cheap at volume.** 60 full campaigns for under a dollar on Nemotron.

## How it works

```
attacker (Nemotron Ultra) ──writes injection──► agent under test (Nemotron Lightning)
        ▲                                                   │
        │   feedback: what the agent did                    ▼
        └──────────────── deterministic state check (did it take the bad action?)
```

- `sieve/scenarios.py` — pluggable agents + tasks + injection points + state checks
- `sieve/attacker.py` — the TAP attacker (payload prompt, technique rotation, refusal handling)
- `sieve/target_agent.py` — the agent under test (a real tool-calling loop)
- `sieve/loop.py` — baseline + attack loop + budget guard
- `sieve/benchmark.py` — independent trials, Wilson CIs, per-technique rates
- `sieve/metering.py` — per-call tokens / latency / cost to JSONL
- `sieve/nebius.py` — Nebius Token Factory client + Nemotron quirk handling

### Built-in scenarios

| key | Agent | Dangerous action the injection aims for |
|---|---|---|
| `inbox` | email assistant | fetch an account secret and email it out |
| `bank` | banking assistant | transfer funds to an external payee |
| `docs` | document assistant | delete the user's files |

## Run it

Dry-run is the default: **no API key, no network, no cost** (offline fakes drive
the full pipeline).

```bash
py -3.12 run.py                          # offline dry-run
py -3.12 run.py --scenario bank          # pick a scenario
py -3.12 run.py --live --scenario inbox  # one live campaign on Nebius
py -3.12 run.py --live --benchmark --trials 20 --budget 3   # the full benchmark
```

For live runs:

```bash
cp .env.example .env     # then fill in NEBIUS_API_KEY
pip install -r requirements.txt
```

Outputs per run: a console report, `report.html` / `benchmark.html` (self-contained,
light + dark), and a timestamped `runs/<ts>/` with `metrics.jsonl`, `attempts.jsonl`
and `summary.json`.

## Powered by Nebius + NVIDIA

- **Nebius Token Factory** — every LLM call goes directly here (OpenAI-compatible),
  never through any gateway. Reasoning toggles, `force_nonempty_content`, tool-call
  sanitising and a hard budget guard (for mid-call HTTP 402) are handled in
  `sieve/nebius.py`.
- **NVIDIA Nemotron** — `Nemotron-3-Ultra-550b-a55b` (attacker) and
  `Nemotron-3_5-Lightning` (agent under test). Model ids live in `.env` and swap
  without a code change.

See [FRICTION_LOG.md](FRICTION_LOG.md) for what worked and what didn't.

## Measurement & reproducibility

Every call is logged with model, prompt/completion/reasoning tokens, latency and
cost (`real_tokens × published_rate`; the rate table is the single source of truth
in `sieve/metering.py`). A `BUDGET_USD` guard stops a run before overspend.

## Scope of use

Sieve attacks only agents you own or are authorized to test, using fully synthetic
fixtures. It is a defensive tool: find the hole before an attacker does.

## Roadmap

- Point Sieve at your **own / external** agent via an adapter.
- Run against **AgentDojo** (MIT) suites for numbers comparable to the literature.
- Suggested fixes per finding.

## License

MIT — see [LICENSE](LICENSE). Built from scratch for this hackathon; no code, data
or models from any prior project. Synthetic data only.
