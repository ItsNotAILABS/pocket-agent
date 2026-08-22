"""Practical deterministic intelligence primitives for POCKET Agent.

These helpers do not replace the model. They make orchestration predictable:
capability routing, explicit budgets, outcome evaluation, drift signals and
recovery recommendations are all inspectable and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Budget:
    wall_seconds: int = 300
    max_files_changed: int = 25
    max_changed_bytes: int = 250_000
    max_subprocesses: int = 20
    max_external_calls: int = 20
    max_children: int = 8
    max_artifact_bytes: int = 20_000_000

    def validate(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid_budget:{name}")

    def to_protocol(self) -> dict[str, Any]:
        self.validate()
        return {"schema": "nexus.budget.v1", "limits": dict(self.__dict__)}


@dataclass
class Usage:
    files_changed: int = 0
    changed_bytes: int = 0
    subprocesses: int = 0
    external_calls: int = 0
    children: int = 0
    artifact_bytes: int = 0


def budget_status(budget: Budget, usage: Usage) -> dict[str, Any]:
    budget.validate()
    mapping = {
        "files_changed": (usage.files_changed, budget.max_files_changed),
        "changed_bytes": (usage.changed_bytes, budget.max_changed_bytes),
        "subprocesses": (usage.subprocesses, budget.max_subprocesses),
        "external_calls": (usage.external_calls, budget.max_external_calls),
        "children": (usage.children, budget.max_children),
        "artifact_bytes": (usage.artifact_bytes, budget.max_artifact_bytes),
    }
    exceeded = [name for name, (used, limit) in mapping.items() if used > limit]
    ratios = {
        name: (used / limit if limit else (1.0 if used else 0.0))
        for name, (used, limit) in mapping.items()
    }
    return {
        "ok": not exceeded,
        "status": "within_budget" if not exceeded else "budget_exhausted",
        "exceeded": exceeded,
        "ratios": ratios,
    }


def route_capability(intent: str, capabilities: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministically rank capabilities by lexical evidence.

    Low confidence is explicit so callers can ask the model/operator instead of
    silently selecting the wrong execution plane.
    """
    tokens = {t for t in intent.lower().replace("_", " ").split() if len(t) > 2}
    ranked: list[tuple[float, Mapping[str, Any], str]] = []
    for cap in capabilities:
        component = str(cap.get("component") or "unknown")
        actions = cap.get("actions") or []
        haystack = " ".join([component, str(cap.get("role") or ""), *map(str, actions)]).lower()
        score_hits = sum(1 for token in tokens if token in haystack)
        score = score_hits / max(1, len(tokens))
        ranked.append((score, cap, component))
    ranked.sort(key=lambda x: (-x[0], x[2]))
    best = ranked[0] if ranked else (0.0, {}, "")
    alternatives = [
        {"component": component, "score": round(score, 3)}
        for score, _, component in ranked[:3]
    ]
    return {
        "selected": best[2] or None,
        "confidence": round(best[0], 3),
        "needs_review": best[0] < 0.25,
        "alternatives": alternatives,
    }


def evaluate_outcome(acceptance: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate common acceptance criteria without trusting prose claims."""
    checks: dict[str, bool] = {}
    required_tests = int(acceptance.get("min_tests_passed") or 0)
    checks["tests"] = int(evidence.get("tests_passed") or 0) >= required_tests

    required_artifacts = set(map(str, acceptance.get("required_artifacts") or []))
    actual_artifacts = set(map(str, evidence.get("artifacts") or []))
    checks["artifacts"] = required_artifacts.issubset(actual_artifacts)

    if acceptance.get("require_clean_exit"):
        checks["clean_exit"] = evidence.get("exit_code") == 0
    if acceptance.get("require_receipt"):
        checks["receipt"] = bool(evidence.get("receipt_digest"))

    failed = [name for name, passed in checks.items() if not passed]
    return {"ok": not failed, "checks": checks, "failed": failed}


def detect_drift(declared: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    drift: list[str] = []
    for key in ("version", "schema", "component"):
        if key in declared and key in observed and declared[key] != observed[key]:
            drift.append(key)
    declared_actions = set(map(str, declared.get("actions") or []))
    observed_actions = set(map(str, observed.get("actions") or []))
    missing = sorted(declared_actions - observed_actions)
    extra = sorted(observed_actions - declared_actions)
    if missing:
        drift.append("missing_actions")
    if extra:
        drift.append("undeclared_actions")
    return {"drift": bool(drift), "fields": drift, "missing_actions": missing, "undeclared_actions": extra}


def recovery_plan(*, error_code: str, retryable: bool, fallback_components: Iterable[str] = ()) -> dict[str, Any]:
    fallbacks = [str(x) for x in fallback_components]
    if retryable:
        action = "retry_once"
    elif fallbacks:
        action = "handoff"
    else:
        action = "stop_and_report"
    return {
        "error_code": error_code,
        "recommended_action": action,
        "max_automatic_retries": 1 if retryable else 0,
        "fallback_components": fallbacks,
        "avoid_retry_storm": True,
    }
