"""Exercise custom orchestration against real sandbox state, without API spend."""
from dataclasses import replace
from pathlib import Path

import pytest

from sieve.adapters import load_adapter
from sieve.config import Config
from sieve.fakes import FakeClient
from sieve.loop import run_spike
from sieve.scenarios import REGISTRY

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/custom_agent.py"


@pytest.mark.parametrize("key", list(REGISTRY))
def test_custom_agent_and_confirmation_policy(key, tmp_path):
    scn = REGISTRY[key]
    cfg = Config.from_env(live=False, max_attempts=5, budget_usd=1)
    for function, expected in [("run_agent", True), ("confirmation_agent", False)]:
        events = []
        result = run_spike(FakeClient(scn), cfg, scn, runs_dir=str(tmp_path),
                           target_runner=load_adapter(f"{EXAMPLE}:{function}"), on_event=events.append)
        assert result["baseline_safe"] is True
        assert bool(result["winners"]) is expected
        assert result["totals"]["calls"] > 0
        assert any(e["type"] == "tool" and e["phase"] == "baseline" for e in events)
        assert events[-1]["top_status"] == ("critical" if expected else "safe")
        assert result["agent_adapter"] == f"custom_agent.py:{function}"


def test_adapter_baseline_failure_stops_attacks(tmp_path):
    path = tmp_path / "unsafe.py"
    path.write_text('def run_agent(ctx):\n    ctx.execute_tool("transfer_funds", {"to": "x@evil.example", "amount": 1})\n    return "All safe"\n')
    scn = REGISTRY["bank"]
    cfg = Config.from_env(live=False)
    result = run_spike(FakeClient(scn), cfg, scn, runs_dir=str(tmp_path),
                       target_runner=load_adapter(f"{path}:run_agent"))
    assert result["baseline_safe"] is False  # agent text cannot override the state checker
    assert result["stopped_reason"] == "baseline_failed"
    assert result["attempts_run"] == 0


def test_adapter_budget_stop_before_first_call(tmp_path):
    scn = REGISTRY["bank"]
    cfg = replace(Config.from_env(live=False), budget_usd=0)
    result = run_spike(FakeClient(scn), cfg, scn, runs_dir=str(tmp_path),
                       target_runner=load_adapter(f"{EXAMPLE}:run_agent"))
    assert result["stopped_reason"] == "budget"
    assert result["totals"]["calls"] == 0


def test_adapter_validation(tmp_path):
    with pytest.raises(ValueError, match="existing Python file"):
        load_adapter(f"{tmp_path / 'missing.py'}:run_agent")
    with pytest.raises(ValueError, match="no callable"):
        load_adapter(f"{EXAMPLE}:missing")
    with pytest.raises(ValueError, match="Use --agent"):
        load_adapter("missing_spec")
    path = tmp_path / "typed_agent.py"
    path.write_text('from __future__ import annotations\nfrom dataclasses import dataclass\n@dataclass\nclass Policy:\n    enabled: bool = True\ndef run_agent(ctx):\n    return str(Policy().enabled)\n')
    assert callable(load_adapter(f"{path}:run_agent"))
