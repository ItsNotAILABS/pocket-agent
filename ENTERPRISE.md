# POCKET Agent — Enterprise Integration Guide

POCKET Agent is designed to sit behind an authenticated product/control plane rather than act as the identity system itself.

## Recommended deployment model

```text
Client / Voice / IDE / Automation
            |
            v
      POCKET Host/API
  auth · tenant · policy · audit
            |
            v
       POCKET Agent
 goals · RLM · RAH · schedules
 capsules · execution receipts
            |
            v
 Repository / tools / governed runtimes
```

## Integration contract

Use `pocket.family.v1` for cross-product execution requests. Preserve:

- `request_id`
- principal/user identity
- tenant/organization scope
- session identifier
- agent identifier
- requested action
- bounded payload
- policy/capability metadata

Responses should include or reference a `pocket.execution-receipt.v1` object.

## Enterprise controls to enforce upstream

- organization membership and roles;
- API-key/service-account lifecycle;
- SSO/MFA when required;
- per-tenant quotas and rate limits;
- allowlisted tools and repositories;
- data residency and retention policy;
- centralized secret handling;
- deployment approval and environment promotion;
- audit export and incident response.

## Agent-side controls

- budget autonomous runs by turns/time/resources;
- use capsules for untrusted or isolation-sensitive work;
- retain explicit cwd/project boundaries;
- make destructive actions reviewable;
- keep session lifecycle observable through status/doctor/attach;
- emit bounded operational receipts;
- preserve cancellation and operator stop paths.

## Evaluation checklist

A design-partner evaluation should exercise at minimum:

1. authenticated host → agent request;
2. tenant identity preserved across the hop;
3. denied action produces a bounded denial record;
4. detach and reattach to a long-running session;
5. scheduled/heartbeat re-entry;
6. capsule execution for an untrusted task;
7. cancellation during execution;
8. receipt digest verification;
9. attempted cross-tenant/session access denial;
10. secret redaction in logs and receipts;
11. upgrade/rollback procedure;
12. operator recovery after an interrupted process.

## Commercialization boundary

The open-source agent runtime can remain MIT while hosted enterprise value is provided by the surrounding POCKET platform: managed identity, organizations, policy, audit storage, deployment, support, observability, usage metering and governed integrations.
