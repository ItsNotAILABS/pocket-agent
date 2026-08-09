# POCKET Agent

**Open-source coding & research agent that beats single-REPL agents** — RLM control plane + continual harness + **Recursive Agent Harnesses (RAH)** + **WASM multi-sandbox capsules** + mesh economy, built for long-running host work.

[Documentation](./docs/) · [vs Prime Agent](./docs/BEATS_PRIME.md) · [WASM capsules](./docs/WASM_CAPSULES.md) · [RAH](./docs/RAH.md)

```bash
pip install -e .
pocket-agent --help
pocket-agent run "audit every API endpoint for missing auth"
pocket-agent capsule spin --webgpu --reason untrusted_eval
```

---

## Why POCKET Agent

| Capability | Typical chat agent | Prime Agent (RLM) | **POCKET Agent** |
|---|---|---|---|
| Context model | Sliding chat | Prompt-as-variable + REPL | **Same + host job ledger + mesh disk** |
| Subagents | Soft tool calls | `rlm(...)` children | **`rlm()` + RAH full-harness fan-out** |
| Durable state | Session only | Continual harness | **Harness + `~/.pocket/` durable domain** |
| Isolation | Optional | Process-ish | **WASM/WASI multi-sandbox capsules + WebGPU** |
| Long runs | Fragile | Daemon reattach | **Daemon + heartbeats + RAH leaves** |
| Economics | — | — | **Twin wallets · escrow · paper clearing** |
| Host OS | Limited | Shell | **Screen, habitat, phone pair, skills platform** |

Everything is **programmatic**: the control environment is a persistent Python REPL. File ops, shell, tools, subagents, capsules, and context management are code — not opaque UI clicks.

---

## Core abstractions

### 1. Recursive Language Model (RLM)

- Context treated as **variables** (`prompt-as-a-variable`)
- Tools & subagents as **function calls** inside a **persistent REPL**
- `rlm(goal, parallel=N)` spawns real child agents and returns results in-process

### 2. Continual Harness

Stores supplemental prompts, memories, skill descriptions, and subagent specs as **durable state**.

- `/refine` applies small, evidence-backed updates  
- **Never** rewrites the immutable base system prompt  
- Snapshots + rollback  

### 3. Recursive Agent Harnesses (RAH)

When work is large and **independent**, the host auto-escalates to **full harness fan-out** (not bare model calls). Parent writes an orchestration plan/script; leaves run with own context + tools. See [docs/RAH.md](./docs/RAH.md).

### 4. WASM multi-sandbox capsules

Agents **spin up** isolated capsules (WASI / HostWorker / BrowserWorker + optional WebGPU) for untrusted or heavy work. **20 reasons** agents should do this are documented and machine-readable — [docs/WASM_CAPSULES.md](./docs/WASM_CAPSULES.md).

---

## Install

```bash
# Python 3.11+
git clone https://github.com/ItsNotAILABS/pocket-agent.git
cd pocket-agent
pip install -e ".[dev]"

# Optional: full POCKET host (desk, phone, economy, mesh)
# set PYTHONPATH to pocket-os/src and run: python -m pocket serve
```

---

## Quick start

```python
from pocket_agent import Agent, Capsule

agent = Agent(cwd=".")
# Persistent REPL control — everything is code
result = agent.run("""
# durable goals
set_goal("Ship auth audit")

# spin a WASM capsule for untrusted eval
cap = capsule_spin(tier="512MB", webgpu=False, reason="untrusted_eval")
print(cap)

# parallel RLM children
outs = rlm_map([
    "inventory public routes",
    "check session gates on POST",
    "list secret logging risks",
], max_workers=3)
print(outs)

# evidence-backed harness refine
refine(evidence="route inventory complete; 12 POST without auth notes")
""")
print(result.summary)
```

CLI:

```bash
pocket-agent repl                 # interactive control REPL
pocket-agent run "..."            # one-shot with auto RAH when fit
pocket-agent capsule list
pocket-agent capsule spin --reason sandbox_tests --webgpu
pocket-agent capsule reasons      # print the 20 reasons
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User / Desk / Phone / API                                  │
├─────────────────────────────────────────────────────────────┤
│  Continual Harness (durable skills, memories, subagent specs)│
│  immutable base prompt  ·  /refine  ·  snapshots/rollback   │
├─────────────────────────────────────────────────────────────┤
│  RLM control REPL (IPython-shaped)                          │
│  files · shell · tools · rlm() · capsule_spin() · messages  │
├──────────────┬──────────────────┬───────────────────────────┤
│  Subagents   │  RAH fan-out     │  WASM capsules            │
│  mesh/latin  │  full harnesses  │  WASI/Host/Browser+GPU    │
├──────────────┴──────────────────┴───────────────────────────┤
│  POCKET host (optional): jobs · economy twins · screen · MCP │
└─────────────────────────────────────────────────────────────┘
```

---

## Feature checklist (ships beyond chat-only agents)

- [x] Persistent Python control environment  
- [x] Built-in subagents via `rlm(...)`  
- [x] Continual harness + `/refine` + snapshots  
- [x] Executable skills as importable packages  
- [x] Background/daemon sessions (reattach)  
- [x] Agent-to-agent messaging  
- [x] Auto compaction hooks + retained goals  
- [x] **RAH** — recursive full-harness fan-out  
- [x] **WASM multi-sandbox capsules** + WebGPU doctrine  
- [x] **20 capsule use-reasons** for agents (machine + human)  
- [x] Economy hooks (twin wallets / escrow when host present)  
- [x] Paper-first Parallax AI-wallet export when host present  

---

## License

Researcher License / lab terms — see [LICENSE](./LICENSE).  
Part of **ItsNotAI Labs** · pairs with the POCKET host product.

## Status

Public alpha · host integration via `pocket-os` · capsules require optional `wasmtime` for WASI guests.
