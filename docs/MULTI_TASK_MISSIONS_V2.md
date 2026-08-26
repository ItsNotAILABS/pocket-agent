# POCKET Agent Multi-Task Missions v2

POCKET Agent missions are durable programs, not one chat completion. A mission may contain many independent workstreams, long dependency chains, repeated review and revision cycles, real deliverable contracts, and a final evidence package.

## Execution model

```text
one or more user objectives
        |
        v
mission program planner
        |
        +--> workstream A: interpret -> evidence + solution -> review/revise -> validate
        +--> workstream B: interpret -> evidence + solution -> review/revise -> validate
        +--> workstream C: interpret -> evidence + solution -> review/revise -> validate
        |
        v
cross-workstream evidence
        |
        v
integration
        |
        v
independent global reviewers
        |
        v
final revision -> final validation
        |
        v
contracted artifact renderers
        |
        v
ARTIFACT_MANIFEST.json + mission-artifacts.zip
```

The durable owner is `pocket-agent`. AURO supplies bounded model reasoning through the Auro-2B council endpoint. A language model is not the scheduler, database, approval authority, artifact custodian, or process supervisor.

## Reasoning profiles

| Profile | Revision cycles | Independent reviewers | Max parallel | Use |
|---|---:|---:|---:|---|
| `quick` | 0 | 1 | 2 | small bounded requests |
| `standard` | 1 | 2 | 3 | ordinary production work |
| `deep` | 2 | 3 | 5 | major research, engineering, or product delivery |
| `exhaustive` | 3 | 4 | 8 | long programs with multiple independent workstreams |

A profile controls visible work structure and bounded council passes. It does not request or export private chain-of-thought. The evidence record contains task objectives, dependencies, model identity, decision summaries, review findings, receipts, artifacts, and blockers.

## Mission request

```json
{
  "title": "Ship a customer-ready AURO product release",
  "objective": "Complete the product, evidence, deployment, and publication work as one integrated delivery.",
  "reasoning_profile": "deep",
  "max_parallel": 5,
  "budget": {
    "max_tasks": 500,
    "max_task_attempts": 1500,
    "max_runtime_seconds": 28800
  },
  "workstreams": [
    {
      "id": "runtime",
      "title": "Production runtime",
      "objective": "Implement and validate the production runtime.",
      "acceptance_criteria": [
        "source imports",
        "runtime fails closed when dependencies are missing",
        "API smoke evidence is produced"
      ]
    },
    {
      "id": "product",
      "title": "Customer product",
      "objective": "Prepare the user-facing application, installation, and account flow."
    },
    {
      "id": "research",
      "title": "Research and evidence",
      "objective": "Create the claim-to-evidence package and publication material."
    }
  ],
  "deliverables": [
    {
      "path": "deliverables/release-report.md",
      "title": "Release Report",
      "acceptance_criteria": ["all workstreams represented", "blockers visible"]
    },
    {
      "path": "deliverables/evidence.json",
      "title": "Evidence Index"
    },
    {
      "path": "deliverables/release-table.csv",
      "title": "Release Matrix"
    },
    {
      "path": "deliverables/summary.html",
      "title": "Customer Summary"
    }
  ]
}
```

## Plan without storing

```bash
python -m pocket_agent.mission_cli plan \
  --request mission.json \
  --principal operator-1 \
  --tenant organization-1
```

The plan exposes every task, dependency, reasoning-round budget, timeout, acceptance criterion, required artifact, and `plan_sha256`.

## Create the durable mission

```bash
python -m pocket_agent.mission_cli create \
  --request mission.json \
  --principal operator-1 \
  --tenant organization-1
```

The mission is stored in SQLite/WAL. Task leases, retries, results, events, receipts, and artifact identities survive process restarts.

## Run one bounded burst

```bash
python -m pocket_agent.mission_cli run MISSION_ID \
  --principal operator-1 \
  --tenant organization-1 \
  --max-tasks 50 \
  --seconds 900
```

