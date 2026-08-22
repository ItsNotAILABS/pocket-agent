<p align="center">
  <img src="assets/pocket-agent-hero.svg" width="100%" alt="POCKET Agent — long-running intelligence" />
</p>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.2.0-10b981?style=flat-square">
  <img alt="python" src="https://img.shields.io/badge/python-3.11+-f59e0b?style=flat-square">
  <img alt="runtime" src="https://img.shields.io/badge/runtime-long--running-8b5cf6?style=flat-square">
  <img alt="protocol" src="https://img.shields.io/badge/protocol-POCKET%20%2B%20NEXUS-2563eb?style=flat-square">
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-3b82f6?style=flat-square"></a>
</p>

# POCKET Agent

**Long-running repository intelligence with durable goals, recursive workers, bounded execution and machine-verifiable receipts.**

POCKET Agent is the execution plane of the POCKET family. It is built for jobs that should survive beyond one prompt: repository audits, implementation runs, scheduled maintenance, research loops, multi-worker decomposition and isolated execution.

```text
Goal + repository
      │
      ▼
Persistent Agent Harness
      │
      ├── RLM control state
      ├── tools + project commands
      ├── recursive agent harnesses (RAH)
      ├── WASM capsules
      ├── schedules / heartbeats
      └── budgets + leases + retries + circuit breakers
      │
      ▼
Artifacts + execution receipt + durable continuation state
```

## Install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/master/install.sh | sh
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/master/install.ps1 | iex
```

Then:

```bash
cd /path/to/project
pocket-agent
```

From source:

```bash
git clone https://github.com/ItsNotAILABS/pocket-agent.git
cd pocket-agent
python -m pip install -e ".[dev]"
pytest -q
pocket-agent doctor --fix
```

## Core product capabilities

| Capability | What it does |
|---|---|
| Persistent sessions | detach and later reattach to the same working state |
| Durable goals | keep objective/progress across turns |
| RLM | represent context as programmable state and tools/workers as callable operations |
| RAH | fan out complete agent harnesses for independent subproblems |
| Continual harness | retain explicit refinements, snapshots and rollback points |
| Schedules | re-enter work periodically without rebuilding context |
| WASM capsules | move isolated work into explicit runspaces |
| Execution budgets | bound time, token, cost, file, subprocess and child-worker usage |
| Idempotency | prevent accidental duplicate execution for retried requests |
| Leases | give long-running work explicit ownership and expiry |
| Retry policy | bounded exponential retry instead of uncontrolled loops |
| Circuit breaker | isolate repeatedly failing dependencies |
| Drift detection | compare declared capability with observed execution behavior |
| Outcome evaluation | require acceptance criteria/evidence before completion |
| Receipts | correlate request, tenant, session, action, runtime and artifacts |

## Five-minute workflow

Start in a repository:

```bash
pocket-agent
```

Set a persistent goal:

```text
/goal Harden the API, add missing tests, and leave the repository releasable.
```

Run bounded autonomous work:

```text
/autonomous
```

Detach:

```text
/detach
```

Reattach later:

```bash
pocket-agent agents
pocket-agent attach <agent>
```

Schedule re-entry:

```bash
pocket-agent schedule add --every 30m --prompt "Continue the active goal when useful work remains."
```

Isolate a task:

```bash
pocket-agent capsule spin --reason untrusted_eval
```

## CLI

```text
pocket-agent
pocket-agent run "audit every API route"
pocket-agent agents
pocket-agent attach <agent>
pocket-agent --resume <path|id>
pocket-agent status
pocket-agent doctor [--fix]
pocket-agent schedule list|add|fire
pocket-agent capsule reasons
pocket-agent capsule spin --reason <id>
pocket-agent update [--force]
pocket-agent shutdown [--force]
```

Session commands:

```text
/goal
/refine
/heartbeat
/autonomous
/capsule
/detach
/help
```

## Resilience primitives

POCKET Agent exposes deterministic runtime helpers for operating long jobs instead of leaving reliability inside prompts.

```python
from pocket_agent import (
    Budget,
    Usage,
    budget_status,
    route_capability,
    evaluate_outcome,
    detect_drift,
    recovery_plan,
)
```

The runtime also contains production-oriented helpers for:

- deterministic request digests;
- idempotency records;
- resource/job leases with expiry;
- bounded retry policies;
- circuit breaker state;
- retry-storm prevention.

These primitives are designed to be stored by the host/runtime layer so retries, restarts and distributed handoffs preserve the same execution identity.

## POCKET family protocol

```python
from pocket_agent import make_envelope, make_receipt

