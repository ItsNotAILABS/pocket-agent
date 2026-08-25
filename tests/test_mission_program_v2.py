import hashlib
import json
from pathlib import Path

import pytest

from pocket_agent.mission_artifacts import ArtifactStore, UnsupportedArtifactFormat
from pocket_agent.mission_executors import AuroCouncilTaskExecutor
from pocket_agent.mission_orchestrator import MissionOrchestrator, PackageTaskExecutor
from pocket_agent.mission_profiles import DeliverableContract, reasoning_profile
from pocket_agent.mission_program import (
    ContractArtifactExecutor,
    MissionProgramPlanner,
    MissionProgramService,
)
from pocket_agent.mission_renderers import (
    ArtifactRendererRegistry,
    callable_binary_renderer,
)
from pocket_agent.mission_store import MissionStore
from pocket_agent.mission_worker import MissionWorker, WorkerConfig


class FakeCouncilClient:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"configured": True, "fake": True}

    def respond(self, objective, *, context="", reasoning_rounds=1, model_lane=None):
        self.calls.append(
            {
                "objective": objective,
                "context": context,
                "reasoning_rounds": reasoning_rounds,
                "model_lane": model_lane,
            }
        )
        digest = hashlib.sha256(
            f"{objective}|{context}|{reasoning_rounds}".encode()
        ).hexdigest()
        return {
            "schema": "auro.2b-council.turn.v1",
            "text": f"Completed: {objective[:160]}",
            "structured_answer": {
                "answer": f"Completed: {objective[:160]}",
                "key_points": ["Evidence is explicit", "Blockers remain visible"],
                "recommendations": ["Validate before delivery"],
                "caveats": [],
                "confidence": 0.91,
                "citations": [],
            },
            "promotion_ready": True,
            "release_evidence_ready": True,
            "blockers": [],
            "evidence_class": "E3-validated-output",
            "runtime_receipt_sha256": digest,
            "runtime_receipt": {
                "schema": "test.council.receipt.v1",
                "receipt_sha256": digest,
            },
            "specialist_reports": [],
            "consensus_votes": [],
            "atomic_agent_count": 0,
            "estimated_text_reduction": 0.0,
        }


def build_service(tmp_path, registry=None):
    store = MissionStore(tmp_path / "missions.sqlite3")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    client = FakeCouncilClient()
    council = AuroCouncilTaskExecutor(client, artifacts)
    renderers = registry or ArtifactRendererRegistry()
    artifact_executor = ContractArtifactExecutor(council, artifacts, renderers)
    orchestrator = MissionOrchestrator(
        store,
        artifacts,
        {
            "reasoning": council,
            "research": council,
            "implementation": council,
            "review": council,
            "synthesis": council,
            "artifact": artifact_executor,
            "package": PackageTaskExecutor(artifacts),
        },
    )
    service = MissionProgramService(
        store=store,
        artifacts=artifacts,
        orchestrator=orchestrator,
        renderers=renderers,
        council_client=client,
    )
    return service, client


def test_named_reasoning_profiles_increase_depth_and_revision_cycles():
    quick = reasoning_profile("quick")
    standard = reasoning_profile("standard")
    deep = reasoning_profile("deep")
    exhaustive = reasoning_profile("exhaustive")
    assert quick.revision_cycles == 0
    assert standard.revision_cycles == 1
    assert deep.revision_cycles == 2
    assert exhaustive.revision_cycles == 3
    assert quick.solution_rounds < standard.solution_rounds < deep.solution_rounds < exhaustive.solution_rounds
    assert exhaustive.independent_reviewers == 4
    assert exhaustive.max_tasks > deep.max_tasks


def test_planner_compiles_multiple_parallel_workstreams_and_repeated_review():
    planner = MissionProgramPlanner()
    program = planner.plan(
        title="Ship the product",
        objectives=[
            {"id": "runtime", "objective": "Build the runtime", "priority": 4},
            {"id": "research", "objective": "Validate the architecture"},
            {"id": "launch", "objective": "Prepare the launch assets"},
        ],
        profile="deep",
        deliverables=[
            "deliverables/final-report.md",
            "deliverables/evidence.json",
            "deliverables/release-table.csv",
        ],
        principal_id="alfredo",
        tenant_id="itsnotai",
    )
    tasks = list(program.tasks)
    task_ids = [task["task_id"] for task in tasks]
    assert len(task_ids) == len(set(task_ids))
    assert len(tasks) > 40
    assert program.max_parallel == 5
    assert program.reasoning_profile["revision_cycles"] == 2
    assert sum(task["payload"].get("phase") == "review" for task in tasks) == 18
    assert {task["payload"].get("workstream_id") for task in tasks if task["payload"].get("workstream_id")} == {"runtime", "research", "launch"}
    package = next(task for task in tasks if task["kind"] == "package")
    assert package["required_artifacts"] == ["ARTIFACT_MANIFEST.json", "mission-artifacts.zip"]
    global_artifact = next(
        task
        for task in tasks
        if task["kind"] == "artifact" and task["payload"].get("phase") == "final-deliverables"
    )
    assert set(global_artifact["required_artifacts"]) == {
        "deliverables/final-report.md",
        "deliverables/evidence.json",
        "deliverables/release-table.csv",
    }
    known = set(task_ids)
    assert all(set(task["depends_on"]).issubset(known) for task in tasks)


