"""Recursive Language Model control helpers — prompt-as-variable + subagents."""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass
class RLMResult:
    ok: bool
    goal: str
    output: str
    agent: str = "child"
    ms: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


def _host_or_local(goal: str, *, mode: str = "plan") -> RLMResult:
    t0 = time.time()
    # Prefer POCKET job path
    try:
        from pocket.jobs import create_job, get as get_job, save as save_job
        from pocket.worker import process_one

        job = create_job(goal[:12000], name="rlm-child", mode=mode)
        job["_harness_inner"] = True
        save_job(job)
        deadline = time.time() + 120
        process_one()
        while time.time() < deadline:
            j = get_job(job["id"])
            if j and j.get("status") in ("done", "failed", "cancelled"):
                out = str(j.get("result") or j.get("error") or "")
                return RLMResult(
                    ok=j.get("status") == "done",
                    goal=goal,
                    output=out[:20000],
                    agent=mode,
                    ms=int((time.time() - t0) * 1000),
                    meta={"job_id": job["id"], "engine": j.get("engine")},
                )
            process_one()
            time.sleep(0.2)
        return RLMResult(ok=False, goal=goal, output="timeout", ms=int((time.time() - t0) * 1000))
    except Exception:
        pass
    # Local stub — structured plan so offline still works
    out = (
        f"## RLM child result\n\n**Goal:** {goal[:500]}\n\n"
        "1. Clarify scope\n2. Act with tools/capsules as needed\n3. Return evidence\n"
        "_(host not on PYTHONPATH — stub child)_\n"
    )
    return RLMResult(ok=True, goal=goal, output=out, agent="stub", ms=int((time.time() - t0) * 1000))


def rlm(goal: str, *, mode: str = "plan", background: bool = False) -> RLMResult:
    """Spawn a child agent and return its result (Prime-style programmatic subagent)."""
    if background:
        # fire and forget file marker
        from pathlib import Path
        import uuid

        p = Path.home() / ".pocket" / "agent" / "bg"
        p.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex[:10]
        (p / f"{rid}.goal").write_text(goal, encoding="utf-8")
        return RLMResult(ok=True, goal=goal, output=f"background:{rid}", agent="bg", meta={"id": rid})
    return _host_or_local(goal, mode=mode)


def rlm_map(
    goals: Sequence[str],
    *,
    max_workers: int = 4,
    mode: str = "plan",
) -> List[RLMResult]:
    """Parallel child agents — intermediate results stay in the list (program vars)."""
    goals = [g for g in goals if (g or "").strip()]
    if not goals:
        return []
    workers = max(1, min(int(max_workers or 4), len(goals), 16))
    out: List[RLMResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(rlm, g, mode=mode) for g in goals]
        for f in concurrent.futures.as_completed(futs):
            try:
                out.append(f.result())
            except Exception as e:
                out.append(RLMResult(ok=False, goal="", output=str(e)))
    # stable-ish order by goal text
    out.sort(key=lambda r: r.goal)
    return out


def synthesize(results: Sequence[RLMResult]) -> str:
    lines = ["# RLM synthesis", ""]
    for r in results:
        lines.append(f"## {'OK' if r.ok else 'FAIL'} · {r.agent} · {r.ms}ms")
        lines.append(f"**Goal:** {r.goal[:300]}")
        lines.append(r.output[:3000])
        lines.append("")
    return "\n".join(lines)
