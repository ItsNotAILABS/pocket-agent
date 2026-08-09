# Long-running and background agents

POCKET Agent is built for long-running research and coding work (same problem space as Prime Agent).

## Continuity

| Feature | Command / API |
|--------|----------------|
| Browse sessions | `pocket-agent agents` |
| Reattach | `pocket-agent attach <id>` |
| Resume saved | `pocket-agent --resume <path\|id>` |
| Service status | `pocket-agent status` |
| Repair | `pocket-agent doctor --fix` |
| Stop all | `pocket-agent shutdown [--force]` |

Daemon state: `~/.pocket/agent/sessions/`, `schedules/`, `service.json`.

## Goals

```
>>> /goal Audit auth across all routes
>>> /goal progress inventory complete
>>> /goal done
```

Goals persist across turns until completed, paused, or cleared.

## Heartbeats & schedules

```
>>> /heartbeat still working on auth
pocket-agent schedule add --session sess-… --every 1800 --note "nudge"
pocket-agent schedule fire
```

## Autonomous mode (bounded)

```
>>> /autonomous on max_turns=16
```

Budgets: turns, estimated tokens, wall minutes.  
**A limit is not success** — only quality gates (when configured) verify outcomes.

## Detach without killing work

```
>>> /detach
# later
pocket-agent attach sess-xxxxxxxxxxxx
```

## Security warning

Lifecycle isolation (sessions/workers) is **not** a security sandbox.  
Model-generated Python runs with **your user permissions**.

For untrusted code:

```bash
pocket-agent capsule spin --reason untrusted_eval
# or in REPL: /capsule untrusted_eval
```

See [WASM_CAPSULES.md](./WASM_CAPSULES.md) for all 20 agent reasons.
