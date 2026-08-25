"""SQLite/WAL state authority for POCKET Agent missions."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any, Iterable, Mapping, Sequence

TERMINAL_TASK_STATES = {"completed", "failed", "cancelled", "blocked"}
TERMINAL_MISSION_STATES = {"completed", "failed", "cancelled"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def now() -> int:
    return int(time.time())


def encode(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def decode(value: str | None, default: Any) -> Any:
    return default if not value else json.loads(value)


class MissionStore:
    """Multi-process-safe durable mission state with task leases and receipts."""

    def __init__(self, path: str | Path = "state/pocket-agent-missions.sqlite3") -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS missions (
                  mission_id TEXT PRIMARY KEY,
                  idempotency_key TEXT UNIQUE,
                  principal_id TEXT NOT NULL,
                  tenant_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  objective TEXT NOT NULL,
                  status TEXT NOT NULL,
                  max_parallel INTEGER NOT NULL,
                  budget_json TEXT NOT NULL,
                  deadline_unix INTEGER,
                  plan_sha256 TEXT NOT NULL,
                  result_summary TEXT,
                  artifact_manifest_sha256 TEXT,
                  error TEXT,
                  created_at_unix INTEGER NOT NULL,
                  updated_at_unix INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_tasks (
                  task_id TEXT PRIMARY KEY,
                  mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
                  ordinal INTEGER NOT NULL,
                  title TEXT NOT NULL,
                  objective TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  status TEXT NOT NULL,
                  priority INTEGER NOT NULL,
                  model_lane TEXT NOT NULL,
                  reasoning_rounds INTEGER NOT NULL,
                  max_attempts INTEGER NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  timeout_seconds INTEGER NOT NULL,
                  payload_json TEXT NOT NULL,
                  acceptance_json TEXT NOT NULL,
                  required_artifacts_json TEXT NOT NULL,
                  result_json TEXT,
                  error TEXT,
                  progress REAL NOT NULL DEFAULT 0,
                  available_at_unix INTEGER NOT NULL,
                  lease_owner TEXT,
                  lease_expires_at_unix INTEGER,
                  created_at_unix INTEGER NOT NULL,
                  updated_at_unix INTEGER NOT NULL,
                  UNIQUE(mission_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS mission_dependencies (
                  task_id TEXT NOT NULL REFERENCES mission_tasks(task_id) ON DELETE CASCADE,
                  depends_on_task_id TEXT NOT NULL REFERENCES mission_tasks(task_id) ON DELETE CASCADE,
                  PRIMARY KEY(task_id, depends_on_task_id)
                );
                CREATE TABLE IF NOT EXISTS mission_events (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                  mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
                  task_id TEXT,
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  observed_at_unix INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_artifacts (
                  artifact_id TEXT PRIMARY KEY,
                  mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
                  task_id TEXT,
                  relative_path TEXT NOT NULL,
                  media_type TEXT NOT NULL,
                  bytes INTEGER NOT NULL,
                  sha256 TEXT NOT NULL,
                  label TEXT NOT NULL,
                  created_at_unix INTEGER NOT NULL,
                  UNIQUE(mission_id, relative_path, sha256)
                );
                CREATE TABLE IF NOT EXISTS mission_decisions (
                  decision_id TEXT PRIMARY KEY,
                  mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
                  task_id TEXT NOT NULL REFERENCES mission_tasks(task_id) ON DELETE CASCADE,
                  summary TEXT NOT NULL,
                  options_json TEXT NOT NULL,
                  decision TEXT NOT NULL,
                  evidence_json TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  blockers_json TEXT NOT NULL,
                  decision_sha256 TEXT NOT NULL,
                  created_at_unix INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS mission_tasks_ready
                  ON mission_tasks(status,available_at_unix,priority,ordinal);
                CREATE INDEX IF NOT EXISTS mission_tasks_by_mission
                  ON mission_tasks(mission_id,status);
                CREATE INDEX IF NOT EXISTS mission_events_by_mission
                  ON mission_events(mission_id,sequence);
                """
            )

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def validate_graph(tasks: Sequence[Mapping[str, Any]]) -> None:
        ids = [str(item.get("task_id") or "") for item in tasks]
        if any(not item for item in ids) or len(ids) != len(set(ids)):
            raise ValueError("task IDs must be non-empty and unique")
        edges = {
            str(task["task_id"]): {str(item) for item in task.get("depends_on", []) or []}
            for task in tasks
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise ValueError("task dependency graph contains a cycle")
            visiting.add(task_id)
            for parent in edges[task_id]:
                if parent not in edges:
                    raise ValueError(f"unknown task dependency: {parent}")
                visit(parent)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in ids:
            visit(task_id)

    def create_mission(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        tasks = [dict(item) for item in spec.get("tasks", [])]
        if not tasks:
            raise ValueError("mission requires at least one task")
        self.validate_graph(tasks)
        budget = dict(spec.get("budget") or {})
        max_tasks = max(1, min(int(budget.get("max_tasks", 500)), 10_000))
        if len(tasks) > max_tasks:
            raise ValueError(f"mission has {len(tasks)} tasks but budget permits {max_tasks}")
        mission_id = str(spec.get("mission_id") or "mission_" + uuid.uuid4().hex)
        idempotency_key = str(spec.get("idempotency_key") or "").strip() or None
        created = now()
        plan_material = {
            "objective": spec.get("objective"),
            "tasks": tasks,
            "budget": budget,
            "max_parallel": spec.get("max_parallel", 3),
        }
        with self.transaction() as db:
            if idempotency_key:
                existing = db.execute(
                    "SELECT mission_id FROM missions WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    return self.get_mission(str(existing["mission_id"]))
            db.execute(
                """INSERT INTO missions(
                  mission_id,idempotency_key,principal_id,tenant_id,title,objective,status,
                  max_parallel,budget_json,deadline_unix,plan_sha256,created_at_unix,updated_at_unix
                ) VALUES (?,?,?,?,?,?,'queued',?,?,?,?,?,?)""",
                (
                    mission_id,
                    idempotency_key,
                    str(spec.get("principal_id") or "anonymous"),
                    str(spec.get("tenant_id") or "default"),
                    str(spec.get("title") or "POCKET Agent mission")[:300],
                    str(spec.get("objective") or "").strip(),
                    max(1, min(int(spec.get("max_parallel", 3)), 32)),
                    encode(budget),
                    int(spec["deadline_unix"]) if spec.get("deadline_unix") else None,
                    digest(plan_material),
                    created,
                    created,
                ),
            )
            task_ids = {str(item["task_id"]) for item in tasks}
            for ordinal, task in enumerate(tasks):
                task_id = str(task["task_id"])
                db.execute(
                    """INSERT INTO mission_tasks(
                      task_id,mission_id,ordinal,title,objective,kind,status,priority,model_lane,
                      reasoning_rounds,max_attempts,timeout_seconds,payload_json,acceptance_json,
                      required_artifacts_json,available_at_unix,created_at_unix,updated_at_unix
                    ) VALUES (?,?,?,?,?,?,'queued',?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task_id,
                        mission_id,
                        ordinal,
                        str(task.get("title") or task_id)[:300],
                        str(task.get("objective") or "").strip(),
                        str(task.get("kind") or "reasoning"),
                        max(-1000, min(int(task.get("priority", 0)), 1000)),
                        str(task.get("model_lane") or "auro-2b-council"),
                        max(1, min(int(task.get("reasoning_rounds", 1)), 12)),
                        max(1, min(int(task.get("max_attempts", 3)), 20)),
                        max(10, min(int(task.get("timeout_seconds", 900)), 86_400)),
                        encode(dict(task.get("payload") or {})),
                        encode(list(task.get("acceptance_criteria") or [])),
                        encode(list(task.get("required_artifacts") or [])),
                        created,
                        created,
                        created,
                    ),
                )
                for parent in task.get("depends_on", []) or []:
                    if str(parent) not in task_ids:
                        raise ValueError(f"unknown task dependency: {parent}")
                    db.execute(
                        "INSERT INTO mission_dependencies(task_id,depends_on_task_id) VALUES (?,?)",
                        (task_id, str(parent)),
                    )
            self._event(db, mission_id, None, "mission_created", {"plan_sha256": digest(plan_material), "task_count": len(tasks)}, created)
        return self.get_mission(mission_id)

    @staticmethod
    def _event(db: sqlite3.Connection, mission_id: str, task_id: str | None, event_type: str, payload: Mapping[str, Any], observed_at: int | None = None) -> None:
        db.execute(
            "INSERT INTO mission_events(mission_id,task_id,event_type,payload_json,observed_at_unix) VALUES (?,?,?,?,?)",
            (mission_id, task_id, event_type, encode(dict(payload)), observed_at or now()),
        )

    def recover_expired(self, current: int | None = None) -> int:
        observed = now() if current is None else int(current)
        with self.transaction() as db:
            return self._recover_expired_locked(db, observed)

    def _recover_expired_locked(self, db: sqlite3.Connection, observed: int) -> int:
        rows = db.execute(
            """SELECT task_id,mission_id,attempts,max_attempts FROM mission_tasks
               WHERE status='running' AND lease_expires_at_unix < ?""",
            (observed,),
        ).fetchall()
        for row in rows:
            terminal = int(row["attempts"]) >= int(row["max_attempts"])
            delay = min(300, 2 ** max(0, int(row["attempts"]) - 1))
            db.execute(
                """UPDATE mission_tasks SET status=?,available_at_unix=?,lease_owner=NULL,
                   lease_expires_at_unix=NULL,error=?,updated_at_unix=? WHERE task_id=?""",
                ("failed" if terminal else "queued", observed + delay, "worker lease expired", observed, row["task_id"]),
            )
            self._event(db, row["mission_id"], row["task_id"], "task_lease_expired", {"terminal": terminal, "retry_delay_seconds": delay}, observed)
        self._refresh_all(db, observed)
        return len(rows)

    def lease_ready_task(self, worker_id: str, *, mission_id: str | None = None, lease_seconds: int = 900, capabilities: Iterable[str] = ()) -> dict[str, Any] | None:
        observed = now()
        capability_set = {str(item) for item in capabilities}
        with self.transaction() as db:
            self._recover_expired_locked(db, observed)
            rows = db.execute(
                """SELECT t.*,m.max_parallel,m.budget_json FROM mission_tasks t
                   JOIN missions m ON m.mission_id=t.mission_id
                   WHERE t.status='queued' AND t.available_at_unix<=?
                     AND m.status IN ('queued','running')
                     AND (? IS NULL OR t.mission_id=?)
                     AND (SELECT COUNT(*) FROM mission_tasks active
                          WHERE active.mission_id=t.mission_id AND active.status='running') < m.max_parallel
                     AND NOT EXISTS (
                       SELECT 1 FROM mission_dependencies d
                       JOIN mission_tasks parent ON parent.task_id=d.depends_on_task_id
                       WHERE d.task_id=t.task_id AND parent.status!='completed'
                     )
                   ORDER BY t.priority DESC,t.ordinal,t.created_at_unix""",
                (observed, mission_id, mission_id),
            ).fetchall()
            selected = None
            for row in rows:
                payload = decode(row["payload_json"], {})
                required = {str(item) for item in payload.get("required_capabilities", [])}
                if required and not required.issubset(capability_set):
                    continue
                budget = decode(row["budget_json"], {})
                maximum_attempts = int(budget.get("max_task_attempts", 10_000))
                total_attempts = int(db.execute(
                    "SELECT COALESCE(SUM(attempts),0) AS total FROM mission_tasks WHERE mission_id=?",
                    (row["mission_id"],),
                ).fetchone()["total"])
                if total_attempts >= maximum_attempts:
                    db.execute("UPDATE missions SET status='failed',error=?,updated_at_unix=? WHERE mission_id=?", ("mission task-attempt budget exhausted", observed, row["mission_id"]))
                    continue
                selected = row
                break
            if selected is None:
                self._mark_dependency_blockers(db, observed)
                self._refresh_all(db, observed)
                return None
            expires = observed + max(30, min(int(lease_seconds), 86_400))
            updated = db.execute(
                """UPDATE mission_tasks SET status='running',attempts=attempts+1,
                   lease_owner=?,lease_expires_at_unix=?,updated_at_unix=?
                   WHERE task_id=? AND status='queued'""",
                (worker_id, expires, observed, selected["task_id"]),
            )
            if updated.rowcount != 1:
                return None
            db.execute("UPDATE missions SET status='running',updated_at_unix=? WHERE mission_id=?", (observed, selected["mission_id"]))
            self._event(db, selected["mission_id"], selected["task_id"], "task_leased", {"worker_id": worker_id, "lease_expires_at_unix": expires}, observed)
            row = db.execute("SELECT * FROM mission_tasks WHERE task_id=?", (selected["task_id"],)).fetchone()
            return self._task_public(db, row)

    def heartbeat(self, task_id: str, worker_id: str, *, progress: float | None = None, lease_seconds: int = 900, note: str = "") -> dict[str, Any]:
        observed = now()
        expires = observed + max(30, min(int(lease_seconds), 86_400))
        with self.transaction() as db:
            row = db.execute("SELECT mission_id FROM mission_tasks WHERE task_id=? AND status='running' AND lease_owner=?", (task_id, worker_id)).fetchone()
            if row is None:
                raise PermissionError("worker does not hold the active task lease")
            normalized = None if progress is None else max(0.0, min(float(progress), 0.99))
            db.execute("UPDATE mission_tasks SET lease_expires_at_unix=?,progress=COALESCE(?,progress),updated_at_unix=? WHERE task_id=?", (expires, normalized, observed, task_id))
            self._event(db, row["mission_id"], task_id, "task_heartbeat", {"progress": normalized, "note": str(note)[:500]}, observed)
        return self.get_task(task_id)

    def complete_task(self, task_id: str, worker_id: str, result: Mapping[str, Any], *, artifacts: Sequence[Mapping[str, Any]] = (), decision: Mapping[str, Any] | None = None) -> dict[str, Any]:
        observed = now()
        with self.transaction() as db:
            row = db.execute("SELECT mission_id,status FROM mission_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row["status"] == "completed":
                return self.get_task(task_id)
            owned = db.execute("SELECT mission_id FROM mission_tasks WHERE task_id=? AND status='running' AND lease_owner=?", (task_id, worker_id)).fetchone()
            if owned is None:
                raise PermissionError("worker does not hold the active task lease")
            mission_id_value = str(owned["mission_id"])
            db.execute("UPDATE mission_tasks SET status='completed',result_json=?,error=NULL,progress=1,lease_owner=NULL,lease_expires_at_unix=NULL,updated_at_unix=? WHERE task_id=?", (encode(dict(result)), observed, task_id))
            for artifact in artifacts:
                self._insert_artifact(db, mission_id_value, task_id, artifact)
            if decision:
                self._insert_decision(db, mission_id_value, task_id, decision)
            self._event(db, mission_id_value, task_id, "task_completed", {"result_sha256": digest(dict(result)), "artifact_count": len(artifacts)}, observed)
            self._mark_dependency_blockers(db, observed)
            self._refresh_mission(db, mission_id_value, observed)
        return self.get_task(task_id)

    def fail_task(self, task_id: str, worker_id: str, error: str, *, retry_delay_seconds: int = 30, terminal: bool = False) -> dict[str, Any]:
        observed = now()
        with self.transaction() as db:
            current = db.execute("SELECT * FROM mission_tasks WHERE task_id=?", (task_id,)).fetchone()
            if current is None:
                raise KeyError(task_id)
            if current["status"] in TERMINAL_TASK_STATES:
                return self._task_public(db, current)
            if current["status"] != "running" or current["lease_owner"] != worker_id:
                raise PermissionError("worker does not hold the active task lease")
            exhausted = int(current["attempts"]) >= int(current["max_attempts"])
            final = bool(terminal or exhausted)
            delay = max(0, min(int(retry_delay_seconds), 86_400))
            db.execute("UPDATE mission_tasks SET status=?,error=?,available_at_unix=?,lease_owner=NULL,lease_expires_at_unix=NULL,updated_at_unix=? WHERE task_id=?", ("failed" if final else "queued", str(error)[:4000], observed + delay, observed, task_id))
            self._event(db, current["mission_id"], task_id, "task_failed" if final else "task_retry_scheduled", {"error": str(error)[:1000], "retry_delay_seconds": delay}, observed)
            self._mark_dependency_blockers(db, observed)
            self._refresh_mission(db, str(current["mission_id"]), observed)
        return self.get_task(task_id)

    def pause(self, mission_id: str) -> dict[str, Any]:
        return self._set_state(mission_id, "paused")

    def resume(self, mission_id: str) -> dict[str, Any]:
        with self.transaction() as db:
            mission = db.execute("SELECT status FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
            if mission is None:
                raise KeyError(mission_id)
            if mission["status"] not in {"paused", "failed"}:
                raise ValueError("only paused or failed missions can be resumed")
            observed = now()
            db.execute("UPDATE missions SET status='queued',error=NULL,updated_at_unix=? WHERE mission_id=?", (observed, mission_id))
            db.execute("UPDATE mission_tasks SET status='queued',error=NULL,available_at_unix=?,updated_at_unix=? WHERE mission_id=? AND status IN ('blocked','failed') AND attempts<max_attempts", (observed, observed, mission_id))
            self._event(db, mission_id, None, "mission_resumed", {}, observed)
        return self.get_mission(mission_id)

    def cancel(self, mission_id: str) -> dict[str, Any]:
        with self.transaction() as db:
            mission = db.execute("SELECT status FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
            if mission is None:
                raise KeyError(mission_id)
            if mission["status"] in TERMINAL_MISSION_STATES:
                return self.get_mission(mission_id)
            observed = now()
            db.execute("UPDATE missions SET status='cancelled',updated_at_unix=? WHERE mission_id=?", (observed, mission_id))
            db.execute("UPDATE mission_tasks SET status='cancelled',lease_owner=NULL,lease_expires_at_unix=NULL,updated_at_unix=? WHERE mission_id=? AND status NOT IN ('completed','failed','cancelled')", (observed, mission_id))
            self._event(db, mission_id, None, "mission_cancelled", {}, observed)
        return self.get_mission(mission_id)

    def _set_state(self, mission_id: str, status: str) -> dict[str, Any]:
        with self.transaction() as db:
            mission = db.execute("SELECT status FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
            if mission is None:
                raise KeyError(mission_id)
            if mission["status"] in TERMINAL_MISSION_STATES:
                raise ValueError("terminal mission cannot change state")
            observed = now()
            db.execute("UPDATE missions SET status=?,updated_at_unix=? WHERE mission_id=?", (status, observed, mission_id))
            self._event(db, mission_id, None, f"mission_{status}", {}, observed)
        return self.get_mission(mission_id)

    def set_result_summary(self, mission_id: str, summary: str, artifact_manifest_sha256: str | None = None) -> None:
        with self.transaction() as db:
            db.execute("UPDATE missions SET result_summary=?,artifact_manifest_sha256=?,updated_at_unix=? WHERE mission_id=?", (str(summary), artifact_manifest_sha256, now(), mission_id))

    @staticmethod
    def _insert_artifact(db: sqlite3.Connection, mission_id: str, task_id: str | None, artifact: Mapping[str, Any]) -> None:
        db.execute(
            """INSERT OR IGNORE INTO mission_artifacts(
              artifact_id,mission_id,task_id,relative_path,media_type,bytes,sha256,label,created_at_unix
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                str(artifact["artifact_id"]), mission_id, task_id,
                str(artifact["relative_path"]), str(artifact.get("media_type") or "application/octet-stream"),
                int(artifact.get("bytes") or 0), str(artifact["sha256"]),
                str(artifact.get("label") or ""), int(artifact.get("created_at_unix") or now()),
            ),
        )

    @staticmethod
    def _insert_decision(db: sqlite3.Connection, mission_id: str, task_id: str, decision: Mapping[str, Any]) -> None:
        material = {
            "mission_id": mission_id,
            "task_id": task_id,
            "summary": str(decision.get("summary") or ""),
            "options": list(decision.get("options") or []),
            "decision": str(decision.get("decision") or ""),
            "evidence": list(decision.get("evidence") or []),
            "confidence": max(0.0, min(float(decision.get("confidence", 0.0)), 1.0)),
            "blockers": list(decision.get("blockers") or []),
        }
        value = digest(material)
        db.execute("INSERT INTO mission_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("decision_" + value[:24], mission_id, task_id, material["summary"], encode(material["options"]), material["decision"], encode(material["evidence"]), material["confidence"], encode(material["blockers"]), value, now()))

    def _mark_dependency_blockers(self, db: sqlite3.Connection, observed: int) -> None:
        rows = db.execute(
            """SELECT DISTINCT child.task_id,child.mission_id FROM mission_tasks child
               JOIN mission_dependencies d ON d.task_id=child.task_id
               JOIN mission_tasks parent ON parent.task_id=d.depends_on_task_id
               WHERE child.status='queued' AND parent.status IN ('failed','cancelled','blocked')"""
        ).fetchall()
        for row in rows:
            db.execute("UPDATE mission_tasks SET status='blocked',error=?,updated_at_unix=? WHERE task_id=?", ("dependency did not complete", observed, row["task_id"]))
            self._event(db, row["mission_id"], row["task_id"], "task_blocked", {"reason": "dependency did not complete"}, observed)

    def _refresh_all(self, db: sqlite3.Connection, observed: int) -> None:
        for row in db.execute("SELECT mission_id FROM missions").fetchall():
            self._refresh_mission(db, str(row["mission_id"]), observed)

    def _refresh_mission(self, db: sqlite3.Connection, mission_id: str, observed: int) -> None:
        mission = db.execute("SELECT status,deadline_unix,created_at_unix,budget_json FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
        if mission is None or mission["status"] in {"paused", "cancelled"}:
            return
        budget = decode(mission["budget_json"], {})
        deadline = mission["deadline_unix"]
        runtime_limit = int(budget.get("max_runtime_seconds", 0))
        if deadline and int(deadline) < observed:
            db.execute("UPDATE missions SET status='failed',error=?,updated_at_unix=? WHERE mission_id=?", ("mission deadline exceeded", observed, mission_id))
            return
        if runtime_limit and observed - int(mission["created_at_unix"]) > runtime_limit:
            db.execute("UPDATE missions SET status='failed',error=?,updated_at_unix=? WHERE mission_id=?", ("mission runtime budget exceeded", observed, mission_id))
            return
        states = [str(row["status"]) for row in db.execute("SELECT status FROM mission_tasks WHERE mission_id=?", (mission_id,)).fetchall()]
        if states and all(state == "completed" for state in states):
            status = "completed"
        elif states and all(state in TERMINAL_TASK_STATES for state in states):
            status = "failed" if any(state in {"failed", "blocked"} for state in states) else "cancelled"
        elif any(state == "running" for state in states):
            status = "running"
        else:
            status = "queued"
        db.execute("UPDATE missions SET status=?,updated_at_unix=? WHERE mission_id=?", (status, observed, mission_id))

    def _task_public(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        task_id = str(row["task_id"])
        dependencies = [str(item["depends_on_task_id"]) for item in db.execute("SELECT depends_on_task_id FROM mission_dependencies WHERE task_id=? ORDER BY depends_on_task_id", (task_id,)).fetchall()]
        return {
            "task_id": task_id, "mission_id": row["mission_id"], "ordinal": row["ordinal"],
            "title": row["title"], "objective": row["objective"], "kind": row["kind"],
            "status": row["status"], "priority": row["priority"], "model_lane": row["model_lane"],
            "reasoning_rounds": row["reasoning_rounds"], "max_attempts": row["max_attempts"],
            "attempts": row["attempts"], "timeout_seconds": row["timeout_seconds"],
            "payload": decode(row["payload_json"], {}), "acceptance_criteria": decode(row["acceptance_json"], []),
            "required_artifacts": decode(row["required_artifacts_json"], []), "result": decode(row["result_json"], None),
            "error": row["error"], "progress": row["progress"], "available_at_unix": row["available_at_unix"],
            "lease_owner": row["lease_owner"], "lease_expires_at_unix": row["lease_expires_at_unix"],
            "depends_on": dependencies, "created_at_unix": row["created_at_unix"], "updated_at_unix": row["updated_at_unix"],
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM mission_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            return self._task_public(db, row)

    def get_mission(self, mission_id: str, *, include_events: bool = True) -> dict[str, Any]:
        with self.connect() as db:
            mission = db.execute("SELECT * FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
            if mission is None:
                raise KeyError(mission_id)
            tasks = [self._task_public(db, row) for row in db.execute("SELECT * FROM mission_tasks WHERE mission_id=? ORDER BY ordinal", (mission_id,)).fetchall()]
            artifacts = [dict(row) for row in db.execute("SELECT * FROM mission_artifacts WHERE mission_id=? ORDER BY created_at_unix,relative_path", (mission_id,)).fetchall()]
            decisions = []
            for row in db.execute("SELECT * FROM mission_decisions WHERE mission_id=? ORDER BY created_at_unix,decision_id", (mission_id,)).fetchall():
                value = dict(row)
                value["options"] = decode(value.pop("options_json"), [])
                value["evidence"] = decode(value.pop("evidence_json"), [])
                value["blockers"] = decode(value.pop("blockers_json"), [])
                decisions.append(value)
            events = []
            if include_events:
                for row in db.execute("SELECT * FROM mission_events WHERE mission_id=? ORDER BY sequence", (mission_id,)).fetchall():
                    value = dict(row)
                    value["payload"] = decode(value.pop("payload_json"), {})
                    events.append(value)
            total = len(tasks)
            completed = sum(item["status"] == "completed" for item in tasks)
            running = sum(item["status"] == "running" for item in tasks)
            failed = sum(item["status"] in {"failed", "blocked"} for item in tasks)
            return {
                "schema": "pocket.mission.snapshot.v1",
                "mission_id": mission["mission_id"], "idempotency_key": mission["idempotency_key"],
                "principal_id": mission["principal_id"], "tenant_id": mission["tenant_id"],
                "title": mission["title"], "objective": mission["objective"], "status": mission["status"],
                "max_parallel": mission["max_parallel"], "budget": decode(mission["budget_json"], {}),
                "deadline_unix": mission["deadline_unix"], "plan_sha256": mission["plan_sha256"],
                "result_summary": mission["result_summary"], "artifact_manifest_sha256": mission["artifact_manifest_sha256"],
                "error": mission["error"], "created_at_unix": mission["created_at_unix"], "updated_at_unix": mission["updated_at_unix"],
                "progress": {"total": total, "completed": completed, "running": running, "failed_or_blocked": failed, "fraction": round(completed / max(total, 1), 6)},
                "tasks": tasks, "artifacts": artifacts, "decisions": decisions, "events": events,
            }

    def list_missions(self, *, tenant_id: str | None = None, principal_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 500))
        conditions, parameters = [], []
        if tenant_id is not None:
            conditions.append("tenant_id=?")
            parameters.append(str(tenant_id))
        if principal_id is not None:
            conditions.append("principal_id=?")
            parameters.append(str(principal_id))
        query = "SELECT mission_id FROM missions"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at_unix DESC LIMIT ?"
        parameters.append(bounded)
        with self.connect() as db:
            ids = [str(row["mission_id"]) for row in db.execute(query, tuple(parameters)).fetchall()]
        return [self.get_mission(item, include_events=False) for item in ids]
