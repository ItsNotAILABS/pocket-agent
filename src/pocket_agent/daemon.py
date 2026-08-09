"""Daemon-backed sessions — detach, reattach, heartbeats, schedules, status.

Prime Agent parity surface:
  pocket-agent agents | attach | --resume | status | doctor | schedule | shutdown

State lives under ~/.pocket/agent/ (local, durable). Worker/kernel isolation is
lifecycle-oriented — not a security sandbox. Use WASM capsules for untrusted code.
"""

from __future__ import annotations

import json
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path.home() / ".pocket" / "agent"
SESS = ROOT / "sessions"
SCHED = ROOT / "schedules"
SERVICE = ROOT / "service.json"
LOG = ROOT / "daemon.log"

for d in (SESS, SCHED):
    d.mkdir(parents=True, exist_ok=True)


def _now() -> float:
    return time.time()


def _write(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _read(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Service (background continuity marker)
# ---------------------------------------------------------------------------

def ensure_service() -> Dict[str, Any]:
    """Mark background service alive (file-backed; optional host worker)."""
    rec = _read(SERVICE) or {
        "schema": "pocket.agent.service.v1",
        "status": "stopped",
        "started_at": None,
        "pid": None,
    }
    rec["status"] = "running"
    rec["pid"] = os.getpid()
    rec["heartbeat_at"] = _now()
    if not rec.get("started_at"):
        rec["started_at"] = _now()
    rec["home"] = str(ROOT)
    rec["warning"] = (
        "Worker/kernel lifecycle isolation is not a security sandbox. "
        "Use capsule_spin for untrusted code."
    )
    _write(SERVICE, rec)
    return rec


def service_status() -> Dict[str, Any]:
    rec = _read(SERVICE) or {"status": "stopped"}
    # Stale if no heartbeat in 120s
    hb = float(rec.get("heartbeat_at") or 0)
    if rec.get("status") == "running" and hb and (_now() - hb) > 120:
        rec["status"] = "stale"
        rec["stale"] = True
    rec["ok"] = True
    rec["sessions"] = len(list_sessions())
    rec["schedules"] = len(list_schedules())
    return rec


def service_shutdown(*, force: bool = False) -> Dict[str, Any]:
    n = 0
    for s in list_sessions():
        if s.get("status") in ("running", "idle", "autonomous"):
            stop_session(s["id"], reason="shutdown")
            n += 1
    for sc in list_schedules():
        if sc.get("enabled"):
            disable_schedule(sc["id"])
    rec = {
        "schema": "pocket.agent.service.v1",
        "status": "stopped",
        "stopped_at": _now(),
        "force": force,
        "sessions_stopped": n,
    }
    _write(SERVICE, rec)
    _log(f"shutdown force={force} sessions={n}")
    return {"ok": True, **rec}


def doctor(*, fix: bool = False) -> Dict[str, Any]:
    """Inspect or repair background service state."""
    issues: List[str] = []
    fixes: List[str] = []
    ROOT.mkdir(parents=True, exist_ok=True)
    for d in (SESS, SCHED):
        if not d.is_dir():
            issues.append(f"missing dir {d}")
            if fix:
                d.mkdir(parents=True, exist_ok=True)
                fixes.append(f"created {d}")
    svc = service_status()
    if svc.get("status") in ("stopped", "stale", None):
        issues.append(f"service {svc.get('status')}")
        if fix:
            ensure_service()
            fixes.append("service restarted (marker)")
    # orphan session files with ancient heartbeats
    for s in list_sessions():
        hb = float(s.get("heartbeat_at") or 0)
        if s.get("status") == "running" and hb and (_now() - hb) > 3600:
            issues.append(f"stale session {s.get('id')}")
            if fix:
                stop_session(s["id"], reason="doctor_stale")
                fixes.append(f"stopped {s.get('id')}")
    return {
        "ok": len(issues) == 0 or fix,
        "issues": issues,
        "fixes": fixes if fix else [],
        "service": service_status(),
        "sessions": len(list_sessions()),
        "capsules_hint": "pocket-agent capsule list",
        "sandbox_warning": (
            "Not a security sandbox. Review changes; spin WASM capsules for untrusted code."
        ),
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def start_session(
    *,
    goal: str = "",
    project: str = "default",
    cwd: str = "",
    autonomous: bool = False,
    max_turns: int = 32,
    max_tokens: int = 200_000,
    max_minutes: float = 120.0,
) -> Dict[str, Any]:
    ensure_service()
    sid = f"sess-{uuid.uuid4().hex[:12]}"
    rec = {
        "id": sid,
        "project": project,
        "cwd": cwd or os.getcwd(),
        "goal": goal,
        "goals": ([{"id": "g0", "text": goal, "status": "active", "progress": ""}] if goal else []),
        "status": "autonomous" if autonomous else "running",
        "started_at": _now(),
        "heartbeat_at": _now(),
        "turns": 0,
        "tokens_est": 0,
        "autonomous": {
            "enabled": autonomous,
            "max_turns": max_turns,
            "max_tokens": max_tokens,
            "max_minutes": max_minutes,
            "quality_gates": [],
        },
        "transcript": [],
        "subagents_retained": [],
        "engine": "pocket-agent",
    }
    _write(SESS / f"{sid}.json", rec)
    _log(f"session start {sid} project={project}")
    return rec


def save_session(rec: Dict[str, Any]) -> None:
    sid = rec.get("id")
    if not sid:
        return
    rec["heartbeat_at"] = _now()
    _write(SESS / f"{sid}.json", rec)


def heartbeat(session_id: str, *, note: str = "") -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    rec["heartbeat_at"] = _now()
    if rec.get("status") in ("idle", "detached"):
        rec["status"] = "running"
    if note:
        rec.setdefault("transcript", []).append(
            {"role": "system", "text": f"heartbeat: {note[:500]}", "at": _now()}
        )
    save_session(rec)
    ensure_service()
    return {"ok": True, **{k: rec[k] for k in ("id", "status", "heartbeat_at", "goal", "turns")}}


def attach(session_id: str) -> Optional[Dict[str, Any]]:
    # allow short id prefix
    p = SESS / f"{session_id}.json"
    if p.is_file():
        return _read(p)
    for f in SESS.glob("sess-*.json"):
        if session_id in f.stem or f.stem.endswith(session_id):
            return _read(f)
    return None


def resume(path_or_id: str) -> Optional[Dict[str, Any]]:
    """Resume a saved session by id or path."""
    path = Path(path_or_id)
    if path.is_file():
        rec = _read(path)
    else:
        rec = attach(path_or_id)
    if not rec:
        return None
    rec["status"] = "running"
    rec["heartbeat_at"] = _now()
    rec["resumed_at"] = _now()
    save_session(rec)
    ensure_service()
    return rec


def detach(session_id: str) -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    rec["status"] = "detached"
    rec["detached_at"] = _now()
    save_session(rec)
    return {"ok": True, "id": session_id, "status": "detached", "hint": f"pocket-agent attach {session_id}"}


def stop_session(session_id: str, *, reason: str = "stopped") -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    rec["status"] = "stopped"
    rec["stopped_at"] = _now()
    rec["stop_reason"] = reason
    save_session(rec)
    return {"ok": True, "id": session_id, "status": "stopped"}


def list_sessions(*, include_stopped: bool = True) -> List[Dict[str, Any]]:
    items = []
    for f in SESS.glob("sess-*.json"):
        rec = _read(f)
        if not rec:
            continue
        if not include_stopped and rec.get("status") == "stopped":
            continue
        # classify
        hb = float(rec.get("heartbeat_at") or 0)
        st = rec.get("status") or "idle"
        if st == "running" and hb and (_now() - hb) > 600:
            rec["status"] = "idle"
        items.append(rec)
    items.sort(key=lambda x: -(x.get("heartbeat_at") or 0))
    return items


def append_turn(session_id: str, role: str, text: str, *, tokens: int = 0) -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    rec.setdefault("transcript", []).append({"role": role, "text": text[:20000], "at": _now()})
    rec["transcript"] = (rec.get("transcript") or [])[-200:]
    rec["turns"] = int(rec.get("turns") or 0) + (1 if role == "user" else 0)
    rec["tokens_est"] = int(rec.get("tokens_est") or 0) + int(tokens or max(1, len(text) // 4))
    # autonomous budgets
    auto = rec.get("autonomous") or {}
    if auto.get("enabled"):
        elapsed_min = (_now() - float(rec.get("started_at") or _now())) / 60.0
        if rec["turns"] >= int(auto.get("max_turns") or 32):
            rec["status"] = "limit_turns"
            rec["autonomous"]["stopped"] = "max_turns"
        elif rec["tokens_est"] >= int(auto.get("max_tokens") or 200_000):
            rec["status"] = "limit_tokens"
            rec["autonomous"]["stopped"] = "max_tokens"
        elif elapsed_min >= float(auto.get("max_minutes") or 120):
            rec["status"] = "limit_time"
            rec["autonomous"]["stopped"] = "max_minutes"
    save_session(rec)
    return {"ok": True, "turns": rec["turns"], "status": rec.get("status")}


# Goals (persistent across turns)
def set_goal(session_id: str, text: str) -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    gid = f"g-{uuid.uuid4().hex[:8]}"
    # pause previous active
    for g in rec.get("goals") or []:
        if g.get("status") == "active":
            g["status"] = "paused"
    rec.setdefault("goals", []).append(
        {"id": gid, "text": text.strip(), "status": "active", "progress": "", "at": _now()}
    )
    rec["goal"] = text.strip()
    save_session(rec)
    return {"ok": True, "goal_id": gid, "text": text.strip()}


def update_goal(session_id: str, *, progress: str = "", status: str = "") -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    for g in reversed(rec.get("goals") or []):
        if g.get("status") == "active" or not status:
            if progress:
                g["progress"] = progress[:1000]
            if status in ("active", "paused", "completed", "cleared"):
                g["status"] = status
                if status == "completed":
                    rec["goal"] = ""
            break
    save_session(rec)
    return {"ok": True, "goals": rec.get("goals")}


def set_autonomous(
    session_id: str,
    *,
    enabled: bool = True,
    max_turns: int = 32,
    max_tokens: int = 200_000,
    max_minutes: float = 120.0,
    quality_gates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    rec = attach(session_id)
    if not rec:
        return {"ok": False, "error": "not found"}
    rec["autonomous"] = {
        "enabled": enabled,
        "max_turns": max_turns,
        "max_tokens": max_tokens,
        "max_minutes": max_minutes,
        "quality_gates": quality_gates or [],
    }
    if enabled:
        rec["status"] = "autonomous"
    save_session(rec)
    return {"ok": True, "autonomous": rec["autonomous"]}


# ---------------------------------------------------------------------------
# Schedules — re-enter a session at interval or epoch
# ---------------------------------------------------------------------------

def schedule_add(
    *,
    session_id: str = "",
    every_seconds: float = 0,
    at_epoch: float = 0,
    note: str = "",
    command: str = "heartbeat",
) -> Dict[str, Any]:
    ensure_service()
    sid = f"sch-{uuid.uuid4().hex[:10]}"
    rec = {
        "id": sid,
        "session_id": session_id,
        "every_seconds": float(every_seconds or 0),
        "at_epoch": float(at_epoch or 0),
        "note": note[:500],
        "command": command,
        "enabled": True,
        "created_at": _now(),
        "next_at": float(at_epoch) if at_epoch else (_now() + float(every_seconds or 3600)),
        "last_fired": None,
    }
    _write(SCHED / f"{sid}.json", rec)
    return {"ok": True, **rec}


def list_schedules() -> List[Dict[str, Any]]:
    items = []
    for f in SCHED.glob("sch-*.json"):
        r = _read(f)
        if r:
            items.append(r)
    items.sort(key=lambda x: float(x.get("next_at") or 0))
    return items


def disable_schedule(schedule_id: str) -> Dict[str, Any]:
    p = SCHED / f"{schedule_id}.json"
    rec = _read(p)
    if not rec:
        for f in SCHED.glob("sch-*.json"):
            if schedule_id in f.stem:
                p = f
                rec = _read(f)
                break
    if not rec:
        return {"ok": False, "error": "not found"}
    rec["enabled"] = False
    _write(p, rec)
    return {"ok": True, "id": rec.get("id"), "enabled": False}


def fire_due_schedules() -> Dict[str, Any]:
    """Run due schedule hooks (heartbeat / note). Call from doctor or a loop."""
    fired = []
    now = _now()
    for sc in list_schedules():
        if not sc.get("enabled"):
            continue
        if float(sc.get("next_at") or 0) > now:
            continue
        sid = sc.get("session_id") or ""
        if sid:
            heartbeat(sid, note=sc.get("note") or sc.get("command") or "scheduled")
        sc["last_fired"] = now
        every = float(sc.get("every_seconds") or 0)
        if every > 0:
            sc["next_at"] = now + every
        else:
            sc["enabled"] = False
        _write(SCHED / f"{sc['id']}.json", sc)
        fired.append(sc["id"])
    return {"ok": True, "fired": fired, "count": len(fired)}
