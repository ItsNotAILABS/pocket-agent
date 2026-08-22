# POCKET Agent Alpha

**Channel:** Alpha  
**Version family:** 0.2.x  
**Audience:** technical founders, platform teams, security-conscious builders, and controlled enterprise design partners.

POCKET Agent is the long-running execution plane of the POCKET family. It owns durable goals, recurrent work, RLM control, RAH fan-out, schedules, session continuity, governed capsules, and execution receipts.

## What Alpha means

Alpha is usable software with explicit operational limits. It is not a claim of GA maturity, an SLA, or third-party certification.

Current Alpha goals:

- reproducible install and upgrade paths;
- deterministic protocol contracts;
- clear operator and security boundaries;
- bounded autonomous execution;
- recoverable sessions;
- auditable execution receipts;
- compatibility with POCKET Host and Pocket Voice;
- CI validation on supported Python versions.

## Enterprise evaluation gates

| Area | Alpha requirement |
|---|---|
| Identity | preserve principal, tenant, session, request and agent identity from host envelopes |
| Execution | distinguish local host execution from capsule-isolated execution |
| Authorization | privileged actions must be routed through explicit capabilities/policy |
| Receipts | emit `pocket.execution-receipt.v1` evidence with timestamps, status and digest |
| Data | workspace/session state must stay scoped to the active user/project boundary |
| Secrets | credentials are runtime configuration and must not be written into receipts or logs |
| Recovery | detach/attach/resume behavior documented and tested |
| Change safety | repository writes remain reviewable; destructive changes require explicit operator control |
| Observability | status/doctor/session state are available without exposing private reasoning |
| Compatibility | `pocket.family.v1` remains provider-neutral and versioned |

## Supported family role

```text
Pocket Voice
  conversation timing + voice context
          |
          v
POCKET Host
  principal + tenant + routing + policy
          |
          v
POCKET Agent
  long-running execution + schedules + RAH + capsules + receipts
```

POCKET Agent does not own customer identity, billing, organization membership, or conversational VAD. Those remain upstream responsibilities.

## Evidence states

- `alpha-source` — code and contracts are present.
- `alpha-ci` — automated tests/import/compile gates have passed.
- `alpha-integrated` — POCKET Host ↔ Agent compatibility tests have passed.
- `alpha-design-partner` — controlled tenant/auth/audit/recovery evaluation has passed in a hosted or managed environment.

Do not infer a higher state from a lower one.

## Known Alpha limitations

- model-generated commands can execute with the current user's permissions outside capsules;
- WASM capsules improve isolation but do not make every host interaction safe by default;
- enterprise SSO, centralized policy administration, and SLA-backed hosted operations belong to the POCKET Host/product layer;
- protocol receipts are operational evidence, not proofs of model correctness;
- long-running autonomy remains budgeted and interruptible rather than unbounded.

## Release criteria

Before a tagged Alpha release:

1. package version and metadata agree;
2. Python 3.11 and 3.12 CI pass;
3. family protocol tests pass;
4. install + doctor smoke tests pass on at least one clean environment;
5. execution receipt schema remains backward compatible or is version-bumped;
6. security and support docs reflect the current behavior;
7. no claim of hosted availability is made without deployment evidence.
