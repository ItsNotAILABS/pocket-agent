"""Agent-to-agent messaging without routing every note through the user."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path.home() / ".pocket" / "agent" / "bus"
ROOT.mkdir(parents=True, exist_ok=True)


def send(to: str, body: str, *, from_agent: str = "agent", channel: str = "default") -> Dict[str, Any]:
    msg = {
        "id": f"msg-{uuid.uuid4().hex[:10]}",
        "from": from_agent,
        "to": to,
        "channel": channel,
        "body": (body or "")[:8000],
        "at": time.time(),
    }
    inbox = ROOT / f"{to}.jsonl"
    with inbox.open("a", encoding="utf-8") as f:
        f.write(json.dumps(msg) + "\n")
    return {"ok": True, "message": msg}


def inbox(agent: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    path = ROOT / f"{agent}.jsonl"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out
