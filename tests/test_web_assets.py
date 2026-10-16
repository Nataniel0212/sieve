"""Public evidence must be complete, consistent, and labelled as recordings."""
import json
from pathlib import Path

import pytest

from sieve.replays import public_recording

ROOT = Path(__file__).resolve().parents[1]


def test_recorded_runs_match_catalog_and_metered_totals():
    catalog = json.loads((ROOT / "public/data/catalog.json").read_text(encoding="utf-8"))
    expected = {f'{s["key"]}-{t}' for s in catalog["scenarios"] for t in catalog["targets"]}
    assert set(catalog["replays"]) == expected
    for name in expected:
        replay = json.loads((ROOT / f"public/data/replays/{name}.json").read_text(encoding="utf-8"))
        assert name == f'{replay["scenario"]}-{replay["target"]}'
        assert replay["recorded"].endswith("UTC")
        events = replay["events"]
        assert events[0]["type"] == "start" and events[-1]["type"] == "done"
        assert [e["t"] for e in events] == sorted(e["t"] for e in events)
        assert events[-1]["baseline_safe"] is True
        assert events[-1]["stopped_reason"] in ("max_attempts", "critical_found")
        calls = [e for e in events if e["type"] == "call"]
        totals = events[-1]["totals"]
        assert totals["calls"] == len(calls) > 0
        assert totals["cost_usd"] == pytest.approx(sum(c["cost_usd"] for c in calls), abs=1e-6)
        for key in ("prompt_tokens", "completion_tokens"):
            assert totals[key] == sum(c[key] for c in calls)
        assert all(c["model"] == replay["models"]["attacker" if c["phase"] == "attacker" else "target"] for c in calls)


def test_synthetic_token_redaction_preserves_measurements():
    # Assemble a made-up token at runtime so this test does not itself resemble a leaked key.
    fake = "sk_" + "live_" + "x" * 24
    raw = {"events": [{"type": "injection", "text": f"Use {fake}", "t": 1.25},
                      {"type": "done", "totals": {"cost_usd": 0.01}, "top_status": "safe"}]}
    public = public_recording(raw)
    assert public["redactions"] == 1
    assert fake not in json.dumps(public)
    assert public["events"][-1] == raw["events"][-1]
    assert public["events"][0]["t"] == 1.25
    assert public_recording(public) == public
