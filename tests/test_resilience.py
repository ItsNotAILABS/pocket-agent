from datetime import datetime, timedelta, timezone

from pocket_agent.resilience import CircuitBreaker, Lease, RetryPolicy, idempotency_record, request_digest


def test_request_digest_is_stable_and_scope_sensitive():
    a = request_digest("agent.run", {"goal": "x"}, scope={"tenant_id": "a"})
    b = request_digest("agent.run", {"goal": "x"}, scope={"tenant_id": "a"})
    c = request_digest("agent.run", {"goal": "x"}, scope={"tenant_id": "b"})
    assert a == b
    assert a != c
    assert a.startswith("sha256:")


def test_retry_policy_is_bounded():
    p = RetryPolicy(max_attempts=3, initial_backoff_ms=100, multiplier=2, max_backoff_ms=250)
    assert p.decision(attempt=1, error_code="timeout") == {
        "retry": True,
        "delay_ms": 100,
        "next_action": "retry",
        "attempt": 1,
        "max_attempts": 3,
        "error_code": "timeout",
    }
    assert p.decision(attempt=2, error_code="timeout")["delay_ms"] == 200
    assert p.decision(attempt=3, error_code="timeout")["retry"] is False
    assert p.to_protocol()["schema"] == "nexus.retry-policy.v1"


def test_circuit_breaker_opens_and_recovers_half_open():
    c = CircuitBreaker("provider-x", threshold=2, recovery_seconds=5)
    c.record_failure()
    assert c.state == "closed"
    c.record_failure()
    assert c.state == "open"
    assert c.allow_request() is False
    future = datetime.fromisoformat(c.opened_at) + timedelta(seconds=6)
    assert c.allow_request(at=future) is True
    assert c.state == "half_open"
    c.record_success()
    assert c.state == "closed"
    assert c.failure_count == 0
    assert c.to_protocol()["schema"] == "nexus.circuit-breaker.v1"


def test_lease_has_expiry_and_protocol_shape():
    lease = Lease.acquire(lease_id="lease-1", resource="job:1", holder="agent:a", ttl_seconds=10)
    assert lease.expired() is False
    future = datetime.fromisoformat(lease.expires_at) + timedelta(seconds=1)
    assert lease.expired(at=future) is True
    assert lease.to_protocol()["schema"] == "nexus.lease.v1"


def test_idempotency_record_never_contains_secret_value():
    r = idempotency_record(
        key="client-123",
        action="agent.run",
        payload={"goal": "audit"},
        scope={"tenant_id": "t1", "project_id": "p1"},
    )
    assert r["schema"] == "nexus.idempotency.v1"
    assert r["request_digest"].startswith("sha256:")
    assert "secret" not in r
    assert "value" not in r
