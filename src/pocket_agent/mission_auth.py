"""Scoped, tenant-bound API-key identity for the mission HTTP surface.

Raw tokens are presented by callers but are never stored by the registry. The
registry stores SHA-256 token digests, principal and tenant identities, scopes,
expiry, and disable state. A single shared bearer token plus caller-selected
identity headers is not considered multi-user authentication.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Mapping, Sequence


AUTH_SCHEMA = "pocket.mission-api-keys.v1"
KNOWN_SCOPES = {
    "mission:plan",
    "mission:create",
    "mission:read",
    "mission:run",
    "mission:control",
    "artifact:read",
    "worker:read",
    "*",
}


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MissionIdentityGrant:
    key_id: str
    principal_id: str
    tenant_id: str
    scopes: tuple[str, ...]
    roles: tuple[str, ...] = ()
    expires_at_unix: int | None = None
    metadata: Mapping[str, Any] | None = None
    schema: str = "pocket.mission-identity-grant.v1"

    def allows(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes

    def require(self, scope: str) -> None:
        if not self.allows(scope):
            raise PermissionError(f"mission API key lacks scope {scope}")

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["metadata"] = dict(self.metadata or {})
        return value


class MissionApiKeyRegistry:
    """Reloadable digest registry with constant-time token matching."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        document: Mapping[str, Any] | None = None,
    ) -> None:
        self.path = Path(path).expanduser() if path else None
        self._document = dict(document) if document is not None else None
        self._entries: tuple[dict[str, Any], ...] = ()
        self._mtime_ns: int | None = None
        self._lock = threading.RLock()
        self.reload(force=True)

    @classmethod
    def from_env(cls) -> "MissionApiKeyRegistry":
        path = os.getenv("POCKET_MISSION_API_KEYS_FILE", "").strip()
        raw = os.getenv("POCKET_MISSION_API_KEYS_JSON", "").strip()
        if path and raw:
            raise ValueError(
                "configure only one of POCKET_MISSION_API_KEYS_FILE and POCKET_MISSION_API_KEYS_JSON"
            )
        if path:
            return cls(path=path)
        if raw:
            value = json.loads(raw)
            if not isinstance(value, Mapping):
                raise ValueError("POCKET_MISSION_API_KEYS_JSON must be an object")
            return cls(document=value)
        return cls(document={"schema": AUTH_SCHEMA, "keys": []})

    @property
    def configured(self) -> bool:
        return bool(self._entries)

    def reload(self, *, force: bool = False) -> None:
        with self._lock:
            if self.path is not None:
                if not self.path.is_file():
                    raise FileNotFoundError(f"mission API key registry not found: {self.path}")
                stat = self.path.stat()
                if not force and self._mtime_ns == stat.st_mtime_ns:
                    return
                value = json.loads(self.path.read_text(encoding="utf-8"))
                self._mtime_ns = stat.st_mtime_ns
            else:
                value = dict(self._document or {})
            if not isinstance(value, Mapping):
                raise ValueError("mission API key registry must be an object")
            if value.get("schema") != AUTH_SCHEMA:
                raise ValueError(f"mission API key registry schema must be {AUTH_SCHEMA}")
            rows = value.get("keys")
            if not isinstance(rows, list):
                raise ValueError("mission API key registry requires a keys array")
            entries: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            seen_digests: set[str] = set()
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    raise ValueError(f"keys[{index}] must be an object")
                key_id = str(row.get("key_id") or "").strip()
                digest = str(row.get("token_sha256") or "").lower().strip()
                principal = str(row.get("principal_id") or "").strip()
                tenant = str(row.get("tenant_id") or "").strip()
                scopes = tuple(str(item) for item in row.get("scopes", ()))
                unknown = sorted(set(scopes) - KNOWN_SCOPES)
                if not key_id or key_id in seen_ids:
                    raise ValueError(f"duplicate or missing key_id at keys[{index}]")
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError(f"invalid token_sha256 for {key_id}")
                if digest in seen_digests:
                    raise ValueError("token digests must be unique")
                if not principal or not tenant:
                    raise ValueError(f"principal_id and tenant_id are required for {key_id}")
                if not scopes or unknown:
                    raise ValueError(f"invalid scopes for {key_id}: {unknown or 'none supplied'}")
                entries.append(
                    {
                        "key_id": key_id,
                        "token_sha256": digest,
                        "principal_id": principal,
                        "tenant_id": tenant,
                        "scopes": scopes,
                        "roles": tuple(str(item) for item in row.get("roles", ())),
                        "expires_at_unix": (
                            int(row["expires_at_unix"])
                            if row.get("expires_at_unix") is not None
                            else None
                        ),
                        "disabled": bool(row.get("disabled", False)),
                        "metadata": dict(row.get("metadata") or {}),
                    }
                )
                seen_ids.add(key_id)
                seen_digests.add(digest)
            self._entries = tuple(entries)

    def authenticate(self, authorization: str, *, required_scope: str) -> MissionIdentityGrant:
        self.reload()
        if not authorization.startswith("Bearer "):
            raise PermissionError("mission API bearer token is required")
        token = authorization[7:]
        if len(token) < 24:
            raise PermissionError("mission API bearer token is invalid")
        supplied = token_sha256(token)
        now = int(time.time())
        selected: dict[str, Any] | None = None
        # Compare against every digest to reduce key-position timing leakage.
        for row in self._entries:
            matched = hmac.compare_digest(supplied, row["token_sha256"])
            if matched:
                selected = row
        if selected is None:
            raise PermissionError("mission API bearer token is invalid")
        if selected["disabled"]:
            raise PermissionError("mission API key is disabled")
        expires = selected["expires_at_unix"]
        if expires is not None and expires < now:
            raise PermissionError("mission API key has expired")
        grant = MissionIdentityGrant(
            key_id=selected["key_id"],
            principal_id=selected["principal_id"],
            tenant_id=selected["tenant_id"],
            scopes=selected["scopes"],
            roles=selected["roles"],
            expires_at_unix=expires,
            metadata=selected["metadata"],
        )
        grant.require(required_scope)
        return grant

    def public(self) -> dict[str, Any]:
        return {
            "schema": AUTH_SCHEMA,
            "configured": self.configured,
            "key_count": len(self._entries),
            "keys": [
                {
                    "key_id": row["key_id"],
                    "principal_id": row["principal_id"],
                    "tenant_id": row["tenant_id"],
                    "scopes": list(row["scopes"]),
                    "roles": list(row["roles"]),
                    "expires_at_unix": row["expires_at_unix"],
                    "disabled": row["disabled"],
                }
                for row in self._entries
            ],
            "raw_tokens_stored": False,
        }


def key_registry_document(
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a registry document from raw tokens without retaining them."""
    rows = []
    for index, entry in enumerate(entries):
        token = str(entry.get("token") or "")
        if len(token) < 24:
            raise ValueError(f"entries[{index}].token must contain at least 24 characters")
        rows.append(
            {
                "key_id": str(entry.get("key_id") or f"key-{index + 1}"),
                "token_sha256": token_sha256(token),
                "principal_id": str(entry.get("principal_id") or ""),
                "tenant_id": str(entry.get("tenant_id") or ""),
                "scopes": list(entry.get("scopes") or []),
                "roles": list(entry.get("roles") or []),
                "expires_at_unix": entry.get("expires_at_unix"),
                "disabled": bool(entry.get("disabled", False)),
                "metadata": dict(entry.get("metadata") or {}),
            }
        )
    return {"schema": AUTH_SCHEMA, "keys": rows}
