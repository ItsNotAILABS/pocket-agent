from pocket_agent.capsules import CAPSULE_REASONS, list_reasons, spin, reason_ids


def test_twenty_reasons():
    assert len(CAPSULE_REASONS) == 20
    assert len(list_reasons()) == 20
    assert "untrusted_eval" in reason_ids()
    assert "webgpu_compute" in reason_ids()


def test_spin_local():
    cap = spin(reason="rollback_experiment", tier="256MB")
    assert cap.get("ok") is True
    assert cap.get("id", "").startswith("cap-")
    assert cap.get("reason") == "rollback_experiment"