A burst is deliberately bounded. Running one burst does not imply that a long mission is complete.

## Run the long-lived worker

```bash
export POCKET_MISSION_DB=state/pocket-agent-missions.sqlite3
export POCKET_MISSION_ARTIFACT_ROOT=state/mission-artifacts
export AURO_COUNCIL_URL=http://127.0.0.1:8090/v1/council/respond
export AURO_API_TOKEN=replace-with-scoped-token
export POCKET_MISSION_TENANTS=organization-1

python -m pocket_agent.mission_worker \
  --worker-id worker-production-1 \
  --tasks-per-burst 25 \
  --burst-seconds 600
```

The worker:

- polls queued and running missions;
- recovers expired task leases;
- advances several missions per cycle;
- writes an atomic heartbeat;
- stops cleanly on `SIGINT` or `SIGTERM`;
- never creates its own missions;
- never grants its own runtime-cell approvals;
- does not silently move work between tenants.

Running the script in a terminal is not production supervision. Production requires a service manager, container, system service, or other operator-controlled process supervisor plus logs and restart evidence.

## Pause, resume, cancel, inspect

```bash
python -m pocket_agent.mission_cli pause MISSION_ID --principal operator-1 --tenant organization-1
python -m pocket_agent.mission_cli resume MISSION_ID --principal operator-1 --tenant organization-1
python -m pocket_agent.mission_cli cancel MISSION_ID --reason "operator decision" --principal operator-1 --tenant organization-1
python -m pocket_agent.mission_cli status MISSION_ID --principal operator-1 --tenant organization-1
```

## Deliverable rules

Built-in renderers support:

```text
.md .txt .json .csv .html .htm .yaml .yml .xml
```

Binary formats require a real renderer registered by the host:

```text
.pdf .docx .pptx .xlsx
```

This is intentional. POCKET Agent will not put plain UTF-8 text into a `.pdf` or `.docx` filename and claim a document was generated.

A host can register a renderer:

```python
from pocket_agent.mission_program import MissionProgramService
from pocket_agent.mission_renderers import (
    ArtifactRendererRegistry,
    callable_binary_renderer,
)

registry = ArtifactRendererRegistry()
registry.register(
    "company-pdf-renderer",
    {".pdf"},
    callable_binary_renderer(
        "company-pdf-renderer",
        "application/pdf",
        render_pdf_with_company_pipeline,
    ),
)
service = MissionProgramService.from_env(renderers=registry)
```

Every produced artifact has:

- a safe mission-relative path;
- a media type;
- a byte count;
- a SHA-256 digest;
- a producing task ID;
- a renderer receipt where applicable;
- a final manifest entry;
- optional semantic acceptance criteria.

## Multiple users and organizations

Each mission records `principal_id` and `tenant_id`. The service rejects cross-tenant access and cross-principal access unless the caller is an explicitly recognized administrative principal. Artifacts are resolved only after mission authorization.

A worker may be restricted to an allowlist:

```bash
export POCKET_MISSION_TENANTS=organization-1,organization-2
```

## Failure and recovery

- Tasks use leases, not permanent process ownership.
- Expired leases return to the queue when retry budget remains.
- A process restart does not erase the mission DAG.
- Review tasks may fail or identify blockers without claiming the entire mission succeeded.
- Required deliverable failures keep the artifact task unaccepted.
- A mission reaches `completed` only when every task is completed.
- `mission-artifacts.zip` is produced only after final validation and deliverable rendering.

## Truth boundary

Source code and deterministic tests establish architecture and local behavior. They do not by themselves establish:

- an always-running production worker;
- a live AURO council endpoint;
- high-quality reasoning from an exact checkpoint;
- semantic correctness of every artifact;
- a successful binary renderer;
- production tenant isolation under adversarial load;
- clean installation or deployment;
- external receipt custody.

Those require separately captured execution, validation, deployment, and custody evidence.
