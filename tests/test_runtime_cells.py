from __future__ import annotations

import pytest

from pocket_agent.runtime_cells import (
    EXECUTION_SEQUENCE,
    RUNTIME_CLASSES,
    OperationRequest,
    RuntimeCellGovernor,
    RuntimeCellSpec,
)


def cell() -> RuntimeCellSpec:
    return RuntimeCellSpec(
        cell_id="cell-builder-1",
        runtime_class="agent-sandbox",
        principal_id="runtime-cell:builder-1",
        agent_id="alpha-builder",
        backend="openshell-adapter",
        policy={
            "filesystem": {"writable": ["/workspace"], "deny": ["/secrets", "/host"]},
            "network": {"default": "deny", "allow": ["api.github.com"]},
            "secrets": "none-by-default",
        },
        state="ready",
    )


def operation(**overrides) -> OperationRequest:
    values = {
        "operator_id": "operator-1",
        "agent_id": "alpha-builder",
        "cell_id": "cell-builder-1",
        "tool": "sandbox.command.execute",
        "arguments": {"argv": ["python", "-m", "pytest", "-q"]},
        "filesystem_scope": ["/workspace"],
        "egress_scope": [],
        "environment": "development",
        "estimated_cost_usd": 0.2,
        "destructive": False,
    }
    values.update(overrides)
    return OperationRequest(**values)


def test_canonical_runtime_classes_and_sequence():
    assert RUNTIME_CLASSES == ("agent-sandbox", "app-bottle", "mini-os")
    assert EXECUTION_SEQUENCE == ("discover", "classify-risk", "plan", "approve", "execute", "validate", "receipt")


def test_runtime_cell_registration_and_exact_action_approval(tmp_path):
    governor = RuntimeCellGovernor(tmp_path / "runtime.sqlite3", signing_key="test-secret")
    registered = governor.register_cell(cell())
    assert registered["schema"] == "nexus.runtime-cell.v1"
    assert registered["policy_hash"] == cell().policy_hash

    op = operation()
    approval = governor.propose(op)
    token = governor.approve(approval["approval_id"], "operator-1")

    mutated = operation(arguments={"argv": ["python", "-c", "print('different')"]})
    with pytest.raises(ValueError, match="exact action"):
        governor.consume(approval["approval_id"], mutated, token)

    stored = governor.consume(approval["approval_id"], op, token)
    assert stored["tool"] == "sandbox.command.execute"


def test_approval_cannot_be_replayed_after_store_restart(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    first = RuntimeCellGovernor(path, signing_key="test-secret")
    first.register_cell(cell())
    op = operation()
    approval = first.propose(op)
    token = first.approve(approval["approval_id"], "operator-1")
    first.consume(approval["approval_id"], op, token)

    second = RuntimeCellGovernor(path, signing_key="test-secret")
    with pytest.raises(ValueError, match="consumed"):
        second.consume(approval["approval_id"], op, token)


def test_execute_records_signed_hash_chain_and_validation(tmp_path):
    governor = RuntimeCellGovernor(tmp_path / "runtime.sqlite3", signing_key="test-secret")
    governor.register_cell(cell())

    def run_once(index: int):
        op = operation(arguments={"argv": ["task", str(index)]})
        approval = governor.propose(op)
        token = governor.approve(approval["approval_id"], "operator-1")
        receipt = governor.execute(
            approval_id=approval["approval_id"],
            operation=op,
            token=token,
            executor=lambda action: {"ok": True, "argv": action["arguments"]["argv"]},
            validator=lambda output: {"status": "pass", "output_ok": output["ok"]},
        )
        assert receipt["status"] == "succeeded"
        assert receipt["signed"] is True
        assert receipt["validation"]["status"] == "pass"
        return receipt

    first = run_once(1)
    second = run_once(2)
    assert first["previous_receipt_hash"] is None
    assert second["previous_receipt_hash"] == first["digest"]
    chain = governor.verify_receipt_chain()
    assert chain["status"] == "pass"
    assert chain["count"] == 2
    assert chain["head"] == second["digest"]


def test_nonempty_approval_id_is_not_authorization(tmp_path):
    governor = RuntimeCellGovernor(tmp_path / "runtime.sqlite3", signing_key="test-secret")
    governor.register_cell(cell())
    op = operation()
    approval = governor.propose(op)
    with pytest.raises(ValueError, match="invalid approval token"):
        governor.consume(approval["approval_id"], op, approval["approval_id"])
