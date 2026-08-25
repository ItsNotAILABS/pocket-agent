"""Secure HTTP routes that turn one large objective into many durable tasks."""
from __future__ import annotations

import argparse
import json
import os
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from .mission_auth import MissionApiKeyRegistry
from .mission_decomposer import AutoMissionProgramService, AuroMissionDecomposer
from .mission_http import MissionApiError, _loopback
from .mission_http_secure import SecureMissionHandler
from .mission_program import MissionProgramService


class AutoSecureMissionHandler(SecureMissionHandler):
    def _required_scope(self) -> str:
        path = urlsplit(self.path).path
        if path == "/v1/missions/auto/plan":
            return "mission:plan"
        if path == "/v1/missions/auto":
            return "mission:create"
        return super()._required_scope()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {"/v1/missions/auto", "/v1/missions/auto/plan"}:
            return super().do_POST()
        self._authorize()
        principal, tenant = self._identity()
        body = self._body()
        service = self.get_service()
        if service.council_client is None:
            raise MissionApiError(
                503,
                "auro_council_unavailable",
                "Automatic mission decomposition requires the AURO council client.",
            )
        decomposer = AuroMissionDecomposer(service.council_client)
        if path.endswith("/plan"):
            result = decomposer.decompose(
                str(body.get("objective") or ""),
                title=str(body.get("title") or ""),
                context=str(body.get("context") or ""),
                profile=body.get("reasoning_profile") or "deep",
                requested_deliverables=list(body.get("deliverables") or []),
            )
            return self._json(200, result.to_dict())
        auto = AutoMissionProgramService(service, decomposer)
        return self._json(
            201,
            auto.create_from_objective(
                body,
                principal_id=principal,
                tenant_id=tenant,
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve scoped POCKET Agent missions with AURO decomposition"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("POCKET_MISSION_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("POCKET_MISSION_PORT", "8792")),
    )
    args = parser.parse_args()
    registry = MissionApiKeyRegistry.from_env()
    if not registry.configured:
        raise SystemExit("A mission API key registry is required")
    if not _loopback(args.host) and not registry.configured:
        raise SystemExit("A configured registry is required for non-loopback binding")
    AutoSecureMissionHandler.registry = registry
    AutoSecureMissionHandler.service = MissionProgramService.from_env()
    server = ThreadingHTTPServer((args.host, args.port), AutoSecureMissionHandler)
    print(
        json.dumps(
            {
                "service": "pocket-agent-auto-missions",
                "host": args.host,
                "port": server.server_port,
                "automatic_decomposition": True,
                "caller_selected_identity_headers": False,
            },
            sort_keys=True,
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
