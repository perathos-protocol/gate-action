"""The step script against a faked `require_approval`: inputs in, outputs and exit codes out."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RECEIPT = {"approver": {"name": "Alice | Moyo"}, "decided_at": "2026-11-10T08:31:10Z", "receipt_hash": "ab" * 32,
           "decision": "approve"}


@pytest.fixture
def step(tmp_path, monkeypatch):
    for name, value in {
        "IN_HOME": str(tmp_path / "home"), "IN_SUMMARY": "Deploy api to production", "IN_TARGET": "production",
        "IN_RECEIPT": str(tmp_path / "out" / "receipt.json"), "IN_WAIT": "5", "IN_TTL": "99999",
        "GITHUB_REPOSITORY": "acme/api", "GITHUB_SHA": "0123456789abcdef0123", "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW": "deploy", "GITHUB_JOB": "deploy", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_ACTOR": "octocat", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_OUTPUT": str(tmp_path / "output"), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "PERATHOS_GATE_APPROVERS": "key-one",
    }.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("gate_step", None)
    module = importlib.import_module("gate_step")
    module.tmp = tmp_path
    return module


def test_approved_writes_receipt_outputs_and_summary(step, monkeypatch, capsys):
    seen = {}

    def fake(summary, **kw):
        seen.update(kw, summary=summary)
        kw["on_created"]({"id": "apr_x", "approve_url": "https://gate.example/a/apr_x?t=SECRET"})
        return RECEIPT
    monkeypatch.setattr(step, "require_approval", fake)
    assert step.main() == 0
    # Bound to this exact run, and the server limits are respected.
    assert seen["args"]["run"]["sha"] == "0123456789abcdef0123" and seen["args"]["run"]["run_attempt"] == "2"
    assert seen["session_id"] == "acme/api/42/2" and seen["ttl_seconds"] == 3600 and seen["wait_seconds"] == 5
    assert "acme/api at 0123456789ab" in seen["detail"] and seen["target"] == "production"
    out = capsys.readouterr().out
    assert "SECRET" not in out and "link not shown" in out and "::warning::" not in out
    assert json.loads((step.tmp / "out" / "receipt.json").read_text(encoding="utf-8")) == RECEIPT
    outputs = (step.tmp / "output").read_text(encoding="utf-8")
    assert f"receipt_hash={'ab' * 32}" in outputs and "approver=Alice | Moyo" in outputs
    summary = (step.tmp / "summary").read_text(encoding="utf-8")
    assert "Alice / Moyo (pinned passkey)" in summary and "run 42 attempt 2" in summary


def test_unpinned_approvers_warns(step, monkeypatch, capsys):
    monkeypatch.setenv("PERATHOS_GATE_APPROVERS", "")
    monkeypatch.setattr(step, "require_approval", lambda summary, **kw: RECEIPT)
    assert step.main() == 0
    assert "::warning::Perathos Gate: no approver keys are pinned" in capsys.readouterr().out
    assert "passkey NOT pinned" in (step.tmp / "summary").read_text(encoding="utf-8")


@pytest.mark.parametrize("exc_name,text", [("ApprovalDenied", "denied by Alice"), ("ApprovalTimeout", "still pending"),
                                           ("GateError", "ERR_GATE_UNTRUSTED_APPROVER: not one you pinned")])
def test_anything_but_an_approval_fails_the_step(step, monkeypatch, capsys, exc_name, text):
    def fake(summary, **kw):
        raise getattr(step, exc_name)(text)
    monkeypatch.setattr(step, "require_approval", fake)
    assert step.main() == 1
    assert "::error::Perathos Gate:" in capsys.readouterr().out
    assert not (step.tmp / "out" / "receipt.json").exists() and not (step.tmp / "output").exists()


def test_empty_summary_is_an_error(step, monkeypatch):
    monkeypatch.setenv("IN_SUMMARY", "  ")
    monkeypatch.setattr(step, "require_approval", lambda *a, **k: pytest.fail("must not be called"))
    assert step.main() == 2
