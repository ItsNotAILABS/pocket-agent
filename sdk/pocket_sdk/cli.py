"""pocket-sdk CLI."""

from __future__ import annotations

import json
import sys

from pocket_sdk import Pocket


def main(argv: list[str] | None = None) -> None:
    argv = list(argv or sys.argv[1:])
    p = Pocket()
    if not argv or argv[0] in ("-h", "--help"):
        print("pocket-sdk health|identity|protocols|economy|login|sessions")
        return
    cmd = argv[0]
    if cmd == "health":
        print(json.dumps(p.health(), indent=2, default=str))
    elif cmd == "identity":
        print(json.dumps(p.identity(), indent=2, default=str))
    elif cmd == "protocols":
        print(json.dumps(p.protocols(), indent=2, default=str)[:8000])
    elif cmd == "economy":
        print(json.dumps(p.economy(), indent=2, default=str)[:8000])
    elif cmd == "login":
        print(json.dumps(p.login(), indent=2, default=str))
    else:
        print(f"unknown: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
