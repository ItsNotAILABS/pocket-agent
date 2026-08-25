"""Dependency-aware planning and bounded execution for POCKET Agent missions.

The scheduler records decision summaries and evidence, never private model
chain-of-thought. Task identifiers are namespaced by mission so independent
users may reuse human-friendly local task names without database collisions.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
import time
import uuid
from typing import Any, Callable, Mapping, Protocol, Sequence

from .mission_artifacts import ArtifactRecord, ArtifactStore
from .mission_store import MissionStore


def _safe_task_id(value: str) -> str:
    clean = "".join(
        character if character.isalnum() or character in "_-" else "-"
        for character in str(value)
    ).strip("-_")
    return (clean or uuid.uuid4().hex[:12])[:120]


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
            "schema": self.schema,
            "summary": self.summary,
            "output": dict(self.output),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "decision": dict(self.decision),
            "metrics": dict(self.metrics),
            "evidence": list(self.evidence),
            "blockers": list(self.blockers),
            "accepted": self.accepted,
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
    """Normalize an explicit DAG or create the default deep-work graph."""

    KINDS = {
        "reasoning",
        "research",
        "implementation",
        "artifact",
        "review",
        "synthesis",
        "package",
        "execution",
    }

    def plan(
        self,
        objective: str,
        *,
        title: str = "POCKET Agent mission",
        tasks: Sequence[Mapping[str, Any]] | None = None,
        deliverables: Sequence[Mapping[str, Any] | str] = (),
        principal_id: str = "operator",
        tenant_id: str = "default",
        max_parallel: int = 3,
        budget: Mapping[str, Any] | None = None,
        deadline_unix: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        objective = str(objective).strip()
        if not objective:
            raise ValueError("mission objective is required")
        mission_id = "mission_" + uuid.uuid4().hex
        local_tasks = (
            self._normalize_explicit(tasks, objective)
            if tasks
            else self._default_tasks(objective, deliverables)
        )
        namespaced = self._namespace_tasks(mission_id, local_tasks)
        normalized_budget = {
            "max_tasks": 64,
            "max_runtime_seconds": 86_400,
            "max_artifact_bytes": 512 * 1024 * 1024,
            "max_task_attempts": 256,
            **dict(budget or {}),
        }
        return {
            "schema": "pocket.mission.plan.v1",
            "mission_id": mission_id,
            "idempotency_key": idempotency_key,
            "principal_id": principal_id,
            "tenant_id": tenant_id,
            "title": str(title)[:300],
            "objective": objective,
            "max_parallel": max(1, min(int(max_parallel), 16)),
            "budget": normalized_budget,
            "deadline_unix": deadline_unix,
            "tasks": namespaced,
            "reasoning_policy": {
                "private_chain_of_thought_exported": False,
                "decision_summaries_recorded": True,
                "independent_analysis_and_review": True,
                "artifact_delivery_required": True,
            },
        }

    def _normalize_explicit(
        self,
        tasks: Sequence[Mapping[str, Any]],
        mission_objective: str,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(tasks):
            local_id = _safe_task_id(
                str(raw.get("task_id") or f"task-{index + 1}")
            )
            if local_id in seen:
                raise ValueError(f"duplicate task_id: {local_id}")
            seen.add(local_id)
            kind = str(raw.get("kind") or "reasoning")
            if kind not in self.KINDS:
                raise ValueError(f"unsupported task kind: {kind}")
            output.append(
                {
                    "task_id": local_id,
                    "title": str(raw.get("title") or local_id),
                    "objective": str(
                        raw.get("objective") or mission_objective
                    ),
                    "kind": kind,
                    "depends_on": [
                        _safe_task_id(str(item))
                        for item in raw.get("depends_on", []) or []
                    ],
                    "priority": int(raw.get("priority", 0)),
                    "model_lane": str(
                        raw.get("model_lane") or "auro-2b-council"
                    ),
                    "reasoning_rounds": max(
                        1, min(int(raw.get("reasoning_rounds", 2)), 6)
                    ),
                    "max_attempts": max(
                        1, min(int(raw.get("max_attempts", 3)), 10)
                    ),
                    "timeout_seconds": max(
                        30,
                        min(
                            int(raw.get("timeout_seconds", 1800)),
                            86_400,
                        ),
                    ),
                    "payload": dict(raw.get("payload") or {}),
                    "acceptance_criteria": list(
                        raw.get("acceptance_criteria") or []
                    ),
                    "required_artifacts": list(
                        raw.get("required_artifacts") or []
                    ),
                }
            )
        return output

    @staticmethod
    def _namespace_tasks(
        mission_id: str,
        tasks: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        mapping = {
            str(task["task_id"]): f"{mission_id}__{task['task_id']}"
            for task in tasks
        }
        output = []
        for raw in tasks:
            local_id = str(raw["task_id"])
            task = dict(raw)
            payload = dict(task.get("payload") or {})
            payload.setdefault("local_task_id", local_id)
            task["payload"] = payload
            task["task_id"] = mapping[local_id]
            task["depends_on"] = [
                mapping.get(str(item), str(item))
                for item in task.get("depends_on", [])
            ]
            output.append(task)
        return output

    def _default_tasks(
        self,
        objective: str,
        deliverables: Sequence[Mapping[str, Any] | str],
    ) -> list[dict[str, Any]]:
        paths = []
        for index, item in enumerate(deliverables):
            if isinstance(item, Mapping):
                path = str(
                    item.get("path")
                    or item.get("name")
                    or f"deliverable-{index + 1}.md"
                )
            else:
                path = str(item)
            if path.strip():
                paths.append(path.strip())
        if not paths:
            paths = [
                "deliverables/mission-report.md",
                "deliverables/mission-report.json",
            ]
        return [
            {
                "task_id": "interpret",
                "title": "Interpret objective and constraints",
                "objective": (
                    "Resolve scope, assumptions, constraints, success criteria, "
                    f"and unknowns for: {objective}"
                ),
                "kind": "reasoning",
                "depends_on": [],
                "priority": 100,
                "reasoning_rounds": 2,
                "required_artifacts": [
                    "tasks/interpret/brief.md",
                    "tasks/interpret/brief.json",
                ],
            },
            {
                "task_id": "evidence",
                "title": "Collect and evaluate evidence",
                "objective": (
                    "Identify evidence, contradictions, risks, and missing "
                    "validation for the mission."
                ),
                "kind": "research",
                "depends_on": ["interpret"],
                "priority": 80,
                "reasoning_rounds": 3,
                "required_artifacts": [
                    "tasks/evidence/evidence-review.md",
                    "tasks/evidence/evidence-review.json",
                ],
            },
            {
                "task_id": "solution",
                "title": "Develop the implementation or solution",
                "objective": (
                    "Produce the strongest practical implementation, design, "
                    "or work product for the mission."
                ),
                "kind": "implementation",
                "depends_on": ["interpret"],
                "priority": 80,
                "reasoning_rounds": 3,
                "timeout_seconds": 7200,
                "required_artifacts": [
                    "tasks/solution/solution.md",
                    "tasks/solution/solution.json",
                ],
            },
            {
                "task_id": "deliverables",
                "title": "Create requested deliverables",
                "objective": (
                    "Convert the evidence and solution into polished user-facing "
                    "deliverables without unsupported claims."
                ),
                "kind": "artifact",
                "depends_on": ["evidence", "solution"],
                "priority": 60,
                "reasoning_rounds": 2,
                "required_artifacts": paths,
            },
            {
                "task_id": "red-team",
                "title": "Red-team and quality review",
                "objective": (
                    "Challenge the work for logical gaps, unsafe assumptions, "
                    "missing evidence, usability defects, and incomplete outputs."
                ),
                "kind": "review",
                "depends_on": ["deliverables"],
                "priority": 50,
                "reasoning_rounds": 3,
                "max_attempts": 2,
                "payload": {"fail_on_blockers": False},
                "required_artifacts": [
                    "tasks/red-team/review.md",
                    "tasks/red-team/review.json",
                ],
            },
            {
                "task_id": "synthesize",
                "title": "Synthesize final answer and handoff",
                "objective": (
                    "Reconcile the solution and red-team findings into a final, "
                    "coherent result with explicit next actions."
                ),
                "kind": "synthesis",
                "depends_on": ["red-team"],
                "priority": 40,
                "reasoning_rounds": 2,
                "required_artifacts": [
                    "FINAL_RESULT.md",
                    "FINAL_RESULT.json",
                ],
            },
            {
                "task_id": "package",
                "title": "Package artifacts and receipts",
                "objective": (
                    "Create the final content manifest and downloadable mission bundle."
                ),
                "kind": "package",
                "depends_on": ["synthesize"],
                "priority": 10,
                "model_lane": "deterministic-packager",
                "reasoning_rounds": 1,
                "max_attempts": 2,
                "timeout_seconds": 900,
                "required_artifacts": [
                    "ARTIFACT_MANIFEST.json",
                    "mission-artifacts.zip",
                ],
            },
        ]


class PackageTaskExecutor:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def execute(
        self,
        mission: Mapping[str, Any],
        task: Mapping[str, Any],
        dependency_results: Sequence[Mapping[str, Any]],
        progress: Callable[[float, str], None] | None = None,
    ) -> TaskExecutionResult:
        mission_id = str(mission["mission_id"])
        if progress:
            progress(0.25, "building artifact manifest")
        manifest_record, bundle_record, manifest = self.artifacts.build_bundle(
            mission_id,
            task_id=str(task["task_id"]),
        )
        if progress:
            progress(0.95, "artifact bundle complete")
        return TaskExecutionResult(
            summary="Packaged all mission outputs.",
            output={
                "manifest": manifest,
                "bundle": bundle_record.to_dict(),
            },
            artifacts=(manifest_record, bundle_record),
            decision={
                "summary": "Packaged all mission outputs.",
                "options": [],
                "decision": "Deliver the generated ZIP and manifest.",
                "evidence": [
                    "manifest:" + manifest["manifest_sha256"],
                    "bundle:" + bundle_record.sha256,
                ],
                "confidence": 1.0,
                "blockers": [],
                "private_chain_of_thought_exported": False,
            },
            metrics={
                "artifact_count": manifest["artifact_count"],
                "bundle_bytes": bundle_record.bytes,
            },
            evidence=(
                "manifest:" + manifest["manifest_sha256"],
                "bundle:" + bundle_record.sha256,
            ),
        )


class MissionOrchestrator:
    """Create and execute durable mission DAGs in resumable bursts."""

    def __init__(
        self,
        store: MissionStore,
        artifacts: ArtifactStore,
        executors: Mapping[str, TaskExecutor],
        *,
        planner: MissionPlanner | None = None,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.executors = dict(executors)
        self.planner = planner or MissionPlanner()

    def create(self, **request: Any) -> dict[str, Any]:
        return self.store.create_mission(self.planner.plan(**request))

    def run_burst(
        self,
        mission_id: str,
        *,
        worker_id: str,
        max_tasks: int = 20,
        time_budget_seconds: int = 300,
        capabilities: Sequence[str] = (),
    ) -> dict[str, Any]:
        started = time.monotonic()
        executed = 0
        failures = 0
        maximum = max(1, min(int(max_tasks), 500))
        stop_reason = "idle-or-budget-exhausted"

        while executed < maximum:
            mission = self.store.get_mission(
                mission_id,
                include_events=False,
            )
            if mission["status"] in {
                "completed",
                "failed",
                "cancelled",
                "paused",
            }:
                stop_reason = "mission-terminal"
                break
            budget = dict(mission.get("budget") or {})
            age = int(time.time()) - int(mission["created_at_unix"])
            attempts = sum(
                int(task.get("attempts", 0)) for task in mission["tasks"]
            )
            artifact_bytes = sum(
                int(item.get("bytes", 0)) for item in mission["artifacts"]
            )
            if age >= int(budget.get("max_runtime_seconds", 86_400)):
                stop_reason = "mission-runtime-budget-exhausted"
                break
            if attempts >= int(budget.get("max_task_attempts", 256)):
                stop_reason = "mission-attempt-budget-exhausted"
                break
            if artifact_bytes >= int(
                budget.get("max_artifact_bytes", 512 * 1024 * 1024)
            ):
                stop_reason = "mission-artifact-budget-exhausted"
                break
            elapsed = time.monotonic() - started
            if elapsed >= max(1, int(time_budget_seconds)):
                stop_reason = "burst-time-budget-exhausted"
                break

            concurrency = min(
                int(mission["max_parallel"]),
                maximum - executed,
            )
            leased: list[tuple[dict[str, Any], str]] = []
            for slot in range(max(1, concurrency)):
                owner = f"{worker_id}:{slot}"
                task = self.store.lease_ready_task(
                    owner,
                    mission_id=mission_id,
                    lease_seconds=86_400,
                    capabilities=capabilities,
                )
                if task is None:
                    break
                leased.append((task, owner))
            if not leased:
                break

            pool = ThreadPoolExecutor(max_workers=len(leased))
            futures: dict[
                Future[TaskExecutionResult],
                tuple[dict[str, Any], str],
            ] = {}
            try:
                for task, owner in leased:
                    dependencies = [
                        self.store.get_task(item)
                        for item in task.get("depends_on", [])
                    ]
                    snapshot = self.store.get_mission(
                        mission_id,
                        include_events=False,
                    )
                    executor = self.executors.get(str(task["kind"]))
                    if executor is None:
                        self.store.fail_task(
                            task["task_id"],
                            owner,
                            f"no executor for task kind {task['kind']}",
                            terminal=True,
                        )
                        failures += 1
                        executed += 1
                        continue

                    def heartbeat(
                        value: float,
                        note: str,
                        *,
                        task_id=task["task_id"],
                        lease_owner=owner,
                        timeout=task["timeout_seconds"],
                    ) -> None:
                        self.store.heartbeat(
                            task_id,
                            lease_owner,
                            progress=value,
                            lease_seconds=max(int(timeout) + 120, 900),
                            note=note,
                        )

                    future = pool.submit(
                        executor.execute,
                        snapshot,
                        task,
                        dependencies,
                        heartbeat,
                    )
                    futures[future] = (task, owner)

                for future in as_completed(futures):
                    task, owner = futures[future]
                    try:
                        result = future.result()
                        if result.accepted:
                            self.store.complete_task(
                                task["task_id"],
                                owner,
                                result.to_dict(),
                                artifacts=[
                                    item.to_dict()
                                    for item in result.artifacts
                                ],
                                decision=result.decision,
                            )
                        else:
                            self.store.fail_task(
                                task["task_id"],
                                owner,
                                "; ".join(result.blockers)
                                or "task acceptance failed",
                                terminal=True,
                            )
                            failures += 1
                    except Exception as exc:
                        try:
                            self.store.fail_task(
                                task["task_id"],
                                owner,
                                f"{type(exc).__name__}: {str(exc)[:2000]}",
                                retry_delay_seconds=30,
                            )
                        except PermissionError:
                            pass
                        failures += 1
                    executed += 1
                    if time.monotonic() - started >= max(
                        1, int(time_budget_seconds)
                    ):
                        stop_reason = "burst-time-budget-exhausted"
                        break
            finally:
                pool.shutdown(wait=True, cancel_futures=False)

        mission = self.store.get_mission(mission_id)
        if mission["status"] == "completed" and not mission.get(
            "result_summary"
        ):
            self.finalize(mission)
            mission = self.store.get_mission(mission_id)
        if mission["status"] in {
            "completed",
            "failed",
            "cancelled",
            "paused",
        }:
            stop_reason = "mission-terminal"
        return {
            "schema": "pocket.mission.run-burst.v1",
            "mission": mission,
            "tasks_executed": executed,
            "task_failures_or_retries": failures,
            "elapsed_ms": round(
                (time.monotonic() - started) * 1000,
                3,
            ),
            "stopped_because": stop_reason,
        }

    def finalize(self, mission: Mapping[str, Any]) -> None:
        synthesis = next(
            (
                task
                for task in mission.get("tasks", [])
                if task.get("payload", {}).get("local_task_id")
                == "synthesize"
                and task.get("result")
            ),
            None,
        )
        summary = "Mission completed."
        if synthesis:
            summary = str(
                (synthesis.get("result") or {}).get("summary") or summary
            )
        manifest = self.artifacts.manifest(str(mission["mission_id"]))
        self.store.set_result_summary(
            str(mission["mission_id"]),
            summary,
            manifest["manifest_sha256"],
        )

    def status(self) -> dict[str, Any]:
        return {
            "schema": "pocket.mission-orchestrator.status.v1",
            "database": str(self.store.path),
            "artifact_root": str(self.artifacts.root),
            "executors": sorted(self.executors),
            "features": [
                "dependency-aware-DAG",
                "mission-namespaced-task-identities",
                "parallel-ready-tasks",
                "mission-parallelism-enforced-in-SQL",
                "pause-resume-cancel",
                "lease-recovery",
                "bounded-retries",
                "budgets-and-deadlines",
                "multi-pass-reasoning-adapters",
                "decision-summaries-without-private-chain-of-thought",
                "content-addressed-artifacts",
                "artifact-manifest-and-ZIP",
            ],
        }
