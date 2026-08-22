"""Resilience primitives for long-running POCKET Agent work.

All state objects are deliberately serializable so the daemon/host can persist
them later without changing the wire contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def request_digest(action: str, payload: Mapping[str, Any], *, scope: Mapping[str, Any] | None = None) -> str:
    raw = json.dumps(
        {"action": action, "payload": dict(payload), "scope": dict(scope or {})},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    initial_backoff_ms: int = 250
    multiplier: float = 2.0
    max_backoff_ms: int = 4000
    retryable_codes: tuple[str, ...] = ("timeout", "provider_unavailable", "rate_limited")
    terminal_action: str = "handoff"

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError("max_attempts_out_of_range")
        if self.initial_backoff_ms < 0 or self.max_backoff_ms < self.initial_backoff_ms:
            raise ValueError("invalid_backoff")
        if self.multiplier < 1:
            raise ValueError("invalid_multiplier")
        if self.terminal_action not in {"handoff", "stop_and_report", "fail"}:
            raise ValueError("invalid_terminal_action")

    def delay_ms(self, attempt: int) -> int:
        if attempt < 1:
            raise ValueError("attempt_must_start_at_1")
        return min(self.max_backoff_ms, int(self.initial_backoff_ms * (self.multiplier ** (attempt - 1))))

    def decision(self, *, attempt: int, error_code: str) -> dict[str, Any]:
        retryable = error_code in self.retryable_codes and attempt < self.max_attempts
        return {
            "retry": retryable,
            "delay_ms": self.delay_ms(attempt) if retryable else 0,
            "next_action": "retry" if retryable else self.terminal_action,
            "attempt": attempt,
            "max_attempts": self.max_attempts,
            "error_code": error_code,
        }

    def to_protocol(self) -> dict[str, Any]:
        return {
            "schema": "nexus.retry-policy.v1",
            "max_attempts": self.max_attempts,
            "backoff": {"initial_ms": self.initial_backoff_ms, "multiplier": self.multiplier, "max_ms": self.max_backoff_ms},
            "retryable_codes": list(self.retryable_codes),
            "terminal_action": self.terminal_action,
        }


@dataclass
class CircuitBreaker:
    dependency: str
    threshold: int = 3
    recovery_seconds: int = 30
    state: str = "closed"
    failure_count: int = 0
    opened_at: str | None = None
    updated_at: str | None = None

    def _stamp(self) -> None:
        self.updated_at = _iso(_now())

    def record_success(self) -> None:
        self.state = "closed"
        self.failure_count = 0
        self.opened_at = None
        self._stamp()

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.state = "open"
            self.opened_at = _iso(_now())
        self._stamp()

    def allow_request(self, *, at: datetime | None = None) -> bool:
        if self.state == "closed":
            return True
        if self.state == "half_open":
            return True
        if self.state != "open" or not self.opened_at:
            return False
        opened = datetime.fromisoformat(self.opened_at)
        if (at or _now()) >= opened + timedelta(seconds=self.recovery_seconds):
            self.state = "half_open"
            self._stamp()
            return True
        return False

    def to_protocol(self) -> dict[str, Any]:
        self._stamp()
        return {
            "schema": "nexus.circuit-breaker.v1",
            "dependency": self.dependency,
            "state": self.state,
            "failure_count": self.failure_count,
            "threshold": self.threshold,
            "recovery_seconds": self.recovery_seconds,
            "opened_at": self.opened_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Lease:
    lease_id: str
    resource: str
    holder: str
    acquired_at: str
    expires_at: str
    state: str = "active"

    @classmethod
    def acquire(cls, *, lease_id: str, resource: str, holder: str, ttl_seconds: int = 60) -> "Lease":
        if ttl_seconds <= 0 or ttl_seconds > 86400:
            raise ValueError("invalid_lease_ttl")
        start = _now()
        return cls(lease_id, resource, holder, _iso(start), _iso(start + timedelta(seconds=ttl_seconds)))

    def expired(self, *, at: datetime | None = None) -> bool:
        return (at or _now()) >= datetime.fromisoformat(self.expires_at)

    def to_protocol(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema"] = "nexus.lease.v1"
        data["state"] = "expired" if self.expired() else self.state
        return data


def idempotency_record(*, key: str, action: str, payload: Mapping[str, Any], scope: Mapping[str, Any], state: str = "pending", ttl_seconds: int = 86400) -> dict[str, Any]:
    if not key or len(key) > 200:
        raise ValueError("invalid_idempotency_key")
    if state not in {"pending", "succeeded", "failed"}:
        raise ValueError("invalid_idempotency_state")
    start = _now()
    return {
        "schema": "nexus.idempotency.v1",
        "key": key,
        "scope": dict(scope),
        "request_digest": request_digest(action, payload, scope=scope),
        "state": state,
        "created_at": _iso(start),
        "expires_at": _iso(start + timedelta(seconds=ttl_seconds)),
    }
