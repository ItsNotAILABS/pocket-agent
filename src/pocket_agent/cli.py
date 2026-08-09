"""CLI: pocket-agent — Prime Agent command parity + capsules/RAH extras.

Useful commands (Prime-compatible surface):
  pocket-agent                         # interactive session in cwd
  pocket-agent agents                  # browse sessions
  pocket-agent attach <agent>          # reattach
  pocket-agent --resume <path|id>      # resume saved session
  pocket-agent status                  # background service state
  pocket-agent doctor [--fix]          # inspect/repair
  pocket-agent schedule ...            # heartbeats / timed re-entry
  pocket-agent shutdown [--force]
  pocket-agent capsule ...             # WASM multi-sandbox (beyond Prime)
  pocket-agent update [--force]        # reinstall hint / git pull
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _j(obj: Any, limit: int = 20000) -> str:
    return json.dumps(obj, indent=2, default=str)[:limit]


def _print_sessions(items: List[Dict[str, Any]]) -> None:
    if not items:
        print("(no sessions)")
        return
    print(f"{'ID':16}  {'STATUS':12}  {'TURNS':5}  {'PROJECT':12}  GOAL")
    for s in items:
        sid = (s.get("id") or "")[:16]
        st = (s.get("status") or "")[:12]
        turns = str(s.get("turns") or 0)
        proj = (s.get("project") or "")[:12]
        goal = (s.get("goal") or "")[:48]
        print(f"{sid:16}  {st:12}  {turns:5}  {proj:12}  {goal}")


def _slash_help() -> str:
    return """
In-session slash commands (type at >>> prompt):
  /help              this help
  /login             auth hint (use POCKET host ACCESS / provider keys)
  /goal <text>       set persistent goal
  /goal progress <t> update progress
  /goal done         complete active goal
  /refine <evidence> continual harness refine (never rewrites base prompt)
  /heartbeat [note]  pulse session (daemon continuity)
  /autonomous on|off [max_turns=N]
  /capsule [reason]  spin WASM capsule (default untrusted_eval)
  /capsule reasons   list 20 agent capsule reasons
  /agents            list sessions
  /status            service status
  /detach            leave session running for attach later
  /quit /exit        leave REPL (session stays if detached)
