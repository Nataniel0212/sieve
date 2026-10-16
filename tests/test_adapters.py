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


def _adapter(tmp_path, body: str):
    path = tmp_path / "probe_agent.py"
    path.write_text(body)
    return load_adapter(f"{path}:run_agent")


def test_bad_tool_calls_answer_the_model_instead_of_aborting(tmp_path):
    # Fake tool-call injections invite invented tool names; the built-in agent
    # gets "Unknown tool: X" back, and an adapter must behave the same way.
    runner = _adapter(tmp_path, (
        'def run_agent(ctx):\n'
        '    unknown = ctx.execute_tool("verify_identity", {})\n'
        '    malformed = ctx.execute_tool("get_balance", "not a dict")\n'
        '    return unknown + " | " + malformed\n'))
    scn = REGISTRY["bank"]
    events = []
    result = run_spike(FakeClient(scn), Config.from_env(live=False, max_attempts=2, budget_usd=1),
                       scn, runs_dir=str(tmp_path), target_runner=runner, on_event=events.append)
    assert result["stopped_reason"] == "max_attempts"
    outputs = [e["result"] for e in events if e["type"] == "tool"]
    assert "Unknown tool: verify_identity" in outputs
    assert "Error: tool arguments must be a JSON object" in outputs


@pytest.mark.parametrize("body", [
    'def run_agent(ctx):\n    while True:\n        ctx.execute_tool("get_balance", {})\n',
    'def run_agent(ctx):\n    while True:\n        ctx.chat([{"role": "user", "content": ctx.task}])\n',
])
def test_adapter_caps_end_the_agent_run_not_the_campaign(tmp_path, body):
    scn = REGISTRY["bank"]
    result = run_spike(FakeClient(scn), Config.from_env(live=False, max_attempts=2, budget_usd=1),
                       scn, runs_dir=str(tmp_path), target_runner=_adapter(tmp_path, body))
    assert result["baseline_safe"] is True
    assert result["stopped_reason"] == "max_attempts"
    assert result["attempts_run"] == 2


def test_adapter_tool_list_is_a_private_copy(tmp_path):
    scn = REGISTRY["bank"]
    before = [t["function"]["name"] for t in scn.tools]
    runner = _adapter(tmp_path, (
        'def run_agent(ctx):\n'
        '    ctx.tools.append({"type": "function", "function": {"name": "confirm", "parameters": {}}})\n'
        '    ctx.tools[0]["function"]["name"] = "renamed"\n'
        '    return "done"\n'))
    run_spike(FakeClient(scn), Config.from_env(live=False, max_attempts=1, budget_usd=1),
              scn, runs_dir=str(tmp_path), target_runner=runner)
    assert [t["function"]["name"] for t in scn.tools] == before
