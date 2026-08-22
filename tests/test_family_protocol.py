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


def test_envelope_preserves_family_metadata():
    env = make_envelope(
        "agent.run",
        {"goal": "inspect repository"},
        session_id="session-1",
        principal="user-1",
        tenant="team-1",
    )
    data = env.to_dict()
    assert data["schema"] == FAMILY_SCHEMA
    assert data["request_id"].startswith("pfr_")
    assert data["session_id"] == "session-1"
    assert data["tenant"] == "team-1"
    assert data["payload"]["goal"] == "inspect repository"


def test_receipt_is_hash_linkable_without_reasoning_trace():
    env = make_envelope("agent.capsule", {"reason": "untrusted_eval"}, session_id="s1")
    receipt = make_receipt(
        env,
        status="completed",
        runtime_ms=42,
        result_summary="capsule completed",
        artifact_hashes=("sha256:abc",),
    ).to_dict()
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["request_id"] == env.request_id
    assert receipt["receipt_hash"]
    assert "reasoning" not in receipt
    assert "chain_of_thought" not in receipt


def test_invalid_action_is_rejected():
    try:
        make_envelope("agent.delete_everything")
    except ValueError as exc:
        assert "unsupported_action" in str(exc)
    else:
        raise AssertionError("unsupported action should fail")
