"""Stable public facade for POCKET Agent mission programs."""
from __future__ import annotations

from typing import Any

from .mission_auth import (
    MissionApiKeyRegistry,
    MissionIdentityGrant,
    key_registry_document,
    token_sha256,
)
from .mission_profiles import (
    DeliverableContract,
    ReasoningProfile,
    WorkstreamSpec,
    REASONING_PROFILES,
    reasoning_profile,
)
from .mission_program import (
    ContractArtifactExecutor,
    MissionProgram,
    MissionProgramPlanner,
    MissionProgramService,
)
from .mission_renderers import (
    ArtifactRendererRegistry,
    RenderedArtifact,
    callable_binary_renderer,
)
from .mission_worker import MissionWorker, WorkerConfig


MISSION_API_VERSION = "2.0.0"


def capability_descriptor() -> dict[str, Any]:
    return {
        "schema": "nexus.capability.v1",
        "component": "pocket-agent-missions",
        "version": MISSION_API_VERSION,
        "role": "durable-multi-workstream-mission-execution",
        "actions": [
            "mission.plan",
            "mission.create",
            "mission.read",
            "mission.run_burst",
            "mission.pause",
            "mission.resume",
            "mission.cancel",
            "mission.artifacts.list",
            "mission.artifacts.download",
            "mission.worker.status",
        ],
        "risk_tiers": {
            "mission.plan": "read-compute",
            "mission.create": "reversible-write",
            "mission.read": "read",
            "mission.run_burst": "governed-compute",
            "mission.pause": "reversible-write",
            "mission.resume": "reversible-write",
            "mission.cancel": "consequential-write",
            "mission.artifacts.list": "read",
            "mission.artifacts.download": "read",
            "mission.worker.status": "read",
        },
        "produces": [
            "nexus.job.v1",
            "nexus.task.v1",
            "nexus.execution-receipt.v1",
            "nexus.artifact.v1",
            "nexus.audit-event.v1",
            "nexus.health.v1",
        ],
        "consumes": [
            "nexus.identity-ref.v1",
            "nexus.policy-decision.v1",
            "nexus.approval.v1",
            "nexus.budget.v1",
            "nexus.context-pack.v1",
            "nexus.capability.v1",
        ],
        "reasoning_profiles": {
            name: profile.to_dict()
            for name, profile in REASONING_PROFILES.items()
        },
        "runtime": {
            "state": "SQLite/WAL",
            "workers": "bounded durable bursts",
            "parallel_workstreams": True,
            "review_and_revision": True,
            "artifact_manifest_and_zip": True,
            "binary_artifacts_require_real_renderer": True,
        },
        "limits": {
            "private_chain_of_thought_export": False,
            "self_approval": False,
            "cross_tenant_access": False,
            "fake_binary_artifacts": False,
            "unbounded_dynamic_task_creation": False,
            "mission_completion_without_all_tasks": False,
        },
        "claim_boundary": (
            "capability source and tests do not prove a continuously supervised worker, "
            "live AURO reasoning, semantic artifact quality, production deployment, "
            "or external evidence custody"
        ),
    }


__all__ = [
    "ArtifactRendererRegistry",
    "ContractArtifactExecutor",
    "DeliverableContract",
    "MISSION_API_VERSION",
    "MissionApiKeyRegistry",
    "MissionIdentityGrant",
    "MissionProgram",
    "MissionProgramPlanner",
    "MissionProgramService",
    "MissionWorker",
    "REASONING_PROFILES",
    "ReasoningProfile",
    "RenderedArtifact",
    "WorkerConfig",
    "WorkstreamSpec",
    "callable_binary_renderer",
    "capability_descriptor",
    "key_registry_document",
    "reasoning_profile",
    "token_sha256",
]
