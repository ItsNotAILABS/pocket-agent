"""Executable skills as importable packages (Prime-style skill creator target)."""

from __future__ import annotations

from typing import Any, Dict


def skill_capsule_reasons(**_: Any) -> Dict[str, Any]:
    from pocket_agent.capsules import list_reasons

    return {"ok": True, "reasons": list_reasons()}


def skill_spin_capsule(
    *,
    reason: str = "untrusted_eval",
    tier: str = "512MB",
    webgpu: bool = False,
    **_: Any,
) -> Dict[str, Any]:
    from pocket_agent.capsules import spin

    return spin(reason=reason, tier=tier, webgpu=webgpu)


SKILLS = {
    "capsule_reasons": skill_capsule_reasons,
    "spin_capsule": skill_spin_capsule,
}
