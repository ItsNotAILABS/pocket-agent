"""CLI: pocket-agent"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pocket-agent", description="POCKET Agent — RLM + harness + RAH + WASM capsules")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="Run a natural-language task or short program")
    r.add_argument("task", nargs="+", help="Task text")
    r.add_argument("--project", default="default")

    sub.add_parser("repl", help="Interactive control REPL")

    c = sub.add_parser("capsule", help="WASM multi-sandbox capsules")
    csub = c.add_subparsers(dest="ccmd")
    csub.add_parser("reasons", help="List 20 agent use-reasons")
    csub.add_parser("list", help="List capsules")
    sp = csub.add_parser("spin", help="Spin a capsule")
    sp.add_argument("--tier", default="512MB")
    sp.add_argument("--webgpu", action="store_true")
    sp.add_argument("--reason", default="untrusted_eval")
    sp.add_argument("--label", default="")
    tm = csub.add_parser("terminate", help="Terminate capsule")
    tm.add_argument("id")

    sub.add_parser("version", help="Print version")

    args = p.parse_args(argv)
    if args.cmd == "version" or not args.cmd:
        from pocket_agent import __version__

        print(f"pocket-agent {__version__}")
        if not args.cmd:
            p.print_help()
        return

    if args.cmd == "run":
        from pocket_agent import Agent

        agent = Agent(project=args.project)
        res = agent.run(" ".join(args.task))
        print(res.summary)
        sys.exit(0 if res.ok else 1)

    if args.cmd == "repl":
        from pocket_agent import Agent

        agent = Agent()
        print("POCKET Agent REPL — code or natural language. Ctrl+C to exit.")
        print("Helpers: rlm, rlm_map, capsule_spin, refine, set_goal")
        while True:
            try:
                line = input(">>> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line.strip():
                continue
            if line.strip() in ("exit", "quit"):
                break
            res = agent.run(line)
            print(res.summary[:8000])

    if args.cmd == "capsule":
        from pocket_agent import capsules

        if args.ccmd == "reasons":
            for rsn in capsules.list_reasons():
                print(f"{rsn['id']:22}  {rsn['title']:22}  {rsn['improves']}")
            return
        if args.ccmd == "list":
            print(json.dumps(capsules.list_capsules(), indent=2, default=str)[:12000])
            return
        if args.ccmd == "spin":
            out = capsules.spin(
                tier=args.tier,
                webgpu=bool(args.webgpu),
                reason=args.reason,
                label=args.label,
            )
            print(json.dumps(out, indent=2, default=str))
            return
        if args.ccmd == "terminate":
            print(json.dumps(capsules.terminate(args.id), indent=2))
            return
        c.print_help()


if __name__ == "__main__":
    main()
