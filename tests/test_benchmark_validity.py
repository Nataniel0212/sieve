"""Missing attacks and interrupted campaigns must not become 0% success data."""
from sieve import attacker, benchmark, benchmark_html, report
from sieve.config import Config
from sieve.fakes import FakeClient


def test_all_refusals_have_no_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(attacker, "propose", lambda *args: "I cannot help with this request.")
    cfg = Config.from_env(live=False, max_attempts=2, budget_usd=1)
    result = benchmark.run_benchmark(FakeClient, cfg, ["bank"], 2, runs_dir=str(tmp_path))
    scenario = result["scenarios"][0]
    assert scenario["valid_trials"] == 0
    assert scenario["all_refusal_trials"] == 2
    assert scenario["exceedance"]["critical"]["n"] == 0
    assert "N/A" in report.render_benchmark(result, "dry-run", str(tmp_path / "report.md"))
    assert "N/A" in benchmark_html.standalone(result)

    from sieve.trials import run_trials
    from sieve.scenarios import REGISTRY
    repeated = run_trials(FakeClient(REGISTRY["bank"]), cfg, REGISTRY["bank"], 2, runs_dir=str(tmp_path))
    assert repeated["aggregate"]["valid_trials"] == 0
    assert "rates N/A" in report.render(repeated, "dry-run", str(tmp_path / "trials.md"))


def test_interrupted_campaign_is_excluded(tmp_path, monkeypatch):
    def interrupted(*args, **kwargs):
        return {"totals": {"cost_usd": 0.02}, "attempt_log": [
            {"attempt": 1, "refused": False, "technique": "system-notice", "status": "safe"}],
            "findings": [], "attempts_run": 1, "baseline_safe": True, "stopped_reason": "budget"}
    monkeypatch.setattr(benchmark.loop, "run_spike", interrupted)
    cfg = Config.from_env(live=False, budget_usd=1)
    result = benchmark.run_benchmark(FakeClient, cfg, ["bank"], 2, runs_dir=str(tmp_path))
    scenario = result["scenarios"][0]
    assert scenario["incomplete_trials"] == 2
    assert scenario["all_refusal_trials"] == 0
    assert scenario["valid_trials"] == 0
    assert scenario["exceedance"]["critical"]["n"] == 0
