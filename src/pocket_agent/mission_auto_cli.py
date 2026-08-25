"""CLI for AURO-assisted decomposition of one large objective."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from .mission_decomposer import AutoMissionProgramService, AuroMissionDecomposer
from .mission_program import MissionProgramService


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pocket-agent-auto-mission",
        description="Decompose one large objective into a durable multi-workstream mission",
    )
    parser.add_argument("objective", nargs="?")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--profile", default="deep")
    parser.add_argument("--deliverable", action="append", default=[])
    parser.add_argument("--principal", default="operator")
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--decompose-only", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.request:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("request file must contain a JSON object")
    else:
        if not args.objective:
            raise ValueError("provide an objective or --request")
        request = {
            "title": args.title,
            "objective": args.objective,
            "context": args.context,
            "reasoning_profile": args.profile,
            "deliverables": args.deliverable,
        }

    base = MissionProgramService.from_env()
    if base.council_client is None:
        raise RuntimeError("AURO council client is not configured")
    decomposer = AuroMissionDecomposer(base.council_client)
    try:
        if args.decompose_only:
            result = decomposer.decompose(
                str(request.get("objective") or ""),
                title=str(request.get("title") or ""),
                context=str(request.get("context") or ""),
                profile=request.get("reasoning_profile") or "deep",
                requested_deliverables=list(request.get("deliverables") or []),
            )
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return 0
        service = AutoMissionProgramService(base, decomposer)
        result = service.create_from_objective(
            request,
            principal_id=args.principal,
            tenant_id=args.tenant,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        base.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
