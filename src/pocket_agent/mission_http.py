"""Tenant-bound HTTP API for POCKET Agent mission programs.

The API exposes planning, durable creation, bounded execution, lifecycle
controls, status, and artifact retrieval. It requires a bearer token when
configured and refuses non-loopback startup without one. Human identity and
tenant scope remain explicit request attributes; a shared anonymous namespace
is not used for remote operation.
"""
from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .mission_program import MissionProgramPlanner, MissionProgramService
from .mission_service import MissionAuthorizationError


API_VERSION = "2026-08-25"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_DOWNLOAD_BYTES = 128 * 1024 * 1024


def _loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


def _bearer(header: str, expected: str) -> bool:
    return bool(
        expected
        and header.startswith("Bearer ")
        and hmac.compare_digest(header[7:], expected)
    )


class MissionApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        self.status = int(status)
        self.code = str(code)
        self.message = str(message)
        super().__init__(message)


class MissionHandler(BaseHTTPRequestHandler):
    service: MissionProgramService | None = None
    api_token: str = ""
    server_version = "PocketAgentMissions/2"

    @classmethod
    def get_service(cls) -> MissionProgramService:
        if cls.service is None:
            cls.service = MissionProgramService.from_env()
        return cls.service

    def handle_one_request(self) -> None:
        self.request_id = "req_" + uuid.uuid4().hex
        try:
            super().handle_one_request()
        except MissionApiError as exc:
            self._error(exc.status, exc.code, exc.message)
        except MissionAuthorizationError as exc:
            self._error(403, "mission_forbidden", str(exc))
        except FileNotFoundError as exc:
            self._error(404, "not_found", str(exc))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(400, "invalid_request", str(exc)[:1000])
        except Exception as exc:
            debug = os.getenv("POCKET_MISSION_DEBUG", "").lower() in {"1", "true", "yes"}
            self._error(
                500,
                "internal_error",
                str(exc)[:1000] if debug else "The mission request could not be completed.",
            )

    def do_OPTIONS(self) -> None:
        return self._bytes(204, "text/plain; charset=utf-8", b"")

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/health", "/v1/health/live"}:
            return self._json(
                200,
                {
                    "ok": True,
                    "status": "live",
                    "service": "pocket-agent-missions",
                    "api_version": API_VERSION,
                },
            )
        self._authorize()
        service = self.get_service()
        principal, tenant = self._identity()

        if path == "/v1/missions/runtime":
            return self._json(200, service.status())
        if path == "/v1/missions":
            query = parse_qs(urlsplit(self.path).query)
            status = query.get("status", [None])[0]
            limit = max(1, min(int(query.get("limit", ["100"])[0]), 1000))
            missions = service.store.list_missions(
                principal_id=None if principal == "system-admin" else principal,
                tenant_id=tenant,
                status=status,
                limit=limit,
            )
            return self._json(
                200,
                {
                    "schema": "pocket.mission-list.v2",
                    "count": len(missions),
                    "missions": missions,
                },
            )

        match = re.fullmatch(r"/v1/missions/([^/]+)", path)
        if match:
            mission_id = unquote(match.group(1))
            return self._json(
                200,
                service.authorized(
                    mission_id,
                    principal_id=principal,
                    tenant_id=tenant,
                ),
            )

        match = re.fullmatch(r"/v1/missions/([^/]+)/artifacts", path)
        if match:
            mission_id = unquote(match.group(1))
            service.authorized(
                mission_id,
                principal_id=principal,
                tenant_id=tenant,
            )
            return self._json(
                200,
                {
                    "schema": "pocket.mission-artifact-list.v2",
                    "mission_id": mission_id,
                    "artifacts": [
                        item.to_dict()
                        for item in service.artifacts.list(mission_id)
                    ],
                },
            )

        match = re.fullmatch(r"/v1/missions/([^/]+)/artifacts/(.+)", path)
        if match:
            mission_id = unquote(match.group(1))
            relative_path = unquote(match.group(2))
            service.authorized(
                mission_id,
                principal_id=principal,
                tenant_id=tenant,
            )
            artifact = service.artifacts.resolve(mission_id, relative_path)
            if not artifact.is_file():
                raise MissionApiError(404, "artifact_not_found", "Artifact does not exist.")
            size = artifact.stat().st_size
            if size > MAX_ARTIFACT_DOWNLOAD_BYTES:
                raise MissionApiError(413, "artifact_too_large", "Artifact exceeds API download limit.")
            media_type = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
            return self._bytes(200, media_type, artifact.read_bytes())

        raise MissionApiError(404, "route_not_found", "The requested route does not exist.")

    def do_POST(self) -> None:
        self._authorize()
        service = self.get_service()
        principal, tenant = self._identity()
        path = urlsplit(self.path).path
        body = self._body()

        if path == "/v1/missions/plan":
            values = body.get("objectives") or body.get("workstreams")
            if not isinstance(values, list):
                raise MissionApiError(400, "workstreams_required", "objectives or workstreams must be an array")
            program = MissionProgramPlanner().plan(
                objectives=values,
                title=str(body.get("title") or "POCKET Agent mission program"),
                objective=(str(body["objective"]) if body.get("objective") else None),
                deliverables=list(body.get("deliverables") or []),
                profile=body.get("reasoning_profile") or body.get("profile") or "standard",
                principal_id=principal,
                tenant_id=tenant,
                max_parallel=body.get("max_parallel"),
                budget=dict(body.get("budget") or {}),
                deadline_unix=body.get("deadline_unix"),
                idempotency_key=body.get("idempotency_key"),
            )
            return self._json(200, program.to_dict())

        if path == "/v1/missions":
            return self._json(
                201,
                service.create_program(
                    body,
                    principal_id=principal,
                    tenant_id=tenant,
                ),
            )

        match = re.fullmatch(
            r"/v1/missions/([^/]+)/(run|pause|resume|cancel)",
            path,
        )
        if match:
            mission_id = unquote(match.group(1))
            action = match.group(2)
            service.authorized(
                mission_id,
                principal_id=principal,
                tenant_id=tenant,
            )
            if action == "run":
                return self._json(
                    200,
                    service.run(
                        mission_id,
                        body,
                        principal_id=principal,
                        tenant_id=tenant,
                    ),
                )
            reason = str(body.get("reason") or "operator request")[:1000]
            if action == "pause":
                service.store.pause_mission(mission_id, reason)
            elif action == "resume":
                service.store.resume_mission(mission_id)
            else:
                service.store.cancel_mission(mission_id, reason)
            return self._json(200, service.store.get_mission(mission_id))

        raise MissionApiError(404, "route_not_found", "The requested route does not exist.")

    def _authorize(self) -> None:
        if self.api_token and not _bearer(
            self.headers.get("authorization", ""),
            self.api_token,
        ):
            raise MissionApiError(401, "api_token_required", "A valid mission API bearer token is required.")

    def _identity(self) -> tuple[str, str]:
        principal = self.headers.get("x-pocket-principal-id", "").strip()
        tenant = self.headers.get("x-pocket-tenant-id", "").strip()
        if not principal or not tenant:
            raise MissionApiError(
                400,
                "identity_required",
                "x-pocket-principal-id and x-pocket-tenant-id are required.",
            )
        return self.get_service()._identity(principal, tenant)

    def _body(self) -> dict[str, Any]:
        content_type = self.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise MissionApiError(415, "json_required", "Content-Type must be application/json.")
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError as exc:
            raise MissionApiError(400, "invalid_content_length", "Content-Length must be an integer.") from exc
        if length <= 0:
            raise MissionApiError(400, "body_required", "A JSON object is required.")
        if length > MAX_REQUEST_BYTES:
            raise MissionApiError(413, "body_too_large", "Request body exceeds the API limit.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise MissionApiError(400, "object_required", "Request JSON must be an object.")
        return value

    def _error(self, status: int, code: str, message: str) -> None:
        if getattr(self, "wfile", None) is None or self.wfile.closed:
            return
        self._json(
            status,
            {
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(self, "request_id", None),
                }
            },
        )

    def _json(self, status: int, payload: Any) -> None:
        self._bytes(
            status,
            "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        )

    def _bytes(self, status: int, media_type: str, data: bytes) -> None:
        self.send_response(status)
        headers = {
            "content-type": media_type,
            "content-length": str(len(data)),
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "x-request-id": getattr(self, "request_id", ""),
            "x-pocket-mission-api-version": API_VERSION,
        }
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if data:
            self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve POCKET Agent missions over HTTP")
    parser.add_argument("--host", default=os.getenv("POCKET_MISSION_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("POCKET_MISSION_PORT", "8792")))
    args = parser.parse_args()

    token = os.getenv("POCKET_MISSION_API_TOKEN", "")
    if not _loopback(args.host) and len(token) < 32:
        raise SystemExit(
            "POCKET_MISSION_API_TOKEN with at least 32 characters is required for non-loopback binding"
        )
    MissionHandler.api_token = token
    MissionHandler.service = MissionProgramService.from_env()
    server = ThreadingHTTPServer((args.host, args.port), MissionHandler)
    print(
        json.dumps(
            {
                "service": "pocket-agent-missions",
                "host": args.host,
                "port": server.server_port,
                "auth_required": bool(token),
                "started_at_unix": time.time(),
            },
            sort_keys=True,
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
