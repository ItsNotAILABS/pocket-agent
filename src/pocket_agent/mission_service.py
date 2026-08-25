"""Tenant-bound service and environment factory for POCKET Agent missions.

POCKET Agent owns durable mission state. AURO remains an external reasoning
provider, and runtime-cell execution remains unavailable until an operator
registers an exact approval-bound executor.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Mapping

from .mission_artifacts import ArtifactStore
from .mission_executors import AuroCouncilClient, AuroCouncilTaskExecutor
from .mission_orchestrator import MissionOrchestrator, MissionPlanner, PackageTaskExecutor, TaskExecutor
from .mission_store import MissionStore

_ID = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")


class MissionAuthorizationError(PermissionError):
    pass


class MissionService:
    """Multi-tenant mission facade over the durable scheduler."""

    def __init__(
        self,
        *,
        store: MissionStore,
        artifacts: ArtifactStore,
        orchestrator: MissionOrchestrator,
        council_client: AuroCouncilClient | None = None,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.orchestrator = orchestrator
        self.council_client = council_client

    @classmethod
    def from_env(cls) -> "MissionService":
        store = MissionStore(
            os.getenv("POCKET_MISSION_DB", "state/pocket-agent-missions.sqlite3")
        )
        artifacts = ArtifactStore(
            os.getenv("POCKET_MISSION_ARTIFACT_ROOT", "state/mission-artifacts"),
            max_artifact_bytes=int(
                os.getenv(
                    "POCKET_MISSION_MAX_ARTIFACT_BYTES",
                    str(64 * 1024 * 1024),
                )
            ),
        )
        council_client = AuroCouncilClient(
            os.getenv(
                "AURO_COUNCIL_URL",
                "http://127.0.0.1:8090/v1/council/respond",
            ),
            api_token=os.getenv("AURO_API_TOKEN", ""),
            timeout_seconds=float(
                os.getenv("AURO_COUNCIL_TIMEOUT_SECONDS", "180")
            ),
        )
        council = AuroCouncilTaskExecutor(council_client, artifacts)
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
        return cls(
            store=store,
            artifacts=artifacts,
            orchestrator=orchestrator,
            council_client=council_client,
        )

    @staticmethod
    def identity(principal_id: str, tenant_id: str) -> tuple[str, str]:
        principal = str(principal_id).strip()
        tenant = str(tenant_id).strip()
        if not _ID.fullmatch(principal):
            raise MissionAuthorizationError("valid principal_id is required")
        if not _ID.fullmatch(tenant):
            raise MissionAuthorizationError("valid tenant_id is required")
        return principal, tenant

    def register_executor(self, kind: str, executor: TaskExecutor) -> None:
        normalized = str(kind).strip()
        if normalized not in MissionPlanner.KINDS:
            raise ValueError(f"unsupported mission task kind: {normalized}")
        self.orchestrator.executors[normalized] = executor

    def authorized(
        self,
        mission_id: str,
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        principal, tenant = self.identity(principal_id, tenant_id)
        mission = self.store.get_mission(mission_id)
        if mission["tenant_id"] != tenant:
            raise MissionAuthorizationError("mission belongs to another tenant")
        if mission["principal_id"] != principal and principal != "system-admin":
            raise MissionAuthorizationError("mission belongs to another principal")
        return mission

    def create(
        self,
        request: Mapping[str, Any],
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        principal, tenant = self.identity(principal_id, tenant_id)
        tasks = request.get("tasks")
        if tasks is not None and not isinstance(tasks, list):
            raise ValueError("tasks must be an array")
        deliverables = request.get("deliverables") or []
        if not isinstance(deliverables, list):
            raise ValueError("deliverables must be an array")
        return self.orchestrator.create(
            objective=str(request.get("objective") or ""),
            title=str(request.get("title") or "POCKET Agent mission"),
            tasks=tasks,
            deliverables=deliverables,
            principal_id=principal,
            tenant_id=tenant,
            max_parallel=int(request.get("max_parallel", 3)),
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

    def list(
        self,
        *,
        principal_id: str,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        principal, tenant = self.identity(principal_id, tenant_id)
        return self.store.list_missions(
            tenant_id=tenant,
            principal_id=None if principal == "system-admin" else principal,
            limit=limit,
        )

    def get(
        self,
        mission_id: str,
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        return self.authorized(
            mission_id,
            principal_id=principal_id,
            tenant_id=tenant_id,
        )

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
                request.get("worker_id") or f"mission:{principal_id}"
            ),
            max_tasks=int(request.get("max_tasks", 20)),
            time_budget_seconds=int(
                request.get("time_budget_seconds", 300)
            ),
            capabilities=[str(item) for item in capabilities],
        )

    def transition(
        self,
        mission_id: str,
        action: str,
        *,
        principal_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        self.authorized(
            mission_id,
            principal_id=principal_id,
            tenant_id=tenant_id,
        )
        handlers = {
            "pause": self.store.pause,
            "resume": self.store.resume,
            "cancel": self.store.cancel,
        }
        if action not in handlers:
            raise ValueError(f"unsupported mission action: {action}")
        return handlers[action](mission_id)

    def artifact_path(
        self,
        mission_id: str,
        relative_path: str,
        *,
        principal_id: str,
        tenant_id: str,
    ) -> Path:
        self.authorized(
            mission_id,
            principal_id=principal_id,
            tenant_id=tenant_id,
        )
        root = self.artifacts.mission_root(mission_id)
        candidate = (root / str(relative_path)).resolve()
        candidate.relative_to(root)
        if not candidate.is_file():
            raise FileNotFoundError(relative_path)
        return candidate

    def status(self) -> dict[str, Any]:
        client = self.council_client
        return {
            **self.orchestrator.status(),
            "multi_user": True,
            "tenant_isolation": "tenant-and-principal-bound",
            "long_running_mode": (
                "durable worker bursts with leases and restart recovery"
            ),
            "auro_council": {
                "client_configured": client is not None,
                "url": client.url if client else None,
                "api_token_configured": bool(client and client.api_token),
                "endpoint_ready": None,
                "claim_boundary": (
                    "client configuration does not prove endpoint readiness, "
                    "model identity, or checkpoint quality"
                ),
            },
            "execution_executor_registered": (
                "execution" in self.orchestrator.executors
            ),
            "execution_tasks": (
                "require a registered RuntimeCellTaskExecutor and an exact, "
                "one-time approval token"
            ),
        }
