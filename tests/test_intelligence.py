from pocket_agent.intelligence import (
    Budget,
    Usage,
    budget_status,
    detect_drift,
    evaluate_outcome,
    recovery_plan,
    route_capability,
)


def test_budget_status_blocks_overrun():
    b = Budget(max_files_changed=2, max_changed_bytes=100)
    s = budget_status(b, Usage(files_changed=3, changed_bytes=50))
    assert s["ok"] is False
    assert s["status"] == "budget_exhausted"
    assert "files_changed" in s["exceeded"]


def test_budget_protocol_shape():
    p = Budget().to_protocol()
    assert p["schema"] == "nexus.budget.v1"
    assert p["limits"]["max_children"] == 8


def test_router_prefers_execution_plane():
    caps = [
        {"component": "pocket-voice", "role": "voice turn timing", "actions": ["voice.session"]},
        {"component": "pocket-agent", "role": "long running execution", "actions": ["agent.run", "agent.capsule"]},
    ]
    r = route_capability("run long agent execution", caps)
    assert r["selected"] == "pocket-agent"
    assert r["needs_review"] is False


def test_router_flags_ambiguous_intent():
    r = route_capability("purple banana", [{"component": "pocket-agent", "actions": ["agent.run"]}])
    assert r["needs_review"] is True


def test_outcome_requires_real_evidence():
    acceptance = {
        "min_tests_passed": 4,
        "required_artifacts": ["report.json", "receipt.json"],
        "require_clean_exit": True,
        "require_receipt": True,
    }
    bad = evaluate_outcome(acceptance, {"tests_passed": 4, "artifacts": ["report.json"], "exit_code": 0})
    assert bad["ok"] is False
    assert set(bad["failed"]) == {"artifacts", "receipt"}
    good = evaluate_outcome(
        acceptance,
        {"tests_passed": 5, "artifacts": ["report.json", "receipt.json"], "exit_code": 0, "receipt_digest": "abc"},
    )
    assert good["ok"] is True


def test_drift_detects_capability_mismatch():
    d = detect_drift(
        {"version": "1", "actions": ["agent.run", "agent.attach"]},
        {"version": "2", "actions": ["agent.run", "agent.delete"]},
    )
    assert d["drift"] is True
    assert d["missing_actions"] == ["agent.attach"]
    assert d["undeclared_actions"] == ["agent.delete"]


def test_recovery_is_bounded():
    retry = recovery_plan(error_code="upstream_timeout", retryable=True)
    assert retry["recommended_action"] == "retry_once"
    assert retry["max_automatic_retries"] == 1
    handoff = recovery_plan(error_code="provider_down", retryable=False, fallback_components=["local-model"])
    assert handoff["recommended_action"] == "handoff"
