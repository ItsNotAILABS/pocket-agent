# POCKET Agent Multi-Task Missions v1

POCKET Agent now owns the durable execution layer for work that contains many dependent tasks, takes longer than one request, needs multiple reasoning passes, or must deliver inspectable artifacts.

AURO remains the reasoning provider. POCKET Agent owns mission state, leases, retries, artifacts, tenant boundaries, and worker recovery.

## System boundary

```text
POCKET / operator request
        |
        v
POCKET Agent mission plan
        |
        +--> SQLite/WAL mission and task state
        +--> dependency-ready scheduling
        +--> bounded worker leases and retries
        +--> organization and principal ownership
        |
        v
AURO-2B council reasoning adapter
        |
        +--> SENSUS
        +--> PRAXIS
        +--> VERBUM
        +--> atomic AURO specialists
        |
        v
POCKET Agent artifact store
        |
        +--> Markdown / JSON / text / HTML / CSV
        +--> SHA-256 records
        +--> decision summaries and evidence
        +--> ARTIFACT_MANIFEST.json
        +--> mission-artifacts.zip
```

The model repository does not become the workflow database. The workflow database does not claim model quality.

## Default deep-work graph

When no explicit tasks are supplied, the planner creates:

```text
interpret
   |
   +--> evidence ----+
   |                 |
   +--> solution ----+--> deliverables --> red-team --> synthesize --> package
```

`evidence` and `solution` may execute concurrently after `interpret`. Every task ID is namespaced by mission so different users and missions can safely reuse names such as `research`, `build`, or `review`.

Each AURO-backed task may use one to six bounded reasoning passes. The store records only:

- conclusions;
- alternatives;
- evidence references;
- confidence;
- blockers;
- receipts;
- artifact hashes.

Private model chain-of-thought is not stored or exported.

## Capabilities

The mission subsystem provides:

- explicit or generated task DAGs;
- cycle and missing-dependency rejection;
- dependency-ready parallel scheduling;
- per-mission parallelism enforced inside SQLite transactions;
- task leases, heartbeats, retries, and expired-lease recovery;
- mission deadlines and resource budgets;
- pause, resume, and idempotent cancellation;
- multi-user organization and principal isolation;
- idempotent mission creation;
- long-running supervised worker loops;
- AURO council reasoning adapters;
- exact approval-bound runtime-cell execution adapters;
- path-safe content-addressed artifacts;
- deterministic manifests and ZIP packages;
- immutable event and decision histories.

## Environment

```bash
export POCKET_MISSION_DB=state/pocket-agent-missions.sqlite3
export POCKET_MISSION_ARTIFACT_ROOT=state/mission-artifacts
export POCKET_PRINCIPAL_ID=operator-123
export POCKET_TENANT_ID=organization-123

export AURO_COUNCIL_URL=http://127.0.0.1:8090/v1/council/respond
export AURO_API_TOKEN=replace-with-scoped-token
export AURO_COUNCIL_TIMEOUT_SECONDS=180
```

The default AURO URL is a configuration default, not a readiness claim. `pocket-mission status` reports endpoint readiness as unknown until a real health or task call supplies evidence.

## Create a complete mission

```bash
pocket-mission create \
  --title "Production release analysis" \
  --objective "Inspect the release, implement fixes, red-team the result, and deliver a report" \
  --deliverable deliverables/release-report.md \
  --deliverable deliverables/release-evidence.json \
  --max-parallel 3 \
  --idempotency-key release-analysis-2026-08-25
```

The command returns the mission ID and complete plan.

## Provide an explicit task graph

`tasks.json`:

```json
[
  {
    "task_id": "inventory",
    "kind": "research",
    "objective": "Inventory current release evidence",
    "reasoning_rounds": 3,
    "required_artifacts": ["inventory.md", "inventory.json"]
  },
  {
    "task_id": "implementation",
    "kind": "implementation",
    "objective": "Implement the approved corrections",
    "depends_on": ["inventory"],
    "reasoning_rounds": 3,
    "required_artifacts": ["implementation.md"]
  },
  {
    "task_id": "review",
    "kind": "review",
    "objective": "Red-team the implementation",
    "depends_on": ["implementation"],
    "required_artifacts": ["review.md"]
  },
  {
    "task_id": "package",
    "kind": "package",
    "objective": "Package outputs",
    "depends_on": ["review"]
  }
]
```

```bash
pocket-mission create \
  --objective "Complete the release program" \
  --tasks-json tasks.json
```

The local task IDs are preserved inside task payloads for display. The durable IDs are mission-prefixed to avoid collisions.

## Run bounded work

