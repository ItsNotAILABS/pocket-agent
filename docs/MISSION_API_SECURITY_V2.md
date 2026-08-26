# POCKET Agent Mission API Security v2

The production-oriented mission API uses a digest-only API-key registry. A caller cannot choose its own `principal_id` or `tenant_id` through HTTP headers. Its bearer token resolves to one key identity, one principal, one tenant, and explicit scopes.

## Registry format

Create a JSON document outside the repository:

```json
{
  "schema": "pocket.mission-api-keys.v1",
  "keys": [
    {
      "key_id": "customer-a-production",
      "token_sha256": "REPLACE_WITH_SHA256_OF_RANDOM_TOKEN",
      "principal_id": "user-123",
      "tenant_id": "organization-456",
      "scopes": [
        "mission:plan",
        "mission:create",
        "mission:read",
        "mission:run",
        "mission:control",
        "artifact:read",
        "worker:read"
      ],
      "roles": ["owner"],
      "expires_at_unix": null,
      "disabled": false
    }
  ]
}
```

Generate the document without retaining raw tokens in it:

```python
import json
from pocket_agent.mission_auth import key_registry_document

raw_token = "use-a-cryptographically-random-secret-here"
document = key_registry_document([
    {
        "key_id": "customer-a-production",
        "token": raw_token,
        "principal_id": "user-123",
        "tenant_id": "organization-456",
        "scopes": [
            "mission:plan",
            "mission:create",
            "mission:read",
            "mission:run",
            "mission:control",
            "artifact:read",
            "worker:read",
        ],
        "roles": ["owner"],
    }
])
open("/secure/path/mission-api-keys.json", "w").write(json.dumps(document, indent=2))
print(raw_token)  # deliver through your secret manager; do not commit it
```

The resulting registry stores only SHA-256 token digests.

## Start the secure service

```bash
export POCKET_MISSION_API_KEYS_FILE=/secure/path/mission-api-keys.json
export POCKET_MISSION_DB=state/pocket-agent-missions.sqlite3
export POCKET_MISSION_ARTIFACT_ROOT=state/mission-artifacts
export AURO_COUNCIL_URL=http://127.0.0.1:8090/v1/council/respond
export AURO_API_TOKEN=replace-with-scoped-auro-token

python -m pocket_agent.mission_http_secure --host 127.0.0.1 --port 8792
```

The secure entrypoint refuses startup when no key registry is configured.

## Scopes

| Scope | Allows |
|---|---|
| `mission:plan` | Compile a mission DAG without storing it |
| `mission:create` | Create a durable mission |
| `mission:read` | List and inspect missions owned by the key identity |
| `mission:run` | Advance a mission through a bounded execution burst |
| `mission:control` | Pause, resume, or cancel a mission |
| `artifact:read` | List and download authorized mission artifacts |
| `worker:read` | Read mission runtime and worker status |
| `*` | All mission API scopes; reserve for tightly controlled operators |

A key without `mission:run` cannot execute a mission even when it can read that mission. A key for another tenant cannot read the mission.

## Requests

```bash
curl -s http://127.0.0.1:8792/v1/missions \
  -H "authorization: Bearer $POCKET_CUSTOMER_TOKEN" \
  -H "content-type: application/json" \
  -d @examples/multi_task_mission.json
```

No principal or tenant headers are accepted by the secure entrypoint. Identity comes from the key registry.

## Key rotation

The file-backed registry reloads when its modification time changes.

1. Create a new random token and add its digest as a second key.
2. Distribute the new raw token through the secret manager.
3. Confirm successful authenticated requests with the new key ID.
4. Mark the old key `disabled: true` or remove it.
5. Preserve a rotation receipt outside the repository.

Raw tokens and token digests must never be written to mission receipts, logs, prompts, or artifacts. Responses may expose the non-secret `key_id` for correlation.

## Deployment boundary

A digest registry is suitable for service tokens and small controlled deployments. A broad multi-user product should normally place this service behind POCKET identity, Cloudflare Access, or another authenticated gateway that issues short-lived, revocable identity assertions.

This code does not establish:

- resistance to distributed brute-force attacks without an upstream rate limiter;
- hardware-backed key custody;
- SSO, SCIM, or customer-managed identity;
- multi-region revocation propagation;
- production load testing;
- an externally deployed TLS endpoint.

Those remain deployment responsibilities and separate evidence gates.
