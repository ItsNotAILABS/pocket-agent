import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from http.server import ThreadingHTTPServer

from pocket_agent.mission_http import MissionHandler
from test_mission_program_v2 import build_service


def request_json(base_url, path, *, token=None, principal=None, tenant=None, body=None):
    headers = {}
    if token:
        headers["authorization"] = f"Bearer {token}"
    if principal:
        headers["x-pocket-principal-id"] = principal
    if tenant:
        headers["x-pocket-tenant-id"] = tenant
    data = None
    method = "GET"
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
        method = "POST"
    request = Request(base_url + path, data=data, headers=headers, method=method)
    with urlopen(request, timeout=10) as response:
        payload = response.read()
        return response.status, response.headers, json.loads(payload) if payload else None


def test_http_api_requires_auth_identity_and_preserves_tenant_boundaries(tmp_path):
    service, _ = build_service(tmp_path)
    token = "t" * 40
    MissionHandler.service = service
    MissionHandler.api_token = token
    server = ThreadingHTTPServer(("127.0.0.1", 0), MissionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, _, health = request_json(base, "/health")
        assert status == 200
        assert health["status"] == "live"

        try:
            request_json(
                base,
                "/v1/missions",
                principal="user-a",
                tenant="tenant-a",
            )
        except HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("mission API unexpectedly allowed missing token")

        try:
            request_json(base, "/v1/missions", token=token)
        except HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("mission API unexpectedly allowed missing identity")

        request_body = {
            "title": "HTTP mission",
            "reasoning_profile": "quick",
            "objectives": [
                {"id": "one", "objective": "Analyze one requirement"},
                {"id": "two", "objective": "Implement another requirement"},
            ],
            "deliverables": ["deliverables/http-report.md"],
        }
        status, _, created = request_json(
            base,
            "/v1/missions",
            token=token,
            principal="user-a",
            tenant="tenant-a",
            body=request_body,
        )
        assert status == 201
        mission_id = created["mission"]["mission_id"]

        status, _, listed = request_json(
            base,
            "/v1/missions",
            token=token,
            principal="user-a",
            tenant="tenant-a",
        )
        assert status == 200
        assert [item["mission_id"] for item in listed["missions"]] == [mission_id]

        try:
            request_json(
                base,
                f"/v1/missions/{mission_id}",
                token=token,
                principal="user-b",
                tenant="tenant-b",
            )
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("cross-tenant mission access unexpectedly succeeded")

        status, _, result = request_json(
            base,
            f"/v1/missions/{mission_id}/run",
            token=token,
            principal="user-a",
            tenant="tenant-a",
            body={"max_tasks": 100, "time_budget_seconds": 120},
        )
        assert status == 200
        assert result["mission"]["status"] == "completed"

        status, _, artifacts = request_json(
            base,
            f"/v1/missions/{mission_id}/artifacts",
            token=token,
            principal="user-a",
            tenant="tenant-a",
        )
        assert status == 200
        paths = {item["relative_path"] for item in artifacts["artifacts"]}
        assert "deliverables/http-report.md" in paths
        assert "mission-artifacts.zip" in paths
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.store.close()
        MissionHandler.service = None
        MissionHandler.api_token = ""
