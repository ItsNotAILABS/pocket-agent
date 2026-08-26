import hashlib
import json
import zipfile

import pytest

from pocket_agent.mission_artifacts import ArtifactStore, UnsupportedArtifactFormat
from pocket_agent.mission_executors import AuroCouncilTaskExecutor, RuntimeCellTaskExecutor
from pocket_agent.mission_orchestrator import MissionOrchestrator, MissionPlanner, PackageTaskExecutor
from pocket_agent.mission_service import MissionAuthorizationError, MissionService
from pocket_agent.mission_store import MissionStore
from pocket_agent.runtime_cells import OperationRequest, RuntimeCellGovernor, RuntimeCellSpec


class FakeCouncilClient:
    url = "http://127.0.0.1:8090/v1/council/respond"
    api_token = ""

    def __init__(self):
        self.calls = []

    def respond(self, message, *, parent_context=None, timeout_seconds=None):
        self.calls.append({"message": message, "parent_context": parent_context})
        digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
        return {
            "schema": "auro.2b-council.turn.v1",
            "text": "A bounded result was produced. Architecture is not trained capability.",
            "structured_answer": {
                "answer": "A bounded result was produced.",
                "key_points": ["Architecture is not trained capability"],
                "confidence": 0.91,
            },
            "consensus_votes": [
                {"consensus": "Use the bounded result.", "confidence": 0.90},
                {"consensus": "Preserve evidence boundaries.", "confidence": 0.88},
            ],
            "runtime_receipt": {"receipt_sha256": digest},
            "mesie_receipts": [{"receipt_sha256": digest[::-1]}],
            "atomic_agent_count": 9,
            "model_backed_atomic_count": 9,
            "evidence_class": "E4-signed-receipt",
            "release_evidence_ready": True,
            "blockers": [],
        }


def build_runtime(tmp_path):
    store = MissionStore(tmp_path / "missions.sqlite3")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    client = FakeCouncilClient()
    council = AuroCouncilTaskExecutor(client, artifacts)
    package = PackageTaskExecutor(artifacts)
    orchestrator = MissionOrchestrator(
        store,
        artifacts,
        {
            "reasoning": council,
            "research": council,
            "implementation": council,
            "artifact": council,
            "review": council,
            "synthesis": council,
            "package": package,
        },
        planner=MissionPlanner(),
    )
    service = MissionService(
        store=store,
        artifacts=artifacts,
        orchestrator=orchestrator,
        council_client=client,
    )
    return store, artifacts, client, orchestrator, service


def test_default_mission_runs_parallel_dag_and_packages_artifacts(tmp_path):
    store, artifacts, client, orchestrator, _ = build_runtime(tmp_path)
    mission = orchestrator.create(
        objective="Research, design, review, and package a production proposal.",
        title="Production proposal",
        principal_id="alfredo",
        tenant_id="itsnotai",
        max_parallel=3,
    )
    assert len(mission["tasks"]) == 7
    result = orchestrator.run_burst(
        mission["mission_id"],
        worker_id="test-worker",
        max_tasks=20,
        time_budget_seconds=60,
    )
    snapshot = result["mission"]
    assert snapshot["status"] == "completed"
    assert snapshot["progress"]["completed"] == 7
    assert snapshot["artifact_manifest_sha256"]
    paths = {item["relative_path"] for item in snapshot["artifacts"]}
    assert "FINAL_RESULT.md" in paths
    assert "ARTIFACT_MANIFEST.json" in paths
    assert "mission-artifacts.zip" in paths
    assert len(snapshot["decisions"]) == 7
    assert len(client.calls) >= 15

    root = artifacts.mission_root(mission["mission_id"])
    with zipfile.ZipFile(root / "mission-artifacts.zip") as bundle:
        names = set(bundle.namelist())
        assert "ARTIFACT_MANIFEST.json" in names
        assert "mission-artifacts.zip" not in names


def test_store_rejects_cycles_and_enforces_mission_parallelism(tmp_path):
    store, _, _, orchestrator, _ = build_runtime(tmp_path)
    with pytest.raises(ValueError, match="cycle"):
        orchestrator.create(
            objective="invalid",
            tasks=[
                {"task_id": "a", "depends_on": ["b"]},
                {"task_id": "b", "depends_on": ["a"]},
            ],
            principal_id="alfredo",
            tenant_id="itsnotai",
        )

    mission = orchestrator.create(
        objective="parallel",
        tasks=[
            {"task_id": "a", "objective": "a"},
            {"task_id": "b", "objective": "b"},
            {"task_id": "c", "objective": "c"},
        ],
        principal_id="alfredo",
        tenant_id="itsnotai",
        max_parallel=2,
    )
    assert store.lease_ready_task("w1", mission_id=mission["mission_id"])
    assert store.lease_ready_task("w2", mission_id=mission["mission_id"])
    assert store.lease_ready_task("w3", mission_id=mission["mission_id"]) is None