def test_program_namespaces_task_ids_so_many_missions_share_one_database(tmp_path):
    service, _ = build_service(tmp_path)
    first = service.create_program(
        {"title": "First", "objectives": ["Complete first objective"], "reasoning_profile": "quick"},
        principal_id="user-a",
        tenant_id="tenant-a",
    )
    second = service.create_program(
        {"title": "Second", "objectives": ["Complete second objective"], "reasoning_profile": "quick"},
        principal_id="user-a",
        tenant_id="tenant-a",
    )
    first_tasks = {task["task_id"] for task in first["mission"]["tasks"]}
    second_tasks = {task["task_id"] for task in second["mission"]["tasks"]}
    assert first["mission"]["mission_id"] != second["mission"]["mission_id"]
    assert first_tasks.isdisjoint(second_tasks)
    assert len(service.store.list_missions(tenant_id="tenant-a")) == 2
    service.store.close()


def test_renderer_registry_refuses_fake_binary_and_accepts_real_registered_renderer(tmp_path):
    registry = ArtifactRendererRegistry()
    with pytest.raises(ValueError, match="registered renderer"):
        DeliverableContract("deliverables/report.pdf", title="Report")

    registry.register(
        "test-pdf",
        {".pdf"},
        callable_binary_renderer(
            "test-pdf",
            "application/pdf",
            lambda contract, source: b"%PDF-1.7\n% real renderer fixture\n%%EOF\n",
        ),
    )
    contract = DeliverableContract(
        "deliverables/report.pdf",
        title="Report",
        renderer="test-pdf",
        minimum_bytes=16,
    )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    record, receipt = registry.render_to_store(
        artifacts,
        "mission-pdf",
        "task-pdf",
        contract,
        {"answer": "Rendered content"},
    )
    assert artifacts.resolve("mission-pdf", record.relative_path).read_bytes().startswith(b"%PDF")
    assert record.media_type == "application/pdf"
    assert receipt["renderer"] == "test-pdf"
    assert receipt["valid"] is True


def test_end_to_end_multi_workstream_mission_delivers_artifacts_and_package(tmp_path):
    service, client = build_service(tmp_path)
    created = service.create_program(
        {
            "title": "Integrated customer delivery",
            "objective": "Complete two related workstreams and deliver a verified package.",
            "objectives": [
                {"id": "analysis", "objective": "Analyze the problem"},
                {"id": "implementation", "objective": "Design the implementation"},
            ],
            "reasoning_profile": "quick",
            "deliverables": [
                "deliverables/final.md",
                "deliverables/final.json",
                "deliverables/findings.csv",
                "deliverables/summary.html",
            ],
        },
        principal_id="operator",
        tenant_id="org-1",
    )
    mission_id = created["mission"]["mission_id"]
    result = service.run(
        mission_id,
        {"max_tasks": 100, "time_budget_seconds": 120},
        principal_id="operator",
        tenant_id="org-1",
    )
    mission = result["mission"]
    assert mission["status"] == "completed"
    assert mission["progress"]["completed"] == mission["progress"]["total"]
    paths = {artifact["relative_path"] for artifact in service.artifacts.list(mission_id)}
    assert {
        "deliverables/final.md",
        "deliverables/final.json",
        "deliverables/findings.csv",
        "deliverables/summary.html",
        "ARTIFACT_MANIFEST.json",
        "mission-artifacts.zip",
    }.issubset(paths)
    assert service.artifacts.verify_manifest(mission_id)["valid"] is True
    assert client.calls
    assert max(call["reasoning_rounds"] for call in client.calls) >= 1
    service.store.close()


def test_long_running_worker_advances_multiple_missions_and_writes_heartbeat(tmp_path):
    service, _ = build_service(tmp_path)
    mission_ids = []
    for index in range(2):
        created = service.create_program(
            {
                "title": f"Mission {index}",
                "objectives": [f"Complete objective {index}"],
                "reasoning_profile": "quick",
            },
            principal_id="operator",
            tenant_id="org-worker",
        )
        mission_ids.append(created["mission"]["mission_id"])

    heartbeat = tmp_path / "worker-heartbeat.json"
    worker = MissionWorker(
        service,
        WorkerConfig(
            worker_id="test-worker",
            poll_seconds=0.1,
            idle_backoff_seconds=0.1,
            tasks_per_burst=100,
            burst_time_budget_seconds=120,
            max_missions_per_cycle=10,
            heartbeat_path=str(heartbeat),
            tenant_allowlist=("org-worker",),
        ),
    )
    cycle = worker.run_cycle()
    worker.write_heartbeat(state="stopped")
    assert cycle["missions_examined"] == 2
    assert cycle["progressed"] is True
    assert worker.tasks_completed > 0
    assert heartbeat.is_file()
    heartbeat_data = json.loads(heartbeat.read_text())
    assert heartbeat_data["state"] == "stopped"
    assert heartbeat_data["worker_id"] == "test-worker"
    assert all(service.store.get_mission(mission_id)["status"] == "completed" for mission_id in mission_ids)
    service.store.close()


def test_program_rejects_task_explosion_beyond_profile_budget():
    planner = MissionProgramPlanner()
    with pytest.raises(ValueError, match="requires .* tasks"):
        planner.plan(
            objectives=[f"Objective {index}" for index in range(20)],
            profile={"base": "quick", "name": "tiny-budget", "max_tasks": 10},
        )
