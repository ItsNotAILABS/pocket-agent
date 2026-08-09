# POCKET Agent

Open-source **coding and research agent** for general and long-running work.  
Built to match and **extend** the Prime Agent (Prime Intellect) model: RLM + continual harness — plus **RAH**, **WASM multi-sandbox capsules**, and optional POCKET host economy/mesh.

[Documentation](./docs/) · [vs Prime](./docs/BEATS_PRIME.md) · [Long-running](./docs/LONG_RUNNING.md) · [WASM capsules](./docs/WASM_CAPSULES.md) · [RAH](./docs/RAH.md)

```bash
# Install (macOS / Linux) — Prime-style one-liner
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.sh | sh

# Windows
# irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.ps1 | iex
```

The installer clones/updates the repo, installs the `pocket-agent` command (and a `prime-agent` alias), and prepares runtime dirs under `~/.pocket/agent/`.

### More one-line slices (SDK · skills · knowledge · plug-n-play)

| Slice | macOS / Linux | Windows |
|-------|----------------|---------|
| **Agent** | `curl -fsSL …/install.sh \| sh` | `irm …/install.ps1 \| iex` |
| **SDK** | `curl -fsSL …/install/sdk.sh \| sh` | `irm …/install/sdk.ps1 \| iex` |
| **Skills** | `curl -fsSL …/install/skills.sh \| sh` | `irm …/install/skills.ps1 \| iex` |
| **Knowledge** | `curl -fsSL …/install/knowledge.sh \| sh` | `irm …/install/knowledge.ps1 \| iex` |
| **Capsules** | `curl -fsSL …/install/capsules.sh \| sh` | `irm …/install/capsules.ps1 \| iex` |
| **Plug-n-play all** | `curl -fsSL …/install/plug.sh \| sh` | `irm …/install/plug.ps1 \| iex` |

Full URLs and JSON catalog: **[install/README.md](./install/README.md)** · `install/slices.json`  
Live host hub (when serve is up): **http://127.0.0.1:8787/install**

---

## Start

```bash
cd /path/to/project
pocket-agent
```

On first launch use **`/login`** for provider/host auth hints. The agent works in the **current directory** and can run commands and modify files there. Prefer a disposable clone or clean worktree you can inspect and restore.

### Warning

POCKET Agent executes model-generated Python and project commands with **your user permissions**. Session/worker lifecycle improves recovery; **it is not a security sandbox**. Review changes. Use trusted repos and instructions. Run untrusted code in a **WASM capsule** or other restricted environment:

```bash
pocket-agent capsule spin --reason untrusted_eval
```

---

## Useful commands

```bash
pocket-agent                         # interactive session (TUI/REPL) in cwd
pocket-agent agents                  # browse running, idle, and saved sessions
pocket-agent attach <agent>          # reattach to a session
pocket-agent --resume <path|id>      # resume a saved session
pocket-agent status                  # background service state
pocket-agent doctor [--fix]          # inspect or repair services
pocket-agent schedule list|add|fire  # heartbeats / timed re-entry
pocket-agent update [--force]        # update install
pocket-agent shutdown [--force]      # stop sessions + service
pocket-agent capsule reasons         # 20 reasons agents spin WASM capsules
pocket-agent capsule spin --webgpu --reason webgpu_compute
pocket-agent run "audit every API for missing auth"   # auto-RAH when fit
```

In-session slash commands: `/goal`, `/refine`, `/heartbeat`, `/autonomous`, `/capsule`, `/detach`, `/help`.

---

## Built for long-running work

| Feature | What it does |
|--------|----------------|
| **Continual harness** | `/refine` persists reviewable lessons as supplemental prompts, memories, skill notes — never rewrites immutable base system prompt; snapshots support rollback |
| **Direct agent-to-agent** | Running agents/subagents message via bus; `rlm()` / RAH for parallel work |
| **Daemon continuity** | Sessions keep state when the terminal detaches; reattach later |
| **Heartbeats & schedules** | `/heartbeat`, `pocket-agent schedule` re-enter periodically |
| **Persistent goals** | `/goal` keeps objective + progress across turns |
| **Bounded autonomous** | `/autonomous` with turn/token/time budgets (limit ≠ success) |
| **RAH** | Full recursive harness fan-out for independent large tasks (auto) |
| **WASM capsules** | Real multi-sandbox spin-up with **20 named reasons** agents should use them |

---

## Two core abstractions (+ two POCKET upgrades)

1. **RLM** — context as variables; tools/subagents as function calls in a persistent Python control environment.  
2. **Continual harness** — durable supplemental state; evidence-backed `/refine`.  
3. **RAH** — recursive unit is a **full agent harness**, not only a bare model call.  
4. **WASM capsules** — isolation/WebGPU/parallel FS slices (PROTO-CAPSULE-WASM-009).

Everything is **programmatic**: files, shell, tools, subagents, capsules, and context management go through code.

---

## Install from source

```bash
git clone https://github.com/ItsNotAILABS/pocket-agent.git
cd pocket-agent
pip install -e ".[dev]"
pocket-agent doctor --fix
cd /path/to/project && pocket-agent
```

Optional full host (desk, phone, economy, mesh):

```bash
# with pocket-os on PYTHONPATH
python -m pocket serve
```

---

## Documentation

| Doc | Topic |
|-----|--------|
| [docs/LONG_RUNNING.md](./docs/LONG_RUNNING.md) | Detach, goals, heartbeats, autonomous |
| [docs/RLM.md](./docs/RLM.md) | Persistent control + subagents |
| [docs/CONTINUAL_HARNESS.md](./docs/CONTINUAL_HARNESS.md) | Refine + snapshots |
| [docs/RAH.md](./docs/RAH.md) | Recursive Agent Harnesses |
| [docs/WASM_CAPSULES.md](./docs/WASM_CAPSULES.md) | 20 capsule reasons |
| [docs/BEATS_PRIME.md](./docs/BEATS_PRIME.md) | Feature comparison |

---

## Acknowledgements

Inspired by open RLM/harness agent designs (including Prime Agent / pi-adjacent work). POCKET Agent adds host-grade RAH, WASM multi-sandbox capsules, and optional POCKET product integration.

## License

**MIT** — see [LICENSE](./LICENSE).

## Status

Public alpha · long-running daemon is file-backed (host workers optional) · capsules use POCKET host when available, else local overlay under `~/.pocket/capsules/`.
