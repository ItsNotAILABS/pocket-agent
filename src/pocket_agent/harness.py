"""Continual harness — durable supplemental state with /refine + rollback."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Immutable — never rewritten by refine
BASE_SYSTEM = """You are POCKET Agent: an RLM + continual-harness coding/research agent.
You improve via evidence-backed harness updates, subagents, RAH when parallel, and WASM capsules for isolation.
Never claim ambient host authority outside granted tools/capsules.
"""

ROOT = Path.home() / ".pocket" / "agent" / "harness"


class Harness:
    def __init__(self, project: str = "default") -> None:
        self.project = (project or "default").replace("/", "_")[:80]
        self.dir = ROOT / self.project
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "state.json"
        self.snap_dir = self.dir / "snapshots"
        self.snap_dir.mkdir(exist_ok=True)
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.is_file():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "schema": "pocket.agent.harness.v1",
            "project": self.project,
            "base_system_sha": "immutable",
            "supplemental_prompt": "",
            "memories": [],
            "skills": [],
            "subagent_specs": [],
            "goals": [],
            "history": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def save(self) -> None:
        self.state["updated_at"] = time.time()
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def snapshot(self, label: str = "") -> str:
        sid = f"snap-{uuid.uuid4().hex[:10]}"
        fp = self.snap_dir / f"{sid}.json"
        payload = {"id": sid, "label": label, "at": time.time(), "state": self.state}
        fp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.state.setdefault("history", []).append({"op": "snapshot", "id": sid, "at": time.time()})
        self.save()
        return sid

    def rollback(self, snap_id: Optional[str] = None) -> Dict[str, Any]:
        snaps = sorted(self.snap_dir.glob("snap-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not snaps:
            return {"ok": False, "error": "no snapshots"}
        target = None
        if snap_id:
            for s in snaps:
                if snap_id in s.name:
                    target = s
                    break
        target = target or snaps[0]
        data = json.loads(target.read_text(encoding="utf-8"))
        self.state = data.get("state") or self.state
        self.save()
        return {"ok": True, "restored": target.name}

    def set_goal(self, goal: str) -> None:
        g = (goal or "").strip()
        if not g:
            return
        self.state.setdefault("goals", []).append({"goal": g, "at": time.time(), "active": True})
        self.save()

    def remember(self, note: str) -> None:
        n = (note or "").strip()
        if not n:
            return
        mems = self.state.setdefault("memories", [])
        mems.append({"note": n[:2000], "at": time.time()})
        self.state["memories"] = mems[-200:]
        self.save()

    def refine(self, *, evidence: str, notes: str = "") -> Dict[str, Any]:
        """Evidence-backed small updates — never touches BASE_SYSTEM."""
        evidence = (evidence or "").strip()
        if not evidence:
            return {"ok": False, "error": "evidence required"}
        self.snapshot(label="pre-refine")
        delta = f"\n- [{time.strftime('%Y-%m-%d')}] {evidence[:500]}"
        if notes:
            delta += f" ({notes[:200]})"
        supp = self.state.get("supplemental_prompt") or ""
        # keep supplemental bounded
        self.state["supplemental_prompt"] = (supp + delta)[-8000:]
        self.remember(f"refine: {evidence[:300]}")
        self.state.setdefault("history", []).append(
            {"op": "refine", "evidence": evidence[:400], "at": time.time()}
        )
        self.save()
        return {
            "ok": True,
            "applied": True,
            "base_system_rewritten": False,
            "supplemental_chars": len(self.state.get("supplemental_prompt") or ""),
        }

    def system_prompt(self) -> str:
        parts = [BASE_SYSTEM.strip()]
        supp = (self.state.get("supplemental_prompt") or "").strip()
        if supp:
            parts.append("## Supplemental harness\n" + supp)
        goals = [g for g in (self.state.get("goals") or []) if g.get("active")]
        if goals:
            parts.append("## Active goals\n" + "\n".join(f"- {g['goal']}" for g in goals[-8:]))
        mems = self.state.get("memories") or []
        if mems:
            parts.append(
                "## Recent memories\n"
                + "\n".join(f"- {m.get('note')}" for m in mems[-12:])
            )
        return "\n\n".join(parts) + "\n"

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.state)