""".strip()


def _run_repl(
    *,
    session_id: Optional[str] = None,
    project: str = "default",
    resume_id: Optional[str] = None,
) -> int:
    from pocket_agent import Agent
    from pocket_agent import daemon
    from pocket_agent import capsules

    daemon.ensure_service()
    if resume_id:
        rec = daemon.resume(resume_id)
        if not rec:
            print(f"resume failed: {resume_id}", file=sys.stderr)
            return 1
        session_id = rec["id"]
        project = rec.get("project") or project
        print(f"Resumed {session_id}  status={rec.get('status')}  goal={rec.get('goal') or '—'}")
    elif session_id:
        rec = daemon.attach(session_id)
        if not rec:
            print(f"attach failed: {session_id}", file=sys.stderr)
            return 1
        project = rec.get("project") or project
        print(f"Attached {session_id}  status={rec.get('status')}")
    else:
        rec = daemon.start_session(project=project, cwd=os.getcwd())
        session_id = rec["id"]
        print(f"POCKET Agent session {session_id}")
        print(f"cwd: {os.getcwd()}")
        print("Warning: executes model/Python with your user permissions — not a security sandbox.")
        print("Use /capsule for WASM isolation. /login for providers. /help for commands.")
        print()

    agent = Agent(cwd=os.getcwd(), project=project)
    agent.session = daemon.attach(session_id) or agent.session

    while True:
        try:
            line = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            daemon.detach(session_id)
            print(f"Detached. Reattach: pocket-agent attach {session_id}")
            return 0
        raw = line.strip()
        if not raw:
            continue

        # slash commands
        if raw.startswith("/"):
            parts = raw.split(maxsplit=2)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            rest = parts[2] if len(parts) > 2 else ""

            if cmd in ("/quit", "/exit"):
                daemon.detach(session_id)
                print(f"Detached {session_id}")
                return 0
            if cmd == "/help":
                print(_slash_help())
                continue
            if cmd == "/login":
                print(
                    "Providers: set OPENAI_API_KEY / ANTHROPIC_API_KEY / XAI_API_KEY, or run POCKET host\n"
                    "  python -m pocket serve  → desk login (ACCESS.txt)\n"
                    "Subscription-style seats: use POCKET founder/market edition on the host."
                )
                continue
            if cmd == "/goal":
                if arg == "done":
                    print(_j(daemon.update_goal(session_id, status="completed")))
                elif arg == "progress":
                    print(_j(daemon.update_goal(session_id, progress=rest or "")))
                elif arg:
                    text = (arg + (" " + rest if rest else "")).strip()
                    print(_j(daemon.set_goal(session_id, text)))
                    agent.harness.set_goal(text)
                else:
                    rec = daemon.attach(session_id) or {}
                    print(_j({"goal": rec.get("goal"), "goals": rec.get("goals")}))
                continue
            if cmd == "/refine":
                ev = (arg + (" " + rest if rest else "")).strip() or "session refine"
                print(_j(agent.harness.refine(evidence=ev)))
                continue
            if cmd == "/heartbeat":
                note = (arg + (" " + rest if rest else "")).strip()
                print(_j(daemon.heartbeat(session_id, note=note)))
                continue
            if cmd == "/autonomous":
                on = arg.lower() in ("on", "1", "true", "yes", "")
                if arg.lower() in ("off", "0", "false", "no"):
                    on = False
                mt = 32
                if rest.startswith("max_turns="):
                    try:
                        mt = int(rest.split("=", 1)[1])
                    except Exception:
                        pass
                print(_j(daemon.set_autonomous(session_id, enabled=on, max_turns=mt)))
                continue
            if cmd == "/capsule":
                if arg == "reasons":
                    for rsn in capsules.list_reasons():
                        print(f"{rsn['id']:22}  {rsn['improves']}")
                else:
                    reason = arg or "untrusted_eval"
                    out = capsules.spin(reason=reason, tier="512MB")
                    print(_j(out))
                continue
            if cmd == "/agents":
                _print_sessions(daemon.list_sessions())
                continue
            if cmd == "/status":
                print(_j(daemon.service_status()))
                continue
            if cmd == "/detach":
                print(_j(daemon.detach(session_id)))
                return 0
            print(f"unknown slash command: {cmd}  (try /help)")
            continue

        daemon.append_turn(session_id, "user", raw)
        daemon.heartbeat(session_id)
        res = agent.run(raw)
        print(res.summary[:12000])
        daemon.append_turn(session_id, "assistant", res.summary[:8000], tokens=len(res.summary) // 4)
        rec = daemon.attach(session_id) or {}
        if str(rec.get("status") or "").startswith("limit_"):
            print(f"\n[autonomous limit] status={rec.get('status')} — review gates; limit ≠ success")
            break
    return 0


def main(argv: Optional[list[str]] = None) -> None:
    argv = list(argv if argv is not None else sys.argv[1:])

    # Global flags before subcommand (prime-agent --resume id)
    resume_id = None
    if "--resume" in argv:
        i = argv.index("--resume")
        if i + 1 < len(argv):
            resume_id = argv[i + 1]
            del argv[i : i + 2]
        else:
            print("--resume requires path|id", file=sys.stderr)
            sys.exit(2)

    p = argparse.ArgumentParser(
        prog="pocket-agent",
        description="POCKET Agent — RLM + continual harness + RAH + WASM capsules (long-running)",
    )
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    # default interactive when no cmd
    sub.add_parser("tui", help="Interactive session in cwd (default)")
    r = sub.add_parser("run", help="One-shot task")
    r.add_argument("task", nargs="+")
    r.add_argument("--project", default="default")
    r.add_argument("--autonomous", action="store_true")

    sub.add_parser("repl", help="Alias for interactive session")
    sub.add_parser("agents", help="Browse running, idle, and saved sessions")
    a = sub.add_parser("attach", help="Reattach to a running/detached session")
    a.add_argument("agent")
    sub.add_parser("status", help="Inspect background service state")
    d = sub.add_parser("doctor", help="Inspect or repair background services")
    d.add_argument("--fix", action="store_true")
    u = sub.add_parser("update", help="Update pocket-agent")
    u.add_argument("--force", action="store_true")
    sh = sub.add_parser("shutdown", help="Stop sessions and background service")
    sh.add_argument("--force", action="store_true")

    sch = sub.add_parser("schedule", help="Heartbeats and timed re-entry")
    sch_sub = sch.add_subparsers(dest="scmd")
    sch_sub.add_parser("list")
    sa = sch_sub.add_parser("add")
    sa.add_argument("--session", default="")
    sa.add_argument("--every", type=float, default=3600, help="seconds")
    sa.add_argument("--note", default="")
    sd = sch_sub.add_parser("disable")
    sd.add_argument("id")
    sch_sub.add_parser("fire", help="Fire due schedules now")

    c = sub.add_parser("capsule", help="WASM multi-sandbox capsules")
    csub = c.add_subparsers(dest="ccmd")
    csub.add_parser("reasons")
    csub.add_parser("list")
    sp = csub.add_parser("spin")
    sp.add_argument("--tier", default="512MB")
    sp.add_argument("--webgpu", action="store_true")
    sp.add_argument("--reason", default="untrusted_eval")
    sp.add_argument("--label", default="")
    tm = csub.add_parser("terminate")
    tm.add_argument("id")

    sub.add_parser("version")

    # No args → interactive (prime-agent style)
    if not argv and not resume_id:
        sys.exit(_run_repl())

    args = p.parse_args(argv)

    if args.version or args.cmd == "version":
        from pocket_agent import __version__

        print(f"pocket-agent {__version__}")
        return

    if resume_id or args.cmd in (None, "tui", "repl"):
        sys.exit(_run_repl(resume_id=resume_id))

    from pocket_agent import daemon

    if args.cmd == "agents":
        _print_sessions(daemon.list_sessions())
        return

    if args.cmd == "attach":
        sys.exit(_run_repl(session_id=args.agent))

    if args.cmd == "status":
        print(_j(daemon.service_status()))
        return

    if args.cmd == "doctor":
        print(_j(daemon.doctor(fix=bool(args.fix))))
        return

    if args.cmd == "shutdown":
        print(_j(daemon.service_shutdown(force=bool(args.force))))
        return

    if args.cmd == "update":
        root = Path(__file__).resolve().parents[2]
        print("Update options:")
        print(f"  cd {root} && git pull && pip install -e .")
        print("  # or re-run: curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.sh | sh")
        if args.force and (root / ".git").is_dir():
            import subprocess

            subprocess.run(["git", "-C", str(root), "pull", "--ff-only"], check=False)
            subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(root)], check=False)
            print("forced update attempted")
        return

    if args.cmd == "schedule":
        if args.scmd == "list" or not args.scmd:
            print(_j(daemon.list_schedules()))
            return
        if args.scmd == "add":
            print(
                _j(
                    daemon.schedule_add(
                        session_id=args.session,
                        every_seconds=args.every,
                        note=args.note,
                    )
                )
            )
            return
        if args.scmd == "disable":
            print(_j(daemon.disable_schedule(args.id)))
            return
        if args.scmd == "fire":
            print(_j(daemon.fire_due_schedules()))
            return
        sch.print_help()
        return

    if args.cmd == "run":
        from pocket_agent import Agent

        daemon.ensure_service()
        sess = daemon.start_session(
            project=args.project,
            cwd=os.getcwd(),
            goal=" ".join(args.task)[:200],
            autonomous=bool(args.autonomous),
        )
        agent = Agent(project=args.project)
        agent.session = sess
        task = " ".join(args.task)
        daemon.append_turn(sess["id"], "user", task)
        res = agent.run(task)
        print(res.summary)
        daemon.append_turn(sess["id"], "assistant", res.summary[:8000])
        daemon.heartbeat(sess["id"], note="run complete")
        sys.exit(0 if res.ok else 1)

    if args.cmd == "capsule":
        from pocket_agent import capsules

        if args.ccmd == "reasons":
            for rsn in capsules.list_reasons():
                print(f"{rsn['id']:22}  {rsn['title']:22}  {rsn['improves']}")
            return
        if args.ccmd == "list":
            print(_j(capsules.list_capsules()))
            return
        if args.ccmd == "spin":
            print(
                _j(
                    capsules.spin(
                        tier=args.tier,
                        webgpu=bool(args.webgpu),
                        reason=args.reason,
                        label=args.label,
                    )
                )
            )
            return
        if args.ccmd == "terminate":
            print(_j(capsules.terminate(args.id)))
            return
        c.print_help()
        return

    p.print_help()


if __name__ == "__main__":
    main()
