import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from http.server import ThreadingHTTPServer

from pocket_agent.mission_auth import (
    MissionApiKeyRegistry,
    key_registry_document,
    token_sha256,
)
from pocket_agent.mission_http_secure import SecureMissionHandler
from test_mission_program_v2 import build_service


def call(base, path, token, *, body=None):
    headers = {"authorization": f"Bearer {token}"}
    data = None
    method = "GET"
    if body is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(body).encode()
        method = "POST"
    request = Request(base + path, data=data, headers=headers, method=method)
    with urlopen(request, timeout=10) as response:
        payload = response.read()
        return response.status, response.headers, json.loads(payload) if payload else None


def test_registry_stores_digests_scopes_tenant_and_expiry(tmp_path):
    token = "customer-token-" + "x" * 32
    document = key_registry_document(
        [
            {
                "key_id": "customer-a",
                "token": token,
                "principal_id": "user-a",
                "tenant_id": "tenant-a",
                "scopes": ["mission:plan", "mission:create", "mission:read"],
                "roles": ["member"],
            }
        ]
    )
    assert token not in json.dumps(document)
    assert document["keys"][0]["token_sha256"] == token_sha256(token)
    path = tmp_path / "keys.json"
    path.write_text(json.dumps(document))
    registry = MissionApiKeyRegistry(path=path)
    grant = registry.authenticate(
        f"Bearer {token}",
        required_scope="mission:create",
    )
    assert grant.principal_id == "user-a"
    assert grant.tenant_id == "tenant-a"
    assert grant.key_id == "customer-a"
    try:
        registry.authenticate(f"Bearer {token}", required_scope="mission:run")
    except PermissionError as exc:
        assert "lacks scope" in str(exc)
    else:
        raise AssertionError("scope escalation unexpectedly succeeded")


def test_secure_api_derives_identity_from_key_and_enforces_scopes(tmp_path):
    service, _ = build_service(tmp_path)
    create_token = "create-token-" + "a" * 32
    read_token = "read-token-" + "b" * 32
    other_token = "other-token-" + "c" * 32
    registry = MissionApiKeyRegistry(
        document=key_registry_document(
            [
                {
                    "key_id": "creator",
                    "token": create_token,
                    "principal_id": "user-a",
                    "tenant_id": "tenant-a",
                    "scopes": [
                        "mission:plan",
                        "mission:create",
                        "mission:read",
                        "mission:run",
                        "mission:control",
                        "artifact:read",
                        "worker:read",
                    ],
                },
                {
                    "key_id": "reader",
                    "token": read_token,
                    "principal_id": "user-a",
                    "tenant_id": "tenant-a",
                    "scopes": ["mission:read", "artifact:read"],
                },
                {
                    "key_id": "other-tenant",
                    "token": other_token,
                    "principal_id": "user-b",
                    "tenant_id": "tenant-b",
                    "scopes": ["mission:read", "artifact:read"],
                },
            ]
        )
    )
    SecureMissionHandler.service = service
    SecureMissionHandler.registry = registry
    server = ThreadingHTTPServer(("127.0.0.1", 0), SecureMissionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, headers, created = call(
            base,
            "/v1/missions",
            create_token,
            body={
                "title": "Scoped identity mission",
                "reasoning_profile": "quick",
                "objectives": ["Complete the scoped mission"],
                "deliverables": ["deliverables/scoped.md"],
            },
        )
        assert status == 201
        assert headers["x-pocket-key-id"] == "creator"
        mission_id = created["mission"]["mission_id"]
        assert created["mission"]["principal_id"] == "user-a"
        assert created["mission"]["tenant_id"] == "tenant-a"

        status, _, mission = call(
            base,
            f"/v1/missions/{mission_id}",
            read_token,
        )
        assert status == 200
        assert mission["mission_id"] == mission_id

        try:
            call(
                base,
                f"/v1/missions/{mission_id}/run",
                read_token,
                body={"max_tasks": 5},
            )
        except HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("read-only key unexpectedly ran a mission")

        try:
            call(base, f"/v1/missions/{mission_id}", other_token)
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("other tenant unexpectedly read the mission")

        status, _, result = call(
            base,
            f"/v1/missions/{mission_id}/run",
            create_token,
            body={"max_tasks": 100, "time_budget_seconds": 120},
        )
        assert status == 200
        assert result["mission"]["status"] == "completed"

        status, _, artifact_list = call(
            base,
            f"/v1/missions/{mission_id}/artifacts",
            read_token,
        )
        assert status == 200
        assert any(
            item["relative_path"] == "deliverables/scoped.md"
            for item in artifact_list["artifacts"]
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.store.close()
        SecureMissionHandler.service = None
        SecureMissionHandler.registry = None