envelope = make_envelope(
    "agent.run",
    {"goal": "audit repository auth boundaries"},
    session_id="session-42",
    principal="user-7",
    tenant="team-acme",
    agent_id="agent-a",
)

receipt = make_receipt(
    envelope,
    status="succeeded",
    runtime_ms=842,
    result_summary="auth audit completed",
).to_dict()
```

Supported family actions:

```text
agent.run
agent.attach
agent.schedule
agent.capsule
```

Receipts preserve request, tenant, session and agent correlation plus runtime and artifact evidence.

## Architecture

<p align="center">
  <img src="assets/pocket-agent-architecture.svg" width="100%" alt="POCKET Agent architecture" />
</p>

```text
Pocket Voice
conversation timing + voice context
        │
        ▼
POCKET Host
identity + teams + policy + routing + approvals
        │
        ▼
POCKET Agent
long-running execution + schedules + RAH + capsules
        │
        ├── MatDaemon bounded compute
        ├── CAPSULA isolated runtime
        ├── Medina Memory durable outcomes
        └── NEXUS ecosystem handoffs
```

## Execution lifecycle

A production request follows an explicit lifecycle:

```text
accept
  -> validate scope
  -> evaluate policy
  -> reserve budget / lease
  -> execute
  -> evaluate acceptance criteria
  -> persist artifacts
  -> emit receipt
  -> release lease
  -> handoff or persist continuation state
```

Failures use bounded recovery:

```text
retry_once -> alternate capability -> handoff -> stop_and_report
```

Repeated dependency failure opens a circuit instead of creating an infinite retry loop.

## Install slices

| Slice | macOS / Linux | Windows |
|---|---|---|
| Agent | `curl -fsSL …/install/agent.sh \| sh` | `irm …/install/agent.ps1 \| iex` |
| SDK | `curl -fsSL …/install/sdk.sh \| sh` | `irm …/install/sdk.ps1 \| iex` |
| Skills | `curl -fsSL …/install/skills.sh \| sh` | `irm …/install/skills.ps1 \| iex` |
| Knowledge | `curl -fsSL …/install/knowledge.sh \| sh` | `irm …/install/knowledge.ps1 \| iex` |
| Capsules | `curl -fsSL …/install/capsules.sh \| sh` | `irm …/install/capsules.ps1 \| iex` |
| Mail | `curl -fsSL …/install/mail.sh \| sh` | `irm …/install/mail.ps1 \| iex` |
| Full family | `curl -fsSL …/install/plug.sh \| sh` | `irm …/install/plug.ps1 \| iex` |

See [`install/README.md`](install/README.md) and [`install/slices.json`](install/slices.json).

## Repository map

```text
src/pocket_agent/
├── agent.py
├── daemon.py
├── harness.py
├── rlm.py
├── capsules.py
├── messaging.py
├── family_protocol.py
├── intelligence.py
├── resilience.py
└── cli.py

tests/
docs/
install/
assets/
ecosystem.surface.json
```

## Operator checklist

Before delegating a large repository run:

```text
[ ] working tree is recoverable
[ ] durable goal is explicit
[ ] tenant/project/session scope is set
[ ] write and runtime budget is bounded
[ ] required external credentials are available to the host, not the prompt
[ ] acceptance criteria are stated
[ ] risky work uses an isolation boundary
[ ] receipt/artifact destination is configured
```

## Documentation

- [`docs/LONG_RUNNING.md`](docs/LONG_RUNNING.md)
- [`docs/RLM.md`](docs/RLM.md)
- [`docs/CONTINUAL_HARNESS.md`](docs/CONTINUAL_HARNESS.md)
- [`docs/RAH.md`](docs/RAH.md)
- [`docs/WASM_CAPSULES.md`](docs/WASM_CAPSULES.md)
- [`install/README.md`](install/README.md)

## Ecosystem

- [POCKET Host](https://github.com/ItsNotAILABS/pocket) — identity, tenancy, policy, routing and user surfaces
- [Pocket Voice](https://github.com/ItsNotAILABS/pocket-voice-to-text) — conversational/voice control plane
- [NEXUS](https://github.com/ItsNotAILABS/nexus) — ecosystem protocols and federation
- [CAPSULA](https://github.com/ItsNotAILABS/CAPSULA) — isolated runtime/build capsules
- [MatDaemon](https://github.com/ItsNotAILABS/MatDaemon) — bounded matrix/compute worker

## License

MIT — see [`LICENSE`](LICENSE).
