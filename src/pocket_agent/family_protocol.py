"""Provider-neutral POCKET family execution envelopes and receipts.

The wire representation follows the canonical POCKET Host schemas:
`pocket.family.v1` and `pocket.execution-receipt.v1`.

Operational receipts intentionally exclude private model reasoning and hidden
chain-of-thought. They are evidence of actions and policy outcomes, not a
serialization of internal cognition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Any, Mapping

FAMILY_SCHEMA = "pocket.family.v1"
RECEIPT_SCHEMA = "pocket.execution-receipt.v1"
SUPPORTED_ACTIONS = ("agent.run", "agent.attach", "agent.schedule", "agent.capsule")
SUPPORTED_STATUSES = ("accepted", "running", "succeeded", "failed", "denied", "cancelled", "timed_out")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _principal(value: str | Mapping[str, Any] | None, tenant: str | None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        out = dict(value)
        out.setdefault("id", "anonymous")
        out.setdefault("type", "user")
    else:
        out = {"id": value or "anonymous", "type": "user"}
    if tenant is not None:
        out.setdefault("tenant_id", tenant)
    return out


@dataclass(frozen=True)
class FamilyEnvelope:
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: f"pfr_{secrets.token_hex(12)}")
    session_id: str | None = None
    principal: str | Mapping[str, Any] | None = None
    tenant: str | None = None
    agent_id: str | None = None
    project_id: str | None = None
    policy: dict[str, Any] = field(default_factory=dict)
    schema: str = FAMILY_SCHEMA
    issued_at: str = field(default_factory=_now)
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if self.action not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported_action:{self.action}")
        if not isinstance(self.payload, dict):
            raise TypeError("payload_must_be_dict")
        if not isinstance(self.policy, dict):
            raise TypeError("policy_must_be_dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "action": self.action,
            "principal": _principal(self.principal, self.tenant),
            "scope": {
                "tenant_id": self.tenant,
                "session_id": self.session_id,
                "agent_id": self.agent_id,
                "project_id": self.project_id,
            },
            "policy": dict(self.policy),
            "payload": dict(self.payload),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    request_id: str
    action: str
    status: str
    runtime_ms: int
    result_summary: str = ""
    artifact_hashes: tuple[str, ...] = ()
    principal_id: str | None = None
    tenant_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    runtime: str | None = "pocket-agent"
    policy: dict[str, Any] = field(default_factory=dict)
    receipt_id: str = field(default_factory=lambda: f"per_{secrets.token_hex(12)}")
    schema: str = RECEIPT_SCHEMA
    started_at: str = field(default_factory=_now)
    finished_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.action not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported_action:{self.action}")
        normalized = "succeeded" if self.status == "completed" else self.status
        if normalized not in SUPPORTED_STATUSES:
            raise ValueError(f"unsupported_status:{self.status}")
        if self.runtime_ms < 0:
            raise ValueError("runtime_ms_must_be_nonnegative")
        if not isinstance(self.policy, dict):
            raise TypeError("policy_must_be_dict")

    def to_dict(self) -> dict[str, Any]:
        status = "succeeded" if self.status == "completed" else self.status
        result = {
            "summary": self.result_summary,
            "artifact_hashes": list(self.artifact_hashes),
        }
        data = {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "request_id": self.request_id,
            "action": self.action,
            "status": status,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "runtime": self.runtime,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.runtime_ms,
            "result": result,
            "error": None,
            "policy": dict(self.policy),
            "metadata": {"reasoning_exposed": False},
        }
        data["digest"] = _stable_hash(data)
        return data


def capability_descriptor() -> dict[str, Any]:
    return {
        "schema": FAMILY_SCHEMA,
        "component": "pocket-agent",
        "plane": "execution",
        "actions": list(SUPPORTED_ACTIONS),
        "receipts": RECEIPT_SCHEMA,
        "reasoning_exposed": False,
        "boundaries": {
            "cwd_scoped": True,
            "capsule_available": True,
            "host_identity_owned_by": "pocket",
            "voice_turn_timing_owned_by": "pocket-voice-to-text",
        },
    }


def make_envelope(action: str, payload: Mapping[str, Any] | None = None, **metadata: Any) -> FamilyEnvelope:
    return FamilyEnvelope(action=action, payload=dict(payload or {}), **metadata)


def make_receipt(envelope: FamilyEnvelope, *, status: str, runtime_ms: int, **fields: Any) -> ExecutionReceipt:
    principal = _principal(envelope.principal, envelope.tenant)
    return ExecutionReceipt(
        request_id=envelope.request_id,
        action=envelope.action,
        session_id=envelope.session_id,
        tenant_id=envelope.tenant,
        principal_id=principal.get("id"),
        agent_id=envelope.agent_id,
        status=status,
        runtime_ms=runtime_ms,
        policy=dict(envelope.policy),
        **fields,
    )
