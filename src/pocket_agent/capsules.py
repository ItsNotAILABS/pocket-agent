"""WASM multi-sandbox capsule spin-up + 20 agent reasons.

When POCKET host is on PYTHONPATH, uses PROTO-CAPSULE-WASM-009.
Otherwise allocates a local filesystem capsule under ~/.pocket/capsules/.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path.home() / ".pocket" / "capsules"

# Machine-readable catalog — agents choose by reason id
CAPSULE_REASONS: List[Dict[str, str]] = [
    {"id": "untrusted_eval", "title": "Untrusted evaluation", "improves": "Run untrusted code without host ambient authority"},
    {"id": "sandbox_tests", "title": "Sandboxed tests", "improves": "Isolated tests that cannot trash the workspace"},
    {"id": "dependency_install", "title": "Ephemeral dependencies", "improves": "Install packages that never leak into host env"},
    {"id": "repo_mount_edit", "title": "Overlay repo edits", "improves": "Edit in overlay; commit only on explicit approve"},
    {"id": "wasm_guest_tool", "title": "WASM guest tools", "improves": "Portable .wasm tools with no ambient network"},
    {"id": "webgpu_compute", "title": "WebGPU compute", "improves": "GPGPU/ML kernels via WebGPU doctrine"},
    {"id": "parallel_slice", "title": "Parallel RAH slice", "improves": "Isolate one fan-out leaf FS to avoid writer collisions"},
    {"id": "adversarial_verify", "title": "Adversarial verify", "improves": "Throwaway environment for verifier/adversary"},
    {"id": "repro_bug", "title": "Bug reproduction", "improves": "Clean env repro with logs; terminate when done"},
    {"id": "secret_scrub", "title": "Secret scrubbing", "improves": "Discard overlay if secrets appear in processing"},
    {"id": "browser_worker", "title": "Browser worker", "improves": "DOM/WebGPU guest without polluting desk session"},
    {"id": "build_artifact", "title": "Build artifacts", "improves": "Compile in capsule; export only dist outputs"},
    {"id": "fuzz_input", "title": "Fuzz isolation", "improves": "Crash isolation for parsers and tools"},
    {"id": "policy_eval", "title": "Policy evaluation", "improves": "Run policy scripts without mutating live ledgers"},
    {"id": "skill_preview", "title": "Skill preview", "improves": "Try generated skills before durable promote"},
    {"id": "third_party_cli", "title": "Third-party CLI", "improves": "Cap FS preopens for untrusted CLIs"},
    {"id": "long_job_park", "title": "Long job park", "improves": "Park long work in overlay between heartbeats"},
    {"id": "multi_tenant_slice", "title": "Multi-tenant slice", "improves": "Soft isolation for seat/demo runs"},
    {"id": "mesh_artifact_lab", "title": "Mesh artifact lab", "improves": "Produce artifacts offline; publish hash-only"},
    {"id": "rollback_experiment", "title": "Rollback experiment", "improves": "Experiment freely; terminate = full rollback"},
]


def list_reasons() -> List[Dict[str, str]]:
    return list(CAPSULE_REASONS)


def reason_ids() -> List[str]:
    return [r["id"] for r in CAPSULE_REASONS]


def _local_spin(
    *,
    tier: str = "512MB",
    webgpu: bool = False,
    reason: str = "untrusted_eval",
    label: str = "",
    runtime: str = "HostWorker",
) -> Dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    cid = "cap-" + uuid.uuid4().hex[:12]
    root = ROOT / cid
    for sub in ("vfs", "overlay", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    meta = {
        "id": cid,
        "state": "allocated",
        "tier": tier,
        "enableWebGPU": bool(webgpu),
        "runtime": runtime,
        "reason": reason,
        "label": label or reason,
        "root": str(root),
        "created_at": time.time(),
        "protocol": "PROTO-CAPSULE-WASM-009",
        "source": "pocket-agent-local",
    }
    (root / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (root / "reason.txt").write_text(reason + "\n", encoding="utf-8")
    return {"ok": True, **meta}


def spin(
    *,
    tier: str = "512MB",
    webgpu: bool = False,
    reason: str = "untrusted_eval",
    label: str = "",
    runtime: str = "HostWorker",
    agent_id: str = "pocket-agent",
) -> Dict[str, Any]:
    """Spin up a WASM/multi-sandbox capsule. Prefer POCKET host when available."""
    rid = (reason or "untrusted_eval").strip()
    if rid not in reason_ids():
        # still allow custom, but annotate
        pass
    # Prefer host CapsuleManager
    try:
        from pocket.protocols.multi_sandbox_capsule import manager, run_capsule_skill

        r = run_capsule_skill(
            "capsule_allocate",
            prompt=label or rid,
            params={
                "tier": tier,
                "enableWebGPU": webgpu,
                "runtime": runtime,
                "agent_id": agent_id,
                "label": label or rid,
                "reason": rid,
            },
        )
        if isinstance(r, dict) and r.get("ok"):
            cap = r.get("capsule") if isinstance(r.get("capsule"), dict) else r
            out = {
                "ok": True,
                "id": cap.get("id") or r.get("id"),
                "state": cap.get("state") or "allocated",
                "tier": (cap.get("config") or {}).get("tier") or tier,
                "reason": r.get("reason") or rid,
                "root": cap.get("root"),
                "protocol": r.get("protocol") or "PROTO-CAPSULE-WASM-009",
                "source": "pocket-host",
                "raw": r,
            }
            return out
        # fallback manager API
        m = manager()
        alloc = m.allocate(
            {
                "tier": tier,
                "enableWebGPU": webgpu,
                "runtime": runtime,
                "agent_id": agent_id,
                "label": label or rid,
                "reason": rid,
            }
        )
        if isinstance(alloc, dict) and alloc.get("ok"):
            cap = alloc.get("capsule") or {}
            return {
                "ok": True,
                "id": cap.get("id"),
                "state": cap.get("state") or "allocated",
                "reason": rid,
                "source": "pocket-host",
                "raw": alloc,
            }
    except Exception:
        pass
    return _local_spin(tier=tier, webgpu=webgpu, reason=rid, label=label, runtime=runtime)


def terminate(capsule_id: str) -> Dict[str, Any]:
    try:
        from pocket.protocols.multi_sandbox_capsule import run_capsule_skill

        r = run_capsule_skill("capsule_terminate", params={"id": capsule_id})
        if isinstance(r, dict):
            return r
    except Exception:
        pass
    p = ROOT / capsule_id
    if p.is_dir():
        meta = p / "meta.json"
        if meta.is_file():
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                m["state"] = "terminated"
                meta.write_text(json.dumps(m, indent=2), encoding="utf-8")
            except Exception:
                pass
        return {"ok": True, "id": capsule_id, "state": "terminated"}
    return {"ok": False, "error": "not found", "id": capsule_id}


def list_capsules() -> Dict[str, Any]:
    try:
        from pocket.protocols.multi_sandbox_capsule import manager

        return {"ok": True, "capsules": manager().list()}
    except Exception:
        items = []
        if ROOT.is_dir():
            for d in ROOT.iterdir():
                if d.is_dir() and (d / "meta.json").is_file():
                    try:
                        items.append(json.loads((d / "meta.json").read_text(encoding="utf-8")))
                    except Exception:
                        items.append({"id": d.name})
        return {"ok": True, "capsules": items, "source": "local"}
