"""The web API, end to end on the offline fakes (no key, no spend)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SIEVE_FAKE_LLM", "1")
    monkeypatch.setenv("DEMO_ACCESS_CODE", "judge-123")
    monkeypatch.delenv("KV_REST_API_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    import app
    importlib.reload(app)
    return TestClient(app.app)


def test_health(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["judge_open"] and not h["public_open"]
    assert set(h["targets"]) == {"lightning", "nano", "ultra"}


def test_scenarios(client):
    keys = [s["key"] for s in client.get("/api/scenarios").json()]
    assert keys == ["inbox", "bank", "docs"]


def test_rejects_unknown_inputs(client):
    assert client.post("/api/attack", json={"scenario": "nope"}).status_code == 400
    assert client.post("/api/attack", json={"target": "gpt"}).status_code == 400


def test_public_is_judge_only_without_store(client):
    r = client.post("/api/attack", json={"scenario": "bank"})
    assert r.status_code == 403 and r.json()["error"] == "judge_only"


def test_attack_streams_ndjson(client):
    r = client.post("/api/attack", json={"scenario": "inbox", "target": "lightning",
                                         "code": "judge-123"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in r.text.splitlines()]
    assert events[0]["type"] == "start" and events[-1]["type"] == "done"
    assert events[-1]["top_status"] == "critical"
    assert all("t" in e for e in events)
