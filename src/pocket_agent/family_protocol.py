"""Provider-neutral POCKET family execution envelopes and receipts.

This module deliberately carries operational metadata only. It never serializes
private model reasoning or hidden chain-of-thought.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Any, Mapping

FAMILY_SCHEMA = "pocket.family.v1"
RECEIPT_SCHEMA = "pocket.execution-receipt.v1"
SUPPORTED_ACTIONS = ("agent.run", "agent.attach", "agent.schedule", "agent.capsule")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class FamilyEnvelope:
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: f"pfr_{secrets.token_hex(12)}")
    session_id: str | None = None
    principal: str | None = None
    tenant: str | None = None
    source: str = "pocket"
    schema: str = FAMILY_SCHEMA
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.action not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported_action:{self.action}")
        if not isinstance(self.payload, dict):
            raise TypeError("payload_must_be_dict")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionReceipt:
    request_id: str
    action: str
    status: str
    runtime_ms: int
    result_summary: str = ""
    artifact_hashes: tuple[str, ...] = ()
    agent_id: str | None = None
    session_id: str | None = None
    schema: str = RECEIPT_SCHEMA
    finished_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.action not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported_action:{self.action}")
        if self.status not in {"accepted", "running", "completed", "failed", "denied", "cancelled"}:
            raise ValueError(f"unsupported_status:{self.status}")
        if self.runtime_ms < 0:
            raise ValueError("runtime_ms_must_be_nonnegative")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["receipt_hash"] = _stable_hash(data)
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
    return ExecutionReceipt(
        request_id=envelope.request_id,
        action=envelope.action,
        session_id=envelope.session_id,
        status=status,
        runtime_ms=runtime_ms,
        **fields,
    )