def test_idempotency_budget_and_lease_recovery(tmp_path):
    store, _, _, orchestrator, _ = build_runtime(tmp_path)
    first = orchestrator.create(
        objective="idempotent",
        principal_id="alfredo",
        tenant_id="itsnotai",
        idempotency_key="request-1",
    )
    second = orchestrator.create(
        objective="idempotent",
        principal_id="alfredo",
        tenant_id="itsnotai",
        idempotency_key="request-1",
    )
    assert first["mission_id"] == second["mission_id"]

    with pytest.raises(ValueError, match="max_tasks"):
        orchestrator.create(
            objective="too many",
            tasks=[{"task_id": "a"}, {"task_id": "b"}],
            principal_id="alfredo",
            tenant_id="itsnotai",
            budget={"max_tasks": 1},
        )

    mission = orchestrator.create(
        objective="recover",
        tasks=[{"task_id": "recover", "objective": "recover"}],
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    leased = store.lease_ready_task(
        "worker-a", mission_id=mission["mission_id"], lease_seconds=30
    )
    assert leased["status"] == "running"
    assert store.recover_expired(int(leased["lease_expires_at_unix"]) + 1) == 1
    assert store.get_task("recover")["status"] == "queued"


def test_service_enforces_tenant_and_principal_boundaries(tmp_path):
    _, _, _, _, service = build_runtime(tmp_path)
    mission = service.create(
        {"objective": "tenant work"},
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    assert service.get(
        mission["mission_id"], principal_id="alfredo", tenant_id="itsnotai"
    )["mission_id"] == mission["mission_id"]
    with pytest.raises(MissionAuthorizationError):
        service.get(
            mission["mission_id"], principal_id="alfredo", tenant_id="other"
        )
    with pytest.raises(MissionAuthorizationError):
        service.get(
            mission["mission_id"], principal_id="someone-else", tenant_id="itsnotai"
        )


def test_unsupported_binary_artifact_is_not_faked(tmp_path):
    store, artifacts, _, orchestrator, _ = build_runtime(tmp_path)
    mission = orchestrator.create(
        objective="make a real PDF",
        tasks=[
            {
                "task_id": "pdf",
                "kind": "artifact",
                "objective": "produce PDF",
                "max_attempts": 1,
                "required_artifacts": ["deliverables/report.pdf"],
            }
        ],
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    result = orchestrator.run_burst(
        mission["mission_id"], worker_id="worker", max_tasks=2
    )
    assert result["mission"]["status"] == "failed"
    assert not (artifacts.mission_root(mission["mission_id"]) / "deliverables/report.pdf").exists()
    assert any(
        "UnsupportedArtifactFormat" in str(event["payload"])
        or "renderer" in str(event["payload"])
        for event in result["mission"]["events"]
    )


def test_runtime_cell_execution_requires_exact_one_time_approval(tmp_path):
    store = MissionStore(tmp_path / "missions.sqlite3")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    governor = RuntimeCellGovernor(tmp_path / "cells.sqlite3", signing_key="s" * 32)
    governor.register_cell(
        RuntimeCellSpec(
            cell_id="cell-1",
            runtime_class="agent-sandbox",
            principal_id="runtime-cell:1",
            agent_id="mission-agent",
            backend="test",
            policy={"network": {"default": "deny"}},
            state="ready",
        )
    )
    operation = OperationRequest(
        operator_id="alfredo",
        agent_id="mission-agent",
        cell_id="cell-1",
        tool="sandbox.command.execute",
        arguments={"argv": ["echo", "ok"]},
    )
    approval = governor.propose(operation)
    token = governor.approve(approval["approval_id"], "alfredo")
    executor = RuntimeCellTaskExecutor(
        governor,
        artifacts,
        backend=lambda action: {"ok": True, "tool": action["tool"]},
        validator=lambda output: {"status": "pass"},
    )
    orchestrator = MissionOrchestrator(
        store,
        artifacts,
        {"execution": executor},
        planner=MissionPlanner(),
    )
    mission = orchestrator.create(
        objective="approved execution",
        tasks=[
            {
                "task_id": "exec",
                "kind": "execution",
                "objective": "execute approved operation",
                "payload": {
                    "approval_id": approval["approval_id"],
                    "approval_token": token,
                    "operation": operation.to_dict(),
                },
            }
        ],
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    result = orchestrator.run_burst(
        mission["mission_id"], worker_id="worker", max_tasks=1
    )
    assert result["mission"]["status"] == "completed"
    assert governor.verify_receipt_chain()["status"] == "pass"

    replay = orchestrator.create(
        objective="replay",
        tasks=[
            {
                "task_id": "exec-replay",
                "kind": "execution",
                "objective": "replay operation",
                "max_attempts": 1,
                "payload": {
                    "approval_id": approval["approval_id"],
                    "approval_token": token,
                    "operation": operation.to_dict(),
                },
            }
        ],
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    replay_result = orchestrator.run_burst(
        replay["mission_id"], worker_id="worker", max_tasks=1
    )
    assert replay_result["mission"]["status"] == "failed"


def test_pause_resume_cancel_are_durable_and_idempotent(tmp_path):
    store, _, _, orchestrator, _ = build_runtime(tmp_path)
    mission = orchestrator.create(
        objective="lifecycle",
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    assert store.pause(mission["mission_id"])["status"] == "paused"
    assert store.resume(mission["mission_id"])["status"] == "queued"
    assert store.cancel(mission["mission_id"])["status"] == "cancelled"
    assert store.cancel(mission["mission_id"])["status"] == "cancelled"
