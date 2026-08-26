"""Supervised long-running worker for durable POCKET Agent missions."""
from __future__ import annotations

import argparse
import json
import signal
import time
from typing import Any, Sequence

from .mission_service import MissionService


class MissionWorker:
    """Execute ready mission tasks in bounded, restart-safe bursts."""

    def __init__(
        self,
        service: MissionService,
        *,
        worker_id: str,
        max_tasks_per_burst: int = 8,
        time_budget_seconds: int = 240,
        idle_seconds: float = 2.0,
        capabilities: Sequence[str] = (),
    ) -> None:
        self.service = service
        self.worker_id = str(worker_id)
        self.max_tasks_per_burst = max(
            1, min(int(max_tasks_per_burst), 100)
        )
        self.time_budget_seconds = max(
            1, min(int(time_budget_seconds), 3600)
        )
        self.idle_seconds = max(0.1, min(float(idle_seconds), 60.0))
        self.capabilities = tuple(str(item) for item in capabilities)
        self.stopping = False

    def stop(self, *_args: Any) -> None:
        self.stopping = True

    def run_once(self, mission_id: str | None = None) -> dict[str, Any]:
        if mission_id:
            missions = [self.service.store.get_mission(mission_id)]
        else:
            missions = self.service.store.list_missions(limit=500)
        candidates = [
            mission
            for mission in missions
            if mission["status"] in {"queued", "running"}
        ]
        results = []
        for mission in candidates:
            if self.stopping:
                break
            outcome = self.service.orchestrator.run_burst(
                mission["mission_id"],
                worker_id=self.worker_id,
                max_tasks=self.max_tasks_per_burst,
                time_budget_seconds=self.time_budget_seconds,
                capabilities=self.capabilities,
            )
            results.append(
                {
                    "mission_id": mission["mission_id"],
                    "status": outcome["mission"]["status"],
                    "tasks_executed": outcome["tasks_executed"],
                    "failures_or_retries": outcome[
                        "task_failures_or_retries"
                    ],
                    "elapsed_ms": outcome["elapsed_ms"],
                }
            )
        return {
            "schema": "pocket.mission-worker.pass.v1",
            "worker_id": self.worker_id,
            "candidate_missions": len(candidates),
            "results": results,
            "stopping": self.stopping,
        }

    def run_forever(self, mission_id: str | None = None) -> None:
        while not self.stopping:
            report = self.run_once(mission_id)
            print(json.dumps(report, sort_keys=True), flush=True)
            if not report["results"] or all(
                item["tasks_executed"] == 0
                for item in report["results"]
            ):
                time.sleep(self.idle_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the POCKET Agent durable mission worker"
    )
    parser.add_argument("--worker-id", default="pocket-mission-worker")
    parser.add_argument("--mission-id")
    parser.add_argument("--max-tasks-per-burst", type=int, default=8)
    parser.add_argument("--time-budget-seconds", type=int, default=240)
    parser.add_argument("--idle-seconds", type=float, default=2.0)
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Worker capability; repeat for multiple values",
    )
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    worker = MissionWorker(
        MissionService.from_env(),
        worker_id=args.worker_id,
        max_tasks_per_burst=args.max_tasks_per_burst,
        time_budget_seconds=args.time_budget_seconds,
        idle_seconds=args.idle_seconds,
        capabilities=args.capability,
    )
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    if args.once:
        print(
            json.dumps(
                worker.run_once(args.mission_id),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        worker.run_forever(args.mission_id)


if __name__ == "__main__":
    main()
