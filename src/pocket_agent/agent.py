"""Top-level Agent — RLM REPL surface + harness + capsules + auto-RAH."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pocket_agent.harness import Harness, BASE_SYSTEM
from pocket_agent import rlm as rlm_mod
from pocket_agent import capsules as cap_mod
from pocket_agent import messaging, daemon


@dataclass
class RunResult:
    ok: bool
    summary: str
    meta: Dict[str, Any]


class Agent:
    def __init__(self, cwd: str = ".", project: str = "default", session: dict | None = None) -> None:
        self.cwd = cwd
        self.harness = Harness(project=project)
        self.session = session or daemon.start_session(project=project, cwd=cwd)

    def run(self, code_or_prompt: str) -> RunResult:
        """Execute control program or natural language task."""
        text = (code_or_prompt or "").strip()
        if not text:
            return RunResult(ok=False, summary="empty", meta={})

        # Natural language → try host auto-RAH / job, else RLM map heuristic
        if not _looks_like_code(text):
            return self._run_task(text)

        # Programmatic REPL subset
        env = self._globals()
        try:
            exec(compile(text, "<pocket-agent>", "exec"), env, env)
            summary = str(env.get("result") or env.get("out") or "ok")
            self.harness.remember(f"ran code block ({len(text)} chars)")
            daemon.heartbeat(self.session["id"])
            return RunResult(ok=True, summary=summary[:20000], meta={"mode": "repl"})
        except Exception as e:
            return RunResult(
                ok=False,
                summary=f"{e}\n{traceback.format_exc()[-2000:]}",
                meta={"mode": "repl", "error": str(e)},
            )

    def _run_task(self, task: str) -> RunResult:
        # Prefer POCKET host executor (includes auto-RAH)
        try:
            from pocket.jobs import create_job, get as get_job, save as save_job
            from pocket.worker import process_one

            # Auto mode selection: plan default; host may escalate to rah
            job = create_job(task[:20000], name="pocket-agent", mode="plan")
            save_job(job)
            import time

            deadline = time.time() + 300
            process_one()
            while time.time() < deadline:
                j = get_job(job["id"])
                if j and j.get("status") in ("done", "failed", "cancelled"):
                    out = str(j.get("result") or j.get("error") or "")
                    self.harness.refine(evidence=f"task finished status={j.get('status')}")
                    return RunResult(
                        ok=j.get("status") == "done",
                        summary=out[:50000],
                        meta={"job_id": job["id"], "engine": j.get("engine")},
                    )
                process_one()
                time.sleep(0.25)
        except Exception:
            pass

        # Offline: local rlm children if task has bullets
        lines = [ln.strip("-* \t") for ln in task.splitlines() if ln.strip().startswith(("-", "*", "1", "2", "3"))]
        if len(lines) >= 2:
            results = rlm_mod.rlm_map(lines[:8], max_workers=4)
            return RunResult(ok=True, summary=rlm_mod.synthesize(results), meta={"mode": "rlm_map"})
        r = rlm_mod.rlm(task)
        return RunResult(ok=r.ok, summary=r.output, meta={"mode": "rlm"})

    def _globals(self) -> Dict[str, Any]:
        def set_goal(g: str) -> None:
            self.harness.set_goal(g)

        def refine(evidence: str = "", notes: str = "") -> Dict[str, Any]:
            return self.harness.refine(evidence=evidence, notes=notes)

        def capsule_spin(**kw: Any) -> Dict[str, Any]:
            return cap_mod.spin(**kw)

        def rlm(goal: str, **kw: Any):
            return rlm_mod.rlm(goal, **kw)

        def rlm_map(goals, **kw: Any):
            return rlm_mod.rlm_map(goals, **kw)

        return {
            "BASE_SYSTEM": BASE_SYSTEM,
            "harness": self.harness,
            "set_goal": set_goal,
            "refine": refine,
            "remember": self.harness.remember,
            "system_prompt": self.harness.system_prompt,
            "rlm": rlm,
            "rlm_map": rlm_map,
            "synthesize": rlm_mod.synthesize,
            "capsule_spin": capsule_spin,
            "capsule_reasons": cap_mod.list_reasons,
            "capsule_terminate": cap_mod.terminate,
            "send": messaging.send,
            "inbox": messaging.inbox,
            "cwd": self.cwd,
            "result": None,
            "out": None,
        }


def _looks_like_code(text: str) -> bool:
    t = text.strip()
    if "\n" in t and any(k in t for k in ("def ", "import ", "rlm(", "capsule_spin", "set_goal", "refine(")):
        return True
    if t.startswith("rlm(") or t.startswith("capsule_spin") or t.startswith("set_goal"):
        return True
    return False
