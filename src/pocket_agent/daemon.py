"""Background session markers — reattach after terminal disconnect."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path.home() / ".pocket" / "agent" / "sessions"
ROOT.mkdir(parents=True, exist_ok=True)


def start_session(*, goal: str = "", project: str = "default") -> Dict[str, Any]:
    sid = f"sess-{uuid.uuid4().hex[:12]}"
    rec = {
        "id": sid,
        "project": project,
        "goal": goal,
        "status": "running",
        "started_at": time.time(),
        "heartbeat_at": time.time(),
    }
    (ROOT / f"{sid}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def heartbeat(session_id: str) -> Dict[str, Any]:
    p = ROOT / f"{session_id}.json"
    if not p.is_file():
        return {"ok": False, "error": "not found"}
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["heartbeat_at"] = time.time()
    rec["status"] = "running"
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return {"ok": True, **rec}


def attach(session_id: str) -> Optional[Dict[str, Any]]:
    p = ROOT / f"{session_id}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def list_sessions() -> List[Dict[str, Any]]:
    items = []
    for f in ROOT.glob("sess-*.json"):
        try:
            items.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    items.sort(key=lambda x: -(x.get("heartbeat_at") or 0))
    return items