```bash
pocket-mission run MISSION_ID \
  --worker-id operator-laptop \
  --max-tasks 20 \
  --time-budget-seconds 900
```

This is a bounded execution burst. It may finish the mission or stop because its burst budget was reached. The mission remains durable and may be resumed by another worker process.

## Run a supervised worker

One pass:

```bash
pocket-mission-worker --once
```

Continuous supervised process:

```bash
pocket-mission-worker \
  --worker-id desktop-worker-1 \
  --max-tasks-per-burst 8 \
  --time-budget-seconds 240
```

A worker process must actually be running for unattended work to continue. Source code and queued rows alone are not evidence of autonomous execution.

## Lifecycle

```bash
pocket-mission pause MISSION_ID
pocket-mission resume MISSION_ID
pocket-mission cancel MISSION_ID
pocket-mission show MISSION_ID
pocket-mission list
```

Cancellation is durable and idempotent. A task already executing in an external backend cannot be assumed cancelled until the backend also returns cancellation evidence.

## Budgets

A budget JSON object may include:

```json
{
  "max_tasks": 64,
  "max_runtime_seconds": 86400,
  "max_artifact_bytes": 536870912,
  "max_task_attempts": 256
}
```

```bash
pocket-mission create \
  --objective "Long evidence campaign" \
  --budget-json budget.json
```

The scheduler stops leasing new work after a budget is exhausted. This does not retroactively terminate a remote model or tool call already in progress.

## Approval-bound computer execution

An `execution` task is not automatically executable. A host application must register `RuntimeCellTaskExecutor` with:

1. a persistent `RuntimeCellGovernor`;
2. a concrete backend adapter;
3. an independent validator;
4. an exact one-time approval ID and token in the task payload.

The task payload must contain:

```json
{
  "operation": {
    "operator_id": "operator-123",
    "agent_id": "mission-agent",
    "cell_id": "cell-123",
    "tool": "sandbox.command.execute",
    "arguments": {"argv": ["python", "-m", "pytest", "-q"]},
    "filesystem_scope": ["/workspace"],
    "egress_scope": [],
    "environment": "development",
    "estimated_cost_usd": 0,
    "destructive": false
  },
  "approval_id": "apr_...",
  "approval_token": "signed-one-time-token"
}
```

A nonempty approval ID is not authorization. Replays are rejected after consumption, including after process restart.

## Artifact policy

Built-in writers support formats that can be created correctly without a specialized renderer:

```text
.md .txt .json .jsonl .csv .tsv .html .htm .xml .yaml .yml
.py .js .ts .tsx .jsx .css .sql .sh .ps1 .toml .ini .cfg .log
```

Requests for `.pdf`, `.docx`, `.pptx`, `.xlsx`, images, audio, or video fail visibly unless a real renderer or generator is registered. POCKET Agent does not write plain text into a binary extension and call it a deliverable.

Every stored artifact records:

- mission ID;
- task ID;
- relative path;
- media type;
- byte count;
- SHA-256;
- timestamp;
- label.

The final bundle contains the current `ARTIFACT_MANIFEST.json` and excludes the bundle itself to avoid recursive or stale manifests.

## Multi-user boundary

Each mission is bound to:

```text
tenant_id + principal_id
```

Ordinary users can see and mutate only their own missions inside their tenant. A separately governed `system-admin` identity may inspect tenant missions through the service API. Database possession alone should not be exposed to untrusted clients.

## Evidence boundary

This subsystem can prove:

- a task graph was stored;
- leases and retries were recorded;
- a model endpoint returned a response;
- an approved runtime-cell operation produced a receipt;
- a file with a specific hash exists;
- a deterministic package was assembled.

It does not by itself prove:

- semantic correctness of the result;
- factual accuracy of generated content;
- a specific AURO checkpoint served the request;
- an external tool actually changed the world beyond its validation evidence;
- unattended execution occurred without a running worker;
- E5 external custody;
- production deployment.

## Promotion gate

Before this subsystem is treated as production-ready, require:

```text
[ ] all focused tests pass on Python 3.11 and 3.12
[ ] database restart and lease-recovery test passes
[ ] two simultaneous worker processes respect max_parallel
[ ] tenant-isolation tests pass
[ ] approval replay is rejected after restart
[ ] an actual AURO council endpoint returns identity-bound receipts
[ ] one real runtime-cell backend returns independent validation
[ ] a clean install exposes pocket-mission and pocket-mission-worker
[ ] artifact ZIP and manifest hashes verify after download
[ ] worker supervision and restart policy are documented
[ ] production secrets remain outside generated code and artifacts
```
