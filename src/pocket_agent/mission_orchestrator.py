"""Dependency-aware mission planner and orchestrator for POCKET Agent."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
import time
import uuid
from typing import Any, Callable, Mapping, Protocol, Sequence

from .mission_artifacts import ArtifactRecord, ArtifactStore
from .mission_store import MissionStore


@dataclass(frozen=True)
class TaskExecutionResult:
    summary: str
    output: Mapping[str, Any]
    artifacts: tuple[ArtifactRecord, ...] = ()
    decision: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    accepted: bool = True
    schema: str = "pocket.mission.task-result.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "output": dict(self.output),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "decision": dict(self.decision),
            "metrics": dict(self.metrics),
            "evidence": list(self.evidence),
            "blockers": list(self.blockers),
        }


class TaskExecutor(Protocol):
    def execute(
        self,
        mission: Mapping[str, Any],
        task: Mapping[str, Any],
        dependency_results: Sequence[Mapping[str, Any]],
        progress: Callable[[float, str], None] | None = None,
    ) -> TaskExecutionResult: ...


class MissionPlanner:
    """Normalize explicit tasks or construct a deep default mission graph."""

    KINDS = {
        "reasoning", "research", "implementation", "execution",
        "artifact", "review", "synthesis", "package",
    }

    @staticmethod
    def safe_task_id(value: str) -> str:
        clean = "".join(character if character.isalnum() or character in "_-" else "-" for character in value)
        clean = clean.strip("-_")
        return (clean or uuid.uuid4().hex[:12])[:120]

    def plan(
        self,
        objective: str,
        *,
        title: str = "POCKET Agent mission",
        tasks: Sequence[Mapping[str, Any]] | None = None,
        deliverables: Sequence[Mapping[str, Any] | str] = (),
        principal_id: str = "anonymous",
        tenant_id: str = "default",
        max_parallel: int = 3,
        budget: Mapping[str, Any] | None = None,
        deadline_unix: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        objective = str(objective).strip()
        if not objective:
            raise ValueError("mission objective is required")
        normalized = self.normalize_tasks(tasks, objective) if tasks else self.default_tasks(objective, deliverables)
        return {
            "schema": "pocket.mission.plan.v1",
            "mission_id": "mission_" + uuid.uuid4().hex,
            "idempotency_key": idempotency_key,
            "principal_id": str(principal_id),
            "tenant_id": str(tenant_id),
            "title": str(title)[:300],
            "objective": objective,
            "max_parallel": max(1, min(int(max_parallel), 32)),
            "budget": {
                "max_tasks": 500,
                "max_task_attempts": 10_000,
                "max_runtime_seconds": 0,
                **dict(budget or {}),
            },
            "deadline_unix": deadline_unix,
            "tasks": normalized,
            "reasoning_policy": {
                "private_chain_of_thought_exported": False,
                "decision_summaries_recorded": True,
                "independent_analysis_and_review": True,
                "artifact_delivery_required": True,
            },
        }

    def normalize_tasks(self, tasks: Sequence[Mapping[str, Any]], mission_objective: str) -> list[dict[str, Any]]:
        output, seen = [], set()
        for index, raw in enumerate(tasks):
            task_id = self.safe_task_id(str(raw.get("task_id") or f"task-{index + 1}"))
            if task_id in seen:
                raise ValueError(f"duplicate task_id: {task_id}")
            seen.add(task_id)
            kind = str(raw.get("kind") or "reasoning")
            if kind not in self.KINDS:
                raise ValueError(f"unsupported task kind: {kind}")
            output.append({
                "task_id": task_id,
                "title": str(raw.get("title") or task_id),
                "objective": str(raw.get("objective") or mission_objective),
                "kind": kind,
                "depends_on": [str(item) for item in raw.get("depends_on", []) or []],
                "priority": int(raw.get("priority", 0)),
                "model_lane": str(raw.get("model_lane") or "auro-2b-council"),
                "reasoning_rounds": max(1, min(int(raw.get("reasoning_rounds", 2)), 12)),
                "max_attempts": max(1, min(int(raw.get("max_attempts", 3)), 20)),
                "timeout_seconds": max(30, min(int(raw.get("timeout_seconds", 1800)), 86_400)),
                "payload": dict(raw.get("payload") or {}),
                "acceptance_criteria": list(raw.get("acceptance_criteria") or []),
                "required_artifacts": list(raw.get("required_artifacts") or []),
            })
        return output

    def default_tasks(self, objective: str, deliverables: Sequence[Mapping[str, Any] | str]) -> list[dict[str, Any]]:
        paths = []
        for index, item in enumerate(deliverables):
            value = str(item.get("path") or item.get("name") or f"deliverable-{index + 1}.md") if isinstance(item, Mapping) else str(item)
            if value.strip():
                paths.append(value.strip())
        if not paths:
            paths = ["deliverables/mission-report.md", "deliverables/mission-report.json"]
        return [
            self._task("interpret", "Interpret objective and constraints", f"Resolve scope, assumptions, constraints, unknowns, and testable success criteria for: {objective}", "reasoning", [], 100, 2, ["tasks/interpret/brief.md", "tasks/interpret/brief.json"]),
            self._task("evidence", "Collect and evaluate evidence", "Identify the strongest evidence, contradictions, risks, and missing validation for the mission.", "research", ["interpret"], 80, 3, ["tasks/evidence/evidence-review.md", "tasks/evidence/evidence-review.json"]),
            self._task("solution", "Develop the implementation or solution", "Produce the strongest practical solution, implementation, or work product for the objective.", "implementation", ["interpret"], 80, 3, ["tasks/solution/solution.md", "tasks/solution/solution.json"]),
            self._task("deliverables", "Create requested deliverables", "Convert the evidence and solution into polished deliverables without unsupported claims.", "artifact", ["evidence", "solution"], 60, 2, paths),
            self._task("red-team", "Red-team and quality review", "Challenge correctness, security, evidence, usability, and completeness; prioritize defects and residual risk.", "review", ["deliverables"], 50, 3, ["tasks/red-team/review.md", "tasks/red-team/review.json"], {"fail_on_blockers": False}),
            self._task("synthesize", "Synthesize final answer and handoff", "Reconcile the work and red-team findings into a coherent user-ready result with explicit next actions.", "synthesis", ["red-team"], 40, 2, ["FINAL_RESULT.md", "FINAL_RESULT.json"]),
            self._task("package", "Package artifacts and receipts", "Create the complete artifact manifest and downloadable bundle.", "package", ["synthesize"], 10, 1, ["ARTIFACT_MANIFEST.json", "mission-artifacts.zip"]),
        ]

    @staticmethod
    def _task(task_id: str, title: str, objective: str, kind: str, depends_on: list[str], priority: int, reasoning_rounds: int, artifacts: list[str], payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {
            "task_id": task_id, "title": title, "objective": objective, "kind": kind,
            "depends_on": depends_on, "priority": priority,
            "model_lane": "deterministic-packager" if kind == "package" else "auro-2b-council",
            "reasoning_rounds": reasoning_rounds, "max_attempts": 3,
            "timeout_seconds": 900 if kind == "package" else 3600,
            "payload": dict(payload or {}),
            "acceptance_criteria": ["result is explicit", "evidence and blockers are visible"],
            "required_artifacts": artifacts,
        }


class PackageTaskExecutor:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def execute(self, mission: Mapping[str, Any], task: Mapping[str, Any], dependency_results: Sequence[Mapping[str, Any]], progress: Callable[[float, str], None] | None = None) -> TaskExecutionResult:
        mission_id = str(mission["mission_id"])
        if progress:
            progress(0.25, "building artifact manifest")
        manifest_record, bundle_record, manifest = self.artifacts.build_bundle(mission_id)
        if progress:
            progress(0.95, "finalizing package receipt")
        return TaskExecutionResult(
            summary="Mission artifacts were packaged with a content hash manifest.",
            output={"manifest": manifest, "bundle": bundle_record.to_dict()},
            artifacts=(manifest_record, bundle_record),
            decision={
                "summary": "Packaged all mission outputs.", "options": [],
                "decision": "Deliver the generated ZIP and manifest.",
                "evidence": ["manifest:" + manifest["manifest_sha256"], "bundle:" + bundle_record.sha256],
                "confidence": 1.0, "blockers": [], "private_chain_of_thought_exported": False,
            },
            metrics={"artifact_count": manifest["artifact_count"], "bundle_bytes": bundle_record.bytes},
            evidence=("manifest:" + manifest["manifest_sha256"], "bundle:" + bundle_record.sha256),
        )


class MissionOrchestrator:
    """Create and execute durable mission DAGs in bounded resumable bursts."""

    def __init__(self, store: MissionStore, artifacts: ArtifactStore, executors: Mapping[str, TaskExecutor], *, planner: MissionPlanner | None = None) -> None:
        self.store = store
        self.artifacts = artifacts
        self.executors = dict(executors)
        self.planner = planner or MissionPlanner()

    def create(self, **request: Any) -> dict[str, Any]:
        return self.store.create_mission(self.planner.plan(**request))

    def run_burst(self, mission_id: str, *, worker_id: str, max_tasks: int = 20, time_budget_seconds: int = 300, capabilities: Sequence[str] = ()) -> dict[str, Any]:
        started = time.monotonic()
        executed = failures = 0
        maximum = max(1, min(int(max_tasks), 500))
        while executed < maximum:
            mission = self.store.get_mission(mission_id, include_events=False)
            if mission["status"] in {"completed", "failed", "cancelled", "paused"}:
                break
            elapsed = time.monotonic() - started
            remaining = max(1, int(time_budget_seconds) - int(elapsed))
            if elapsed >= max(1, int(time_budget_seconds)):
                break
            concurrency = min(int(mission["max_parallel"]), maximum - executed)
            leased = []
            for slot in range(max(1, concurrency)):
                task = self.store.lease_ready_task(
                    f"{worker_id}:{slot}", mission_id=mission_id,
                    lease_seconds=86_400, capabilities=capabilities,
                )
                if task is None:
                    break
                leased.append((task, f"{worker_id}:{slot}"))
            if not leased:
                break

            pool = ThreadPoolExecutor(max_workers=len(leased))
            futures: dict[Future[TaskExecutionResult], tuple[dict[str, Any], str]] = {}
            try:
                for task, owner in leased:
                    dependencies = [self.store.get_task(item) for item in task.get("depends_on", [])]
                    mission_snapshot = self.store.get_mission(mission_id, include_events=False)
                    executor = self.executors.get(str(task["kind"])) or self.executors.get("default")
                    if executor is None:
                        self.store.fail_task(task["task_id"], owner, f"no executor for task kind {task['kind']}", terminal=True)
                        failures += 1
                        executed += 1
                        continue

                    def heartbeat(value: float, note: str, *, task_id=task["task_id"], lease_owner=owner, timeout=task["timeout_seconds"]):
                        self.store.heartbeat(task_id, lease_owner, progress=value, lease_seconds=max(int(timeout) + 120, 900), note=note)

                    futures[pool.submit(executor.execute, mission_snapshot, task, dependencies, heartbeat)] = (task, owner)

                for future in as_completed(futures):
                    task, owner = futures[future]
                    try:
                        result = future.result()
                        if result.accepted:
                            self.store.complete_task(task["task_id"], owner, result.to_dict(), artifacts=[item.to_dict() for item in result.artifacts], decision=result.decision)
                        else:
                            self.store.fail_task(task["task_id"], owner, "; ".join(result.blockers) or "task acceptance failed", terminal=True)
                            failures += 1
                    except Exception as exc:
                        try:
                            self.store.fail_task(task["task_id"], owner, f"{type(exc).__name__}: {str(exc)[:2000]}", retry_delay_seconds=30)
                        except PermissionError:
                            pass
                        failures += 1
                    executed += 1
                    if time.monotonic() - started >= max(1, int(time_budget_seconds)):
                        break
            finally:
                pool.shutdown(wait=True, cancel_futures=False)

        mission = self.store.get_mission(mission_id)
        if mission["status"] == "completed" and not mission.get("result_summary"):
            self.finalize(mission)
            mission = self.store.get_mission(mission_id)
        return {
            "schema": "pocket.mission.run-burst.v1",
            "mission": mission,
            "tasks_executed": executed,
            "task_failures_or_retries": failures,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "stopped_because": "mission-terminal" if mission["status"] in {"completed", "failed", "cancelled", "paused"} else "idle-or-budget-exhausted",
        }

    def finalize(self, mission: Mapping[str, Any]) -> None:
        synthesis = next((task for task in mission.get("tasks", []) if task.get("task_id") == "synthesize" and task.get("result")), None)
        summary = str((synthesis.get("result") or {}).get("summary") or "Mission completed.") if synthesis else "Mission completed."
        manifest = self.artifacts.manifest(str(mission["mission_id"]))
        self.store.set_result_summary(str(mission["mission_id"]), summary, manifest["manifest_sha256"])

    def status(self) -> dict[str, Any]:
        return {
            "schema": "pocket.mission-orchestrator.status.v1",
            "database": str(self.store.path), "artifact_root": str(self.artifacts.root),
            "executors": sorted(self.executors),
            "features": [
                "dependency-aware-DAG", "parallel-ready-tasks", "mission-parallelism-enforced-in-SQL",
                "pause-resume-cancel", "lease-recovery", "bounded-retries", "budgets-and-deadlines",
                "multi-pass-reasoning-adapters", "decision-summaries-without-private-chain-of-thought",
                "content-addressed-artifacts", "artifact-manifest-and-ZIP",
            ],
        }
