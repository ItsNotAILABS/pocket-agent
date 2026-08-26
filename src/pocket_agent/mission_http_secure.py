"""Production-oriented mission HTTP entrypoint with scoped identity grants.

Unlike the compatibility mission HTTP handler, this service never accepts a
caller-selected principal or tenant header. The bearer token resolves to one
principal, one tenant, and an explicit set of scopes through a digest-only key
registry.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from .mission_auth import MissionApiKeyRegistry, MissionIdentityGrant
from .mission_http import MissionApiError, MissionHandler, _loopback
from .mission_program import MissionProgramService


class SecureMissionHandler(MissionHandler):
    registry: MissionApiKeyRegistry | None = None

    def _required_scope(self) -> str:
        path = urlsplit(self.path).path
        method = self.command.upper()
        if method == "GET":
            if path == "/v1/missions/runtime":
                return "worker:read"
            if "/artifacts" in path:
                return "artifact:read"
            return "mission:read"
        if path == "/v1/missions/plan":
            return "mission:plan"
        if path == "/v1/missions":
            return "mission:create"
        if path.endswith("/run"):
            return "mission:run"
        if path.endswith(("/pause", "/resume", "/cancel")):
            return "mission:control"
        return "mission:read"

    def _authorize(self) -> None:
        if self.registry is None:
            raise MissionApiError(
                503,
                "identity_registry_unavailable",
                "Mission identity registry is unavailable.",
            )
        try:
            self.identity_grant = self.registry.authenticate(
                self.headers.get("authorization", ""),
                required_scope=self._required_scope(),
            )
        except PermissionError as exc:
            raise MissionApiError(401, "mission_api_key_denied", str(exc)) from exc

    def _identity(self) -> tuple[str, str]:
        grant: MissionIdentityGrant | None = getattr(self, "identity_grant", None)
        if grant is None:
            raise MissionApiError(
                401,
                "identity_required",
                "A scoped mission identity grant is required.",
            )
        return self.get_service()._identity(grant.principal_id, grant.tenant_id)

    def _bytes(self, status: int, media_type: str, data: bytes) -> None:
        # Preserve the base security headers and include only non-secret key ID
        # for request correlation. Raw bearer tokens and digests never appear.
        grant: MissionIdentityGrant | None = getattr(self, "identity_grant", None)
        if grant is not None:
            self.send_response(status)
            headers = {
                "content-type": media_type,
                "content-length": str(len(data)),
                "cache-control": "no-store",
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
                "referrer-policy": "no-referrer",
                "x-request-id": getattr(self, "request_id", ""),
                "x-pocket-mission-api-version": "2026-08-25-secure",
                "x-pocket-key-id": grant.key_id,
            }
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            if data:
                self.wfile.write(data)
            return
        super()._bytes(status, media_type, data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve tenant-bound POCKET Agent missions with scoped API keys"
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
        raise SystemExit(
            "Configure POCKET_MISSION_API_KEYS_FILE or POCKET_MISSION_API_KEYS_JSON before starting the secure mission API."
        )
    if not _loopback(args.host) and not registry.configured:
        raise SystemExit("A configured identity registry is required for non-loopback binding")

    SecureMissionHandler.registry = registry
    SecureMissionHandler.service = MissionProgramService.from_env()
    server = ThreadingHTTPServer((args.host, args.port), SecureMissionHandler)
    print(
        json.dumps(
            {
                "service": "pocket-agent-missions-secure",
                "host": args.host,
                "port": server.server_port,
                "identity_registry": registry.public(),
                "caller_selected_identity_headers": False,
            },
            sort_keys=True,
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
