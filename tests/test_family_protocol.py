from pocket_agent.family_protocol import (
    FAMILY_SCHEMA,
    RECEIPT_SCHEMA,
    SUPPORTED_ACTIONS,
    capability_descriptor,
    make_envelope,
    make_receipt,
)


def test_capability_descriptor_is_provider_neutral():
    d = capability_descriptor()
    assert d["schema"] == FAMILY_SCHEMA
    assert d["component"] == "pocket-agent"
    assert d["plane"] == "execution"
    assert d["actions"] == list(SUPPORTED_ACTIONS)
    assert d["reasoning_exposed"] is False


def test_envelope_matches_canonical_family_shape():
    env = make_envelope(
        "agent.run",
        {"goal": "inspect repository"},
        session_id="session-1",
        principal="user-1",
        tenant="team-1",
        agent_id="agent-1",
        policy={"capabilities": ["repo:read"], "risk_tier": "low"},
    )
    data = env.to_dict()
    assert data["schema"] == FAMILY_SCHEMA
    assert data["request_id"].startswith("pfr_")
    assert data["principal"]["id"] == "user-1"
    assert data["principal"]["tenant_id"] == "team-1"
    assert data["scope"]["session_id"] == "session-1"
    assert data["scope"]["tenant_id"] == "team-1"
    assert data["scope"]["agent_id"] == "agent-1"
    assert data["payload"]["goal"] == "inspect repository"
    assert data["policy"]["risk_tier"] == "low"


def test_mapping_principal_is_preserved():
    env = make_envelope(
        "agent.attach",
        {"target": "a1"},
        principal={"id": "svc-1", "type": "service", "roles": ["runner"]},
        tenant="tenant-a",
    )
    data = env.to_dict()
    assert data["principal"]["id"] == "svc-1"
    assert data["principal"]["type"] == "service"
    assert data["principal"]["roles"] == ["runner"]
    assert data["principal"]["tenant_id"] == "tenant-a"


def test_receipt_is_canonical_hashable_and_reasoning_safe():
    env = make_envelope(
        "agent.capsule",
        {"reason": "untrusted_eval"},
        session_id="s1",
        principal="user-1",
        tenant="team-1",
        agent_id="agent-1",
    )
    receipt = make_receipt(
        env,
        status="completed",
        runtime_ms=42,
        result_summary="capsule completed",
        artifact_hashes=("sha256:abc",),
    ).to_dict()
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["receipt_id"].startswith("per_")
    assert receipt["request_id"] == env.request_id
    assert receipt["status"] == "succeeded"
    assert receipt["duration_ms"] == 42
    assert receipt["principal_id"] == "user-1"
    assert receipt["tenant_id"] == "team-1"
    assert receipt["session_id"] == "s1"
    assert receipt["agent_id"] == "agent-1"
    assert len(receipt["digest"]) == 64
    assert receipt["metadata"]["reasoning_exposed"] is False
    assert "reasoning" not in receipt
    assert "chain_of_thought" not in receipt


def test_explicit_succeeded_status_is_supported():
    env = make_envelope("agent.run", {"goal": "test"})
    receipt = make_receipt(env, status="succeeded", runtime_ms=1).to_dict()
    assert receipt["status"] == "succeeded"


def test_invalid_action_is_rejected():
    try:
        make_envelope("agent.delete_everything")
    except ValueError as exc:
        assert "unsupported_action" in str(exc)
    else:
        raise AssertionError("unsupported action should fail")


def test_invalid_status_is_rejected():
    env = make_envelope("agent.run")
    try:
        make_receipt(env, status="mystery", runtime_ms=0)
    except ValueError as exc:
        assert "unsupported_status" in str(exc)
    else:
        raise AssertionError("unsupported status should fail")
