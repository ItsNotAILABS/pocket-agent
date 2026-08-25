"""Persistent approval-bound runtime cells for POCKET Agent.

The module governs three execution bodies:
- agent-sandbox: bounded autonomous work under explicit policy;
- app-bottle: one packaged program in a minimal userspace;
- mini-os: a complete minimized operating environment.

It deliberately does not provide a shell or virtualization backend. Execution
is supplied by a caller-owned adapter after an exact, one-time approval is
consumed. Source presence therefore does not prove that OpenShell, a bottle, or
an x86/WASM machine actually executed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Any, Callable, Mapping, Sequence

RUNTIME_CLASSES = ("agent-sandbox", "app-bottle", "mini-os")
EXECUTION_SEQUENCE = ("discover", "classify-risk", "plan", "approve", "execute", "validate", "receipt")
CELL_SCHEMA = "nexus.runtime-cell.v1"
APPROVAL_SCHEMA = "nexus.approval.v1"
RECEIPT_SCHEMA = "nexus.execution-receipt.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class RuntimeCellSpec:
    cell_id: str
    runtime_class: str
    principal_id: str
    agent_id: str
    policy: Mapping[str, Any]
    backend: str
    resources: Mapping[str, Any] = field(default_factory=dict)
    filesystem: Mapping[str, Any] = field(default_factory=dict)
    network: Mapping[str, Any] = field(default_factory=dict)
    bindings: Sequence[str] = ()
    state: str = "declared"

    def __post_init__(self) -> None:
        if self.runtime_class not in RUNTIME_CLASSES:
            raise ValueError(f"unsupported runtime class: {self.runtime_class}")
        for name in ("cell_id", "principal_id", "agent_id", "backend"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.state not in {"declared", "ready", "suspended", "terminated"}:
            raise ValueError(f"unsupported cell state: {self.state}")

    @property
    def policy_hash(self) -> str:
        return _sha(dict(self.policy))

    def to_protocol(self) -> dict[str, Any]:
        return {
            "schema": CELL_SCHEMA,
            "cell_id": self.cell_id,
            "runtime_class": self.runtime_class,
            "principal": {"principal_id": self.principal_id, "principal_type": "runtime-cell"},
            "agent_id": self.agent_id,
            "policy_hash": self.policy_hash,
            "policy": dict(self.policy),
            "backend": self.backend,
            "resources": dict(self.resources),
            "filesystem": dict(self.filesystem),
            "network": dict(self.network),
            "bindings": list(self.bindings),
            "state": self.state,
            "created_at": "store-assigned",
            "claim_boundary": "runtime contract only; backend execution requires independent evidence",
        }


@dataclass(frozen=True)
class OperationRequest:
    operator_id: str
    agent_id: str
    cell_id: str
    tool: str
    arguments: Mapping[str, Any]
    filesystem_scope: Sequence[str] = ()
    egress_scope: Sequence[str] = ()
    environment: str = "development"
    estimated_cost_usd: float = 0.0
    destructive: bool = False

    def __post_init__(self) -> None:
        for name in ("operator_id", "agent_id", "cell_id", "tool"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.environment not in {"development", "staging", "production"}:
            raise ValueError("environment must be development, staging, or production")
        if float(self.estimated_cost_usd) < 0:
            raise ValueError("estimated_cost_usd must be nonnegative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "agent_id": self.agent_id,
            "cell_id": self.cell_id,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "filesystem_scope": list(self.filesystem_scope),
            "egress_scope": list(self.egress_scope),
            "environment": self.environment,
            "estimated_cost_usd": float(self.estimated_cost_usd),
            "destructive": bool(self.destructive),
        }

    @property
    def action_hash(self) -> str:
        return _sha(self.to_dict())


class RuntimeCellGovernor:
    """SQLite-backed runtime-cell, approval, replay, and receipt authority."""

    def __init__(self, path: str | Path, *, signing_key: str | bytes | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = signing_key or b""
        self._key = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        self._lock = threading.RLock()
        self._initialize()

    @property
    def signing_configured(self) -> bool:
        return bool(self._key)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_cells (
                    cell_id TEXT PRIMARY KEY,
                    runtime_class TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    policy_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    cell_id TEXT NOT NULL,
                    action_hash TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    nonce TEXT NOT NULL UNIQUE,
                    expires_at INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    token_hash TEXT,
                    created_at TEXT NOT NULL,
                    accepted_at TEXT,
                    consumed_at TEXT,
                    FOREIGN KEY(cell_id) REFERENCES runtime_cells(cell_id)
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    previous_hash TEXT,
                    payload_json TEXT NOT NULL,
                    receipt_hash TEXT NOT NULL UNIQUE,
                    signature TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(approval_id) REFERENCES approvals(approval_id)
                );
                CREATE INDEX IF NOT EXISTS approvals_status_expiry ON approvals(status, expires_at);
                CREATE INDEX IF NOT EXISTS receipts_created ON receipts(created_at);
                """
            )

    def register_cell(self, spec: RuntimeCellSpec) -> dict[str, Any]:
        protocol = spec.to_protocol()
        now = _now()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """INSERT INTO runtime_cells
                   (cell_id,runtime_class,principal_id,agent_id,policy_hash,payload_json,state,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(cell_id) DO UPDATE SET
                     runtime_class=excluded.runtime_class,
                     principal_id=excluded.principal_id,
                     agent_id=excluded.agent_id,
                     policy_hash=excluded.policy_hash,
                     payload_json=excluded.payload_json,
                     state=excluded.state,
                     updated_at=excluded.updated_at""",
                (
                    spec.cell_id,
                    spec.runtime_class,
                    spec.principal_id,
                    spec.agent_id,
                    spec.policy_hash,
                    json.dumps(protocol, sort_keys=True),
                    spec.state,
                    now,
                    now,
                ),
            )
            db.execute("COMMIT")
        return {**protocol, "created_at": now, "registration_sha256": _sha(protocol)}

    def get_cell(self, cell_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload_json,state,created_at,updated_at FROM runtime_cells WHERE cell_id=?", (cell_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload.update({"state": row["state"], "created_at": row["created_at"], "updated_at": row["updated_at"]})
        return payload

    def propose(self, operation: OperationRequest, *, ttl_seconds: int = 300) -> dict[str, Any]:
        cell = self.get_cell(operation.cell_id)
        if cell is None:
            raise ValueError("unknown runtime cell")
        if cell.get("state") in {"suspended", "terminated"}:
            raise ValueError(f"runtime cell is {cell.get('state')}")
        if cell.get("agent_id") != operation.agent_id:
            raise ValueError("operation agent does not own the runtime cell")
        ttl = max(30, min(int(ttl_seconds), 900))
        approval_id = "apr_" + secrets.token_hex(12)
        nonce = secrets.token_urlsafe(24)
        expires_at = int(time.time()) + ttl
        now = _now()
        action = operation.to_dict()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """INSERT INTO approvals
                   (approval_id,operator_id,agent_id,cell_id,action_hash,action_json,nonce,expires_at,status,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    approval_id,
                    operation.operator_id,
                    operation.agent_id,
                    operation.cell_id,
                    operation.action_hash,
                    json.dumps(action, sort_keys=True),
                    nonce,
                    expires_at,
                    "pending",
                    now,
                ),
            )
            db.execute("COMMIT")
        return {
            "schema": APPROVAL_SCHEMA,
            "approval_id": approval_id,
            "request_id": operation.action_hash,
            "actor": {"principal_id": operation.operator_id, "principal_type": "human"},
            "decision": "pending",
            "scope": action,
            "created_at": now,
            "expires_at": expires_at,
            "nonce": nonce,
            "action_hash": operation.action_hash,
        }

    def approve(self, approval_id: str, operator_id: str) -> str:
        if not self._key:
            raise ValueError("a signing key is required to accept runtime-cell operations")
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                raise ValueError("unknown approval")
            if row["operator_id"] != operator_id:
                db.execute("ROLLBACK")
                raise ValueError("approval belongs to another operator")
            if row["status"] != "pending":
                db.execute("ROLLBACK")
                raise ValueError(f"approval is {row['status']}")
            if int(row["expires_at"]) < int(time.time()):
                db.execute("UPDATE approvals SET status='expired' WHERE approval_id=?", (approval_id,))
                db.execute("COMMIT")
                raise ValueError("approval expired")
            token_payload = {
                "approval_id": approval_id,
                "operator_id": operator_id,
                "action_hash": row["action_hash"],
                "nonce": row["nonce"],
                "expires_at": int(row["expires_at"]),
            }
            encoded = _b64(_canonical(token_payload))
            signature = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
            token = f"{encoded}.{signature}"
            db.execute(
                "UPDATE approvals SET status='accepted',token_hash=?,accepted_at=? WHERE approval_id=?",
                (hashlib.sha256(token.encode("utf-8")).hexdigest(), _now(), approval_id),
            )
            db.execute("COMMIT")
        return token

    def consume(self, approval_id: str, operation: OperationRequest, token: str) -> dict[str, Any]:
        if not self._key:
            raise ValueError("a signing key is required to consume runtime-cell approvals")
        try:
            encoded, supplied_signature = token.split(".", 1)
            payload = json.loads(_unb64(encoded).decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid approval token") from exc
        expected_signature = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("invalid approval signature")
        if payload.get("approval_id") != approval_id:
            raise ValueError("approval token ID mismatch")
        if payload.get("action_hash") != operation.action_hash:
            raise ValueError("approval token does not match the exact action")
        if payload.get("operator_id") != operation.operator_id:
            raise ValueError("approval token operator mismatch")
        if int(payload.get("expires_at", 0)) < int(time.time()):
            raise ValueError("approval token expired")

        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                raise ValueError("unknown approval")
            if row["status"] != "accepted":
                db.execute("ROLLBACK")
                raise ValueError(f"approval is {row['status']}")
            if row["action_hash"] != operation.action_hash or row["nonce"] != payload.get("nonce"):
                db.execute("ROLLBACK")
                raise ValueError("stored approval does not match action or nonce")
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(str(row["token_hash"] or ""), token_hash):
                db.execute("ROLLBACK")
                raise ValueError("approval token hash mismatch")
            db.execute("UPDATE approvals SET status='consumed',consumed_at=? WHERE approval_id=?", (_now(), approval_id))
            db.execute("COMMIT")
        return json.loads(row["action_json"])

    def execute(
        self,
        *,
        approval_id: str,
        operation: OperationRequest,
        token: str,
        executor: Callable[[Mapping[str, Any]], Any],
        validator: Callable[[Any], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        action = self.consume(approval_id, operation, token)
        started = time.perf_counter()
        status = "succeeded"
        error = None
        output: Any = None
        validation: Mapping[str, Any] = {"status": "not-configured"}
        try:
            output = executor(action)
            if validator is not None:
                validation = dict(validator(output))
                if validation.get("status") not in {"pass", "validated"}:
                    status = "failed-validation"
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        receipt = self._write_receipt(
            approval_id=approval_id,
            operation=operation,
            status=status,
            output=output,
            error=error,
            validation=validation,
            duration_ms=duration_ms,
        )
        return receipt

    def _write_receipt(
        self,
        *,
        approval_id: str,
        operation: OperationRequest,
        status: str,
        output: Any,
        error: str | None,
        validation: Mapping[str, Any],
        duration_ms: float,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT receipt_hash FROM receipts ORDER BY rowid DESC LIMIT 1").fetchone()
            previous_hash = previous["receipt_hash"] if previous else None
            payload = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": "rcpt_" + secrets.token_hex(12),
                "request_id": operation.action_hash,
                "approval_id": approval_id,
                "status": status,
                "component": "pocket-agent",
                "cell_id": operation.cell_id,
                "agent_id": operation.agent_id,
                "operator_id": operation.operator_id,
                "tool": operation.tool,
                "started_at": now,
                "finished_at": now,
                "duration_ms": duration_ms,
                "output_digest": _sha(output),
                "error": error,
                "validation": dict(validation),
                "previous_receipt_hash": previous_hash,
                "reasoning_exposed": False,
                "claim_boundary": "receipt proves the governed call record, not external backend correctness beyond validation evidence",
            }
            receipt_hash = _sha(payload)
            signature = hmac.new(self._key, receipt_hash.encode("ascii"), hashlib.sha256).hexdigest() if self._key else None
            db.execute(
                "INSERT INTO receipts VALUES (?,?,?,?,?,?,?)",
                (
                    payload["receipt_id"], approval_id, previous_hash,
                    json.dumps(payload, sort_keys=True), receipt_hash, signature, now,
                ),
            )
            db.execute("COMMIT")
        return {**payload, "digest": receipt_hash, "signature": signature, "signed": bool(signature)}

    def verify_receipt_chain(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM receipts ORDER BY rowid").fetchall()
        errors: list[str] = []
        previous_hash: str | None = None
        for index, row in enumerate(rows):
            payload = json.loads(row["payload_json"])
            actual = _sha(payload)
            if actual != row["receipt_hash"]:
                errors.append(f"receipt {index}: payload hash mismatch")
            if row["previous_hash"] != previous_hash or payload.get("previous_receipt_hash") != previous_hash:
                errors.append(f"receipt {index}: chain link mismatch")
            if row["signature"] and self._key:
                expected = hmac.new(self._key, row["receipt_hash"].encode("ascii"), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(row["signature"], expected):
                    errors.append(f"receipt {index}: signature mismatch")
            previous_hash = row["receipt_hash"]
        return {
            "schema": "pocket.runtime-cell-receipt-chain.v1",
            "count": len(rows),
            "head": previous_hash,
            "status": "pass" if not errors else "fail",
            "errors": errors,
            "signed": bool(self._key),
        }
