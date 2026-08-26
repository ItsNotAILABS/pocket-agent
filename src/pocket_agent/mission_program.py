"""Multi-workstream, long-running mission programs for POCKET Agent.

A program turns one or more objectives into a namespaced dependency graph.
Independent workstreams run concurrently, each may pass through repeated review
and revision cycles, and the complete mission converges through integration,
global review, final validation, deliverable rendering, and packaging.

The program records bounded decision summaries and evidence references. It does
not request, store, or expose private chain-of-thought.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import time
import uuid
from typing import Any, Mapping, Sequence

from .mission_artifacts import ArtifactStore, UnsupportedArtifactFormat
from .mission_executors import AuroCouncilClient, AuroCouncilTaskExecutor
from .mission_orchestrator import (
    MissionOrchestrator,
    PackageTaskExecutor,
    TaskExecutionResult,
)
from .mission_profiles import (
    DeliverableContract,
    ReasoningProfile,
    WorkstreamSpec,
    normalize_deliverables,
    normalize_workstreams,
    reasoning_profile,
)
from .mission_renderers import ArtifactRendererRegistry
from .mission_service import MissionAuthorizationError
from .mission_store import MissionStore


PROGRAM_SCHEMA = "pocket.mission.program.v2"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _task_id(namespace: str, *parts: str) -> str:
    raw = "__".join([namespace, *parts])
    clean = "".join(
        character if character.isalnum() or character in "_-" else "-"
        for character in raw
    ).strip("-_")
    return clean[:120]


@dataclass(frozen=True)
class MissionProgram:
    mission_id: str
    title: str
    objective: str
    principal_id: str
    tenant_id: str
    reasoning_profile: Mapping[str, Any]
    workstreams: tuple[Mapping[str, Any], ...]
    deliverables: tuple[Mapping[str, Any], ...]
    tasks: tuple[Mapping[str, Any], ...]
    max_parallel: int
    budget: Mapping[str, Any]
    deadline_unix: int | None
    idempotency_key: str | None
    plan_sha256: str
    schema: str = PROGRAM_SCHEMA

    def to_store_spec(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "idempotency_key": self.idempotency_key,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "title": self.title,
            "objective": self.objective,
            "max_parallel": self.max_parallel,
            "budget": dict(self.budget),
            "deadline_unix": self.deadline_unix,
            "tasks": [dict(item) for item in self.tasks],
            "reasoning_policy": {
                "profile": dict(self.reasoning_profile),
                "private_chain_of_thought_exported": False,
                "decision_summaries_recorded": True,
                "independent_review_and_revision": True,
                "artifact_delivery_required": True,
            },
            "workstreams": [dict(item) for item in self.workstreams],
            "deliverables": [dict(item) for item in self.deliverables],
            "plan_sha256": self.plan_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "reasoning_profile": dict(self.reasoning_profile),
            "workstreams": [dict(item) for item in self.workstreams],
            "deliverables": [dict(item) for item in self.deliverables],
            "tasks": [dict(item) for item in self.tasks],
            "budget": dict(self.budget),
        }


class MissionProgramPlanner:
    """Compile multiple objectives into a bounded, revision-capable task DAG."""

    def plan(
        self,
        *,
        objectives: Sequence[str | Mapping[str, Any] | WorkstreamSpec],
        title: str = "POCKET Agent mission program",
        objective: str | None = None,
        deliverables: Sequence[
            str | Mapping[str, Any] | DeliverableContract
        ] = (),
        profile: str | Mapping[str, Any] | ReasoningProfile | None = "standard",
        principal_id: str = "anonymous",
        tenant_id: str = "default",
        max_parallel: int | None = None,
        budget: Mapping[str, Any] | None = None,
        deadline_unix: int | None = None,
        idempotency_key: str | None = None,
        mission_id: str | None = None,
    ) -> MissionProgram:
        streams = normalize_workstreams(objectives)
        global_deliverables = normalize_deliverables(deliverables)
        selected_profile = reasoning_profile(profile)
        mission_id = mission_id or "mission_" + uuid.uuid4().hex
        namespace = "m" + mission_id.replace("mission_", "")[-12:]
        combined_objective = str(
            objective
            or "Coordinate and complete the supplied workstreams with evidence, review, artifacts, and a final integrated result."
        ).strip()
        if not combined_objective:
            raise ValueError("program objective is required")

        tasks = self._tasks(
            namespace,
            streams,
            global_deliverables,
            selected_profile,
        )
        caller_budget = dict(budget or {})
        requested_task_limit = int(
            caller_budget.get("max_tasks", selected_profile.max_tasks)
        )
        maximum_tasks = min(requested_task_limit, selected_profile.max_tasks)
        if len(tasks) > maximum_tasks:
            raise ValueError(
                f"program requires {len(tasks)} tasks but profile/budget permits {maximum_tasks}"
            )
        actual_parallel = (
            selected_profile.max_parallel
            if max_parallel is None
            else max(1, min(int(max_parallel), selected_profile.max_parallel, 32))
        )
        actual_budget = {
            "max_tasks": maximum_tasks,
            "max_task_attempts": max(
                len(tasks) * 3,
                int(caller_budget.get("max_task_attempts", len(tasks) * 3)),
            ),
            "max_runtime_seconds": max(
                0,
                int(caller_budget.get("max_runtime_seconds", 0)),
            ),
            "reasoning_profile": selected_profile.name,
            "workstream_count": len(streams),
            "revision_cycles": selected_profile.revision_cycles,
            **{
                key: value
                for key, value in caller_budget.items()
                if key
                not in {
                    "max_tasks",
                    "max_task_attempts",
                    "max_runtime_seconds",
                    "reasoning_profile",
                    "workstream_count",
                    "revision_cycles",
                }
            },
        }
        material = {
            "mission_id": mission_id,
            "title": title,
            "objective": combined_objective,
            "principal_id": principal_id,
            "tenant_id": tenant_id,
            "reasoning_profile": selected_profile.to_dict(),
            "workstreams": [item.to_dict() for item in streams],
            "deliverables": [item.to_dict() for item in global_deliverables],
            "tasks": tasks,
            "max_parallel": actual_parallel,
            "budget": actual_budget,
            "deadline_unix": deadline_unix,
            "idempotency_key": idempotency_key,
        }
        return MissionProgram(
            mission_id=mission_id,
            title=str(title)[:300],
            objective=combined_objective,
            principal_id=str(principal_id),
            tenant_id=str(tenant_id),
            reasoning_profile=selected_profile.to_dict(),
            workstreams=tuple(item.to_dict() for item in streams),
            deliverables=tuple(item.to_dict() for item in global_deliverables),
            tasks=tuple(tasks),
            max_parallel=actual_parallel,
            budget=actual_budget,
            deadline_unix=deadline_unix,
            idempotency_key=idempotency_key,
            plan_sha256=_digest(material),
        )

    def _tasks(
        self,
        namespace: str,
        streams: Sequence[WorkstreamSpec],
        global_deliverables: Sequence[DeliverableContract],
        profile: ReasoningProfile,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        final_by_stream: list[str] = []
        evidence_by_stream: list[str] = []

        for stream in streams:
            prefix = stream.workstream_id
            interpret_id = _task_id(namespace, prefix, "interpret")
            evidence_id = _task_id(namespace, prefix, "evidence")
            solution_id = _task_id(namespace, prefix, "solution")
            tasks.extend(
                [
                    self._task(
                        interpret_id,
                        f"Interpret: {stream.title}",
                        (
                            f"Resolve scope, assumptions, constraints, unknowns, and testable "
                            f"success criteria for this workstream: {stream.objective}\n"
                            f"Context: {stream.context or '[none supplied]'}"
                        ),
                        "reasoning",
                        [],
                        100 + stream.priority,
                        profile.interpretation_rounds,
                        profile.default_timeout_seconds,
                        [
                            f"workstreams/{prefix}/interpretation.md",
                            f"workstreams/{prefix}/interpretation.json",
                        ],
                        stream,
                        phase="interpretation",
                    ),
                    self._task(
                        evidence_id,
                        f"Evidence: {stream.title}",
                        (
                            "Collect, compare, and evaluate the strongest available evidence, "
                            "contradictions, uncertainties, and missing validation for the workstream."
                        ),
                        "research",
                        [interpret_id],
                        90 + stream.priority,
                        profile.evidence_rounds,
                        profile.default_timeout_seconds,
                        [
                            f"workstreams/{prefix}/evidence.md",
                            f"workstreams/{prefix}/evidence.json",
                        ],
                        stream,
                        phase="evidence",
                    ),
                    self._task(
                        solution_id,
                        f"Solution: {stream.title}",
                        (
                            "Develop the strongest practical implementation, analysis, or work "
                            "product for this workstream. Specify interfaces, failure behavior, "
                            "verification, and remaining uncertainty."
                        ),
                        "implementation",
                        [interpret_id],
                        90 + stream.priority,
                        profile.solution_rounds,
                        profile.default_timeout_seconds,
                        [
                            f"workstreams/{prefix}/solution.md",
                            f"workstreams/{prefix}/solution.json",
                        ],
                        stream,
                        phase="solution",
                    ),
                ]
            )
            evidence_by_stream.append(evidence_id)
            current_dependencies = [evidence_id, solution_id]

            for cycle in range(1, profile.revision_cycles + 1):
                review_ids: list[str] = []
                for reviewer in range(1, profile.independent_reviewers + 1):
                    review_id = _task_id(
                        namespace,
                        prefix,
                        f"review-{cycle}-{reviewer}",
                    )
                    review_ids.append(review_id)
                    tasks.append(
                        self._task(
                            review_id,
                            f"Independent review {reviewer}, cycle {cycle}: {stream.title}",
                            (
                                "Independently red-team the workstream for correctness, evidence, "
                                "security, usability, hidden assumptions, incomplete artifacts, and "
                                "alternative solutions. Prioritize defects and specify corrections."
                            ),
                            "review",
                            list(current_dependencies),
                            70 - cycle,
                            profile.review_rounds,
                            profile.default_timeout_seconds,
                            [
                                f"workstreams/{prefix}/reviews/cycle-{cycle}-review-{reviewer}.md",
                                f"workstreams/{prefix}/reviews/cycle-{cycle}-review-{reviewer}.json",
                            ],
                            stream,
                            phase="review",
                            revision_cycle=cycle,
                            reviewer=reviewer,
                            fail_on_blockers=False,
                        )
                    )
                revise_id = _task_id(namespace, prefix, f"revise-{cycle}")
                tasks.append(
                    self._task(
                        revise_id,
                        f"Revision cycle {cycle}: {stream.title}",
                        (
                            "Reconcile all independent reviews, correct confirmed defects, compare "
                            "alternatives, preserve unresolved disagreement, and produce the improved "
                            "workstream result."
                        ),
                        "implementation",
                        review_ids,
                        60 - cycle,
                        profile.revision_rounds,
                        profile.default_timeout_seconds,
                        [
                            f"workstreams/{prefix}/revisions/cycle-{cycle}.md",
                            f"workstreams/{prefix}/revisions/cycle-{cycle}.json",
                        ],
                        stream,
                        phase="revision",
                        revision_cycle=cycle,
                    )
                )
                current_dependencies = [revise_id]

            validate_id = _task_id(namespace, prefix, "validate")
            tasks.append(
                self._task(
                    validate_id,
                    f"Validate: {stream.title}",
                    (
                        "Validate the final workstream against its acceptance criteria. Distinguish "
                        "passed criteria, failed criteria, missing evidence, and residual risks."
                    ),
                    "review",
                    list(current_dependencies),
                    50,
                    profile.review_rounds,
                    profile.default_timeout_seconds,
                    [
                        f"workstreams/{prefix}/validation.md",
                        f"workstreams/{prefix}/validation.json",
                    ],
                    stream,
                    phase="validation",
                    fail_on_blockers=True,
                )
            )
            final_by_stream.append(validate_id)

            if stream.deliverables:
                deliver_id = _task_id(namespace, prefix, "deliver")
                tasks.append(
                    self._artifact_task(
                        deliver_id,
                        f"Render workstream deliverables: {stream.title}",
                        "Render the accepted workstream result into every contracted artifact.",
                        [validate_id],
                        45,
                        profile.synthesis_rounds,
                        profile.default_timeout_seconds,
                        stream.deliverables,
                        phase="workstream-deliverables",
                        workstream=stream,
                    )
                )
                final_by_stream[-1] = deliver_id

        cross_evidence_id = _task_id(namespace, "global", "cross-evidence")
        integrate_id = _task_id(namespace, "global", "integrate")
        tasks.append(
            self._task(
                cross_evidence_id,
                "Cross-workstream evidence synthesis",
                (
                    "Compare evidence across all workstreams, detect contradictions and shared "
                    "dependencies, identify conclusions that transfer, and preserve conflicts that "
                    "cannot be resolved from available evidence."
                ),
                "research",
                evidence_by_stream,
                40,
                profile.evidence_rounds,
                profile.default_timeout_seconds,
                ["integration/cross-evidence.md", "integration/cross-evidence.json"],
                None,
                phase="cross-evidence",
            )
        )
        tasks.append(
            self._task(
                integrate_id,
                "Integrate all workstreams",
                (
                    "Integrate the validated workstreams into one coherent system or delivery. "
                    "Resolve interface conflicts, order implementation, consolidate evidence, and "
                    "define a unified result without erasing workstream-specific caveats."
                ),
                "synthesis",
                [*final_by_stream, cross_evidence_id],
                35,
                profile.synthesis_rounds,
                profile.default_timeout_seconds,
                ["integration/integrated-result.md", "integration/integrated-result.json"],
                None,
                phase="integration",
            )
        )

        global_reviews: list[str] = []
        for reviewer in range(1, profile.independent_reviewers + 1):
            review_id = _task_id(namespace, "global", f"review-{reviewer}")
            global_reviews.append(review_id)
            tasks.append(
                self._task(
                    review_id,
                    f"Global independent review {reviewer}",
                    (
                        "Red-team the integrated mission for completeness, cross-workstream "
                        "contradictions, unsafe assumptions, evidence gaps, artifact failures, and "
                        "unaddressed user requirements."
                    ),
                    "review",
                    [integrate_id],
                    30,
                    profile.review_rounds,
                    profile.default_timeout_seconds,
                    [
                        f"integration/reviews/global-review-{reviewer}.md",
                        f"integration/reviews/global-review-{reviewer}.json",
                    ],
                    None,
                    phase="global-review",
                    reviewer=reviewer,
                    fail_on_blockers=False,
                )
            )

        final_revision_id = _task_id(namespace, "global", "final-revision")
        final_validation_id = _task_id(namespace, "global", "final-validation")
        tasks.extend(
            [
                self._task(
                    final_revision_id,
                    "Final integrated revision",
                    (
                        "Resolve the global review findings, correct defects, retain unresolved "
                        "uncertainty, and produce the final integrated content for delivery."
                    ),
                    "synthesis",
                    global_reviews,
                    20,
                    profile.revision_rounds,
                    profile.default_timeout_seconds,
                    ["FINAL_RESULT.md", "FINAL_RESULT.json"],
                    None,
                    phase="final-revision",
                ),
                self._task(
                    final_validation_id,
                    "Final acceptance validation",
                    (
                        "Validate the integrated result and every required deliverable contract. "
                        "List passed criteria, failed criteria, missing evidence, blockers, and "
                        "whether the mission is acceptable for delivery."
                    ),
                    "review",
                    [final_revision_id],
                    15,
                    profile.review_rounds,
                    profile.default_timeout_seconds,
                    [
                        "FINAL_VALIDATION.md",
                        "FINAL_VALIDATION.json",
                    ],
                    None,
                    phase="final-validation",
                    fail_on_blockers=True,
                ),
            ]
        )

        deliver_id = _task_id(namespace, "global", "deliverables")
        package_id = _task_id(namespace, "global", "package")
        required = list(global_deliverables) or [
            DeliverableContract("deliverables/mission-report.md", "Mission Report"),
            DeliverableContract("deliverables/mission-report.json", "Mission Report Data"),
        ]
        tasks.append(
            self._artifact_task(
                deliver_id,
                "Render final contracted deliverables",
                "Render the validated integrated result into every required output contract.",
                [final_validation_id],
                10,
                profile.synthesis_rounds,
                profile.default_timeout_seconds,
                required,
                phase="final-deliverables",
            )
        )
        tasks.append(
            {
                "task_id": package_id,
                "title": "Package mission artifacts and receipts",
                "objective": (
                    "Produce ARTIFACT_MANIFEST.json and mission-artifacts.zip containing the "
                    "complete mission output without including the ZIP inside itself."
                ),
                "kind": "package",
                "depends_on": [deliver_id],
                "priority": 0,
                "model_lane": "deterministic-packager",
                "reasoning_rounds": 1,
                "max_attempts": 3,
                "timeout_seconds": 900,
                "payload": {
                    "phase": "package",
                    "reasoning_profile": profile.name,
                },
                "acceptance_criteria": [
                    "artifact manifest exists",
                    "bundle exists",
                    "every packaged file is hash-addressed",
                ],
                "required_artifacts": [
                    "ARTIFACT_MANIFEST.json",
                    "mission-artifacts.zip",
                ],
            }
        )
        return tasks

    @staticmethod
    def _task(
        task_id: str,
        title: str,
        objective: str,
        kind: str,
        depends_on: Sequence[str],
        priority: int,
        rounds: int,
        timeout_seconds: int,
        required_artifacts: Sequence[str],
        workstream: WorkstreamSpec | None,
        **payload: Any,
    ) -> dict[str, Any]:
        acceptance = list(workstream.acceptance_criteria) if workstream else []
        if not acceptance:
            acceptance = [
                "result directly addresses the task objective",
                "evidence and uncertainty are explicit",
                "remaining blockers are visible",
            ]
        return {
            "task_id": task_id,
            "title": title,
            "objective": objective,
            "kind": kind,
            "depends_on": list(depends_on),
            "priority": int(priority),
            "model_lane": "auro-2b-council",
            "reasoning_rounds": max(1, min(int(rounds), 12)),
            "max_attempts": 4,
            "timeout_seconds": max(30, min(int(timeout_seconds), 86_400)),
            "payload": {
                **payload,
                "workstream_id": workstream.workstream_id if workstream else None,
                "workstream_metadata": dict(workstream.metadata) if workstream else {},
            },
            "acceptance_criteria": acceptance,
            "required_artifacts": list(required_artifacts),
        }

    @staticmethod
    def _artifact_task(
        task_id: str,
        title: str,
        objective: str,
        depends_on: Sequence[str],
        priority: int,
        rounds: int,
        timeout_seconds: int,
        deliverables: Sequence[DeliverableContract],
        **payload: Any,
    ) -> dict[str, Any]:
        contracts = [item.to_dict() for item in deliverables]
        return {
            "task_id": task_id,
            "title": title,
            "objective": objective,
            "kind": "artifact",
            "depends_on": list(depends_on),
            "priority": int(priority),
            "model_lane": "auro-2b-council+artifact-renderers",
            "reasoning_rounds": max(1, min(int(rounds), 12)),
            "max_attempts": 4,
            "timeout_seconds": max(30, min(int(timeout_seconds), 86_400)),
            "payload": {
                **payload,
                "deliverable_contracts": contracts,
            },
            "acceptance_criteria": [
                "all required deliverable contracts are rendered",
                "every artifact meets its minimum byte and media-type checks",
                "artifact hashes and renderer receipts are recorded",
            ],
            "required_artifacts": [item.path for item in deliverables if item.required],
        }


class ContractArtifactExecutor:
    """Use the council for content, then real registered renderers for files."""

    def __init__(
        self,
        council: AuroCouncilTaskExecutor,
        artifacts: ArtifactStore,
        renderers: ArtifactRendererRegistry,
    ) -> None:
        self.council = council
        self.artifacts = artifacts
        self.renderers = renderers

    def execute(
        self,
        mission: Mapping[str, Any],
        task: Mapping[str, Any],
        dependency_results: Sequence[Mapping[str, Any]],
        progress=None,
    ) -> TaskExecutionResult:
        content_task = dict(task)
        content_task["required_artifacts"] = []
        base = self.council.execute(
            mission,
            content_task,
            dependency_results,
            progress,
        )
        source = {
            "text": base.summary,
            **dict(base.output),
            "mission": {
                "mission_id": mission.get("mission_id"),
                "title": mission.get("title"),
                "objective": mission.get("objective"),
            },
            "task": {
                "task_id": task.get("task_id"),
                "title": task.get("title"),
                "objective": task.get("objective"),
            },
        }
        contracts = [
            DeliverableContract.from_value(item)
            for item in task.get("payload", {}).get("deliverable_contracts", [])
        ]
        records = list(base.artifacts)
        receipts: list[dict[str, Any]] = []
        blockers = list(base.blockers)
        for contract in contracts:
            try:
                record, receipt = self.renderers.render_to_store(
                    self.artifacts,
                    str(mission["mission_id"]),
                    str(task["task_id"]),
                    contract,
                    source,
                )
                records.append(record)
                receipts.append(receipt)
            except (UnsupportedArtifactFormat, ValueError, TypeError) as exc:
                if contract.required:
                    blockers.append(f"{contract.path}: {type(exc).__name__}: {exc}")
        produced = {item.relative_path for item in records}
        required = {item.path for item in contracts if item.required}
        missing = sorted(required - produced)
        blockers.extend(f"missing required deliverable: {item}" for item in missing)
        output = {
            **dict(base.output),
            "deliverable_receipts": receipts,
            "required_deliverables": sorted(required),
            "produced_deliverables": sorted(produced & required),
            "missing_deliverables": missing,
            "renderer_registry": self.renderers.manifest(),
        }
        accepted = base.accepted and not blockers
        return TaskExecutionResult(
            summary=base.summary,
            output=output,
            artifacts=tuple(records),
            decision={
                **dict(base.decision),
                "blockers": list(blockers),
            },
            metrics={
                **dict(base.metrics),
                "deliverable_contracts": len(contracts),
                "deliverables_rendered": len(receipts),
            },
            evidence=tuple(
                dict.fromkeys(
                    [
                        *base.evidence,
                        *(
                            "artifact:" + item.sha256
                            for item in records
                            if item.relative_path in required
                        ),
                    ]
                )
            ),
            blockers=tuple(blockers),
            accepted=accepted,
        )


class MissionProgramService:
    """Tenant-bound service that owns durable mission programs."""

    def __init__(
        self,
        *,
        store: MissionStore,
        artifacts: ArtifactStore,
        orchestrator: MissionOrchestrator,
        planner: MissionProgramPlanner | None = None,
        renderers: ArtifactRendererRegistry | None = None,
        council_client: AuroCouncilClient | None = None,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.orchestrator = orchestrator
        self.planner = planner or MissionProgramPlanner()
        self.renderers = renderers or ArtifactRendererRegistry()
        self.council_client = council_client

    @classmethod
    def from_env(
        cls,
        *,
        renderers: ArtifactRendererRegistry | None = None,
    ) -> "MissionProgramService":
        import os

        store = MissionStore(
            os.getenv(
                "POCKET_MISSION_DB",
                "state/pocket-agent-missions.sqlite3",
            )
        )
        artifacts = ArtifactStore(
            os.getenv(
                "POCKET_MISSION_ARTIFACT_ROOT",
                "state/mission-artifacts",
            ),
            max_artifact_bytes=int(
                os.getenv(
                    "POCKET_MISSION_MAX_ARTIFACT_BYTES",
                    str(64 * 1024 * 1024),
                )
            ),
        )
        client = AuroCouncilClient(
            os.getenv(
                "AURO_COUNCIL_URL",
                "http://127.0.0.1:8090/v1/council/respond",
            ),
            api_token=os.getenv("AURO_API_TOKEN", ""),
            timeout_seconds=float(
                os.getenv("AURO_COUNCIL_TIMEOUT_SECONDS", "180")
            ),
        )
        council = AuroCouncilTaskExecutor(client, artifacts)
        registry = renderers or ArtifactRendererRegistry()
        artifact_executor = ContractArtifactExecutor(
            council,
            artifacts,
            registry,
        )
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
        return cls(
            store=store,
            artifacts=artifacts,
            orchestrator=orchestrator,
            renderers=registry,
            council_client=client,
        )

    @staticmethod
    def _identity(principal_id: str, tenant_id: str) -> tuple[str, str]:
        # Reuse the existing service's strict identity validation without
        # instantiating another database or orchestrator.
        from .mission_service import MissionService

        return MissionService.identity(principal_id, tenant_id)

    def create_program(
        self,
        request: Mapping[str, Any],
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        principal, tenant = self._identity(principal_id, tenant_id)
        values = request.get("objectives") or request.get("workstreams")
        if not isinstance(values, list) or not values:
            raise ValueError("objectives or workstreams must be a non-empty array")
        deliverables = request.get("deliverables") or []
        if not isinstance(deliverables, list):
            raise ValueError("deliverables must be an array")
        program = self.planner.plan(
            objectives=values,
            title=str(request.get("title") or "POCKET Agent mission program"),
            objective=(
                str(request.get("objective"))
                if request.get("objective") is not None
                else None
            ),
            deliverables=deliverables,
            profile=request.get("reasoning_profile") or request.get("profile") or "standard",
            principal_id=principal,
            tenant_id=tenant,
            max_parallel=(
                int(request["max_parallel"])
                if request.get("max_parallel") is not None
                else None
            ),
            budget=dict(request.get("budget") or {}),
            deadline_unix=(
                int(request["deadline_unix"])
                if request.get("deadline_unix") is not None
                else None
            ),
            idempotency_key=(
                str(request.get("idempotency_key") or "").strip() or None
            ),
        )
        created = self.store.create_mission(program.to_store_spec())
        return {
            "schema": "pocket.mission.program-created.v2",
            "program": program.to_dict(),
            "mission": created,
        }

    def authorized(
        self,
        mission_id: str,
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        principal, tenant = self._identity(principal_id, tenant_id)
        mission = self.store.get_mission(mission_id)
        if mission["tenant_id"] != tenant:
            raise MissionAuthorizationError("mission belongs to another tenant")
        if mission["principal_id"] != principal and principal != "system-admin":
            raise MissionAuthorizationError("mission belongs to another principal")
        return mission

    def run(
        self,
        mission_id: str,
        request: Mapping[str, Any],
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        self.authorized(
            mission_id,
            principal_id=principal_id,
            tenant_id=tenant_id,
        )
        capabilities = request.get("capabilities") or []
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be an array")
        return self.orchestrator.run_burst(
            mission_id,
            worker_id=str(
                request.get("worker_id")
                or f"mission-program:{tenant_id}:{principal_id}"
            ),
            max_tasks=int(request.get("max_tasks", 50)),
            time_budget_seconds=int(
                request.get("time_budget_seconds", 900)
            ),
            capabilities=[str(item) for item in capabilities],
        )

    def status(self) -> dict[str, Any]:
        return {
            "schema": "pocket.mission-program.service-status.v2",
            "orchestrator": self.orchestrator.status(),
            "reasoning_profiles": {
                name: value.to_dict()
                for name, value in reasoning_profile.__globals__["REASONING_PROFILES"].items()
            },
            "renderers": self.renderers.manifest(),
            "council_client": (
                self.council_client.status()
                if self.council_client is not None
                else None
            ),
            "multi_workstream": True,
            "long_running": "durable bursts plus worker loop",
            "private_chain_of_thought_exported": False,
            "claim_boundary": (
                "source readiness does not prove an always-running worker, a live AURO endpoint, "
                "semantic artifact correctness, or production deployment"
            ),
        }
