"""Operator CLI for POCKET Agent durable missions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .mission_service import MissionService
from .mission_worker import MissionWorker


def _load_json(path: str | None, default: Any) -> Any:
    if not path:
        return default
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value


def _identity(args: argparse.Namespace) -> tuple[str, str]:
    principal = (
        getattr(args, "principal_id", None)
        or os.getenv("POCKET_PRINCIPAL_ID")
        or ""
    )
    tenant = (
        getattr(args, "tenant_id", None)
        or os.getenv("POCKET_TENANT_ID")
        or ""
    )
    if not principal or not tenant:
        raise SystemExit(
            "principal and tenant are required through --principal-id/--tenant-id "
            "or POCKET_PRINCIPAL_ID/POCKET_TENANT_ID"
        )
    return principal, tenant


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pocket-mission",
        description=(
            "Create and operate durable dependency-aware POCKET Agent missions"
        ),
    )
    parser.add_argument("--principal-id")
    parser.add_argument("--tenant-id")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create a mission")
    create.add_argument("--objective", required=True)
    create.add_argument("--title", default="POCKET Agent mission")
    create.add_argument("--tasks-json")
    create.add_argument("--budget-json")
    create.add_argument("--deliverable", action="append", default=[])
    create.add_argument("--max-parallel", type=int, default=3)
    create.add_argument("--deadline-unix", type=int)
    create.add_argument("--idempotency-key")

    listing = commands.add_parser("list", help="List visible missions")
    listing.add_argument("--limit", type=int, default=50)

    show = commands.add_parser("show", help="Inspect one mission")
    show.add_argument("mission_id")

    run = commands.add_parser("run", help="Run a bounded mission burst")
    run.add_argument("mission_id")
    run.add_argument("--worker-id", default="pocket-mission-cli")
    run.add_argument("--max-tasks", type=int, default=20)
    run.add_argument("--time-budget-seconds", type=int, default=300)
    run.add_argument("--capability", action="append", default=[])

    for action in ("pause", "resume", "cancel"):
        command = commands.add_parser(action, help=f"{action.title()} a mission")
        command.add_argument("mission_id")

    commands.add_parser("status", help="Show mission subsystem status")

    worker = commands.add_parser("worker", help="Run the durable worker")
    worker.add_argument("--worker-id", default="pocket-mission-worker")
    worker.add_argument("--mission-id")
    worker.add_argument("--max-tasks-per-burst", type=int, default=8)
    worker.add_argument("--time-budget-seconds", type=int, default=240)
    worker.add_argument("--idle-seconds", type=float, default=2.0)
    worker.add_argument("--capability", action="append", default=[])
    worker.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = MissionService.from_env()

    if args.command == "status":
        return _print(service.status())

    if args.command == "worker":
        worker = MissionWorker(
            service,
            worker_id=args.worker_id,
            max_tasks_per_burst=args.max_tasks_per_burst,
            time_budget_seconds=args.time_budget_seconds,
            idle_seconds=args.idle_seconds,
            capabilities=args.capability,
        )
        if args.once:
            return _print(worker.run_once(args.mission_id))
        return worker.run_forever(args.mission_id)

    principal, tenant = _identity(args)
    if args.command == "create":
        tasks = _load_json(args.tasks_json, None)
        if tasks is not None and not isinstance(tasks, list):
            raise SystemExit("--tasks-json must contain a JSON array")
        budget = _load_json(args.budget_json, {})
        if not isinstance(budget, dict):
            raise SystemExit("--budget-json must contain a JSON object")
        return _print(
            service.create(
                {
                    "objective": args.objective,
                    "title": args.title,
                    "tasks": tasks,
                    "budget": budget,
                    "deliverables": args.deliverable,
                    "max_parallel": args.max_parallel,
                    "deadline_unix": args.deadline_unix,
                    "idempotency_key": args.idempotency_key,
                },
                principal_id=principal,
                tenant_id=tenant,
            )
        )
    if args.command == "list":
        return _print(
            {
                "schema": "pocket.mission-list.v1",
                "missions": service.list(
                    principal_id=principal,
                    tenant_id=tenant,
                    limit=args.limit,
                ),
            }
        )
    if args.command == "show":
        return _print(
            service.get(
                args.mission_id,
                principal_id=principal,
                tenant_id=tenant,
            )
        )
    if args.command == "run":
        return _print(
            service.run(
                args.mission_id,
                {
                    "worker_id": args.worker_id,
                    "max_tasks": args.max_tasks,
                    "time_budget_seconds": args.time_budget_seconds,
                    "capabilities": args.capability,
                },
                principal_id=principal,
                tenant_id=tenant,
            )
        )
    if args.command in {"pause", "resume", "cancel"}:
        return _print(
            service.transition(
                args.mission_id,
                args.command,
                principal_id=principal,
                tenant_id=tenant,
            )
        )
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
