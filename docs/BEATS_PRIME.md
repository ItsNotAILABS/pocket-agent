# POCKET Agent vs Prime Agent (Prime Intellect)

Prime Agent is a strong open design: **RLM + continual harness**.  
POCKET Agent **implements those abstractions** and adds host-grade systems Prime does not ship as one product.

## Shared ground (we ship too)

| Prime concept | POCKET Agent |
|---|---|
| RLM, prompt-as-variable | `pocket_agent.rlm` — variables + REPL |
| Programmatic tools / subagents | `rlm()`, `rlm_map()`, shell, files |
| Continual harness | `pocket_agent.harness` — durable JSON state |
| `/refine` evidence updates | `harness.refine(evidence=...)` + snapshots |
| Immutable base prompt | `BASE_SYSTEM` never rewritten |
| Executable skills | `pocket_agent.skills` packages |
| Background sessions | `daemon` reattach files under `~/.pocket/agent/` |
| Agent messaging | `messaging` bus (file-backed) |

## Where we beat / extend

| Gap in single-REPL RLM agents | POCKET Agent |
|---|---|
| Subagent = another model call | **RAH**: full harness fan-out (context+tools+plan+spawn), filesystem intermediate state |
| No isolation story for untrusted code | **WASM multi-sandbox capsules** (WASI / HostWorker / BrowserWorker + WebGPU) |
| Skills improve prompts only | Capsules + mesh + optional host skills platform |
| No economic metering | Twin wallets, escrow, paper clearing (when POCKET host present) |
| Desktop/phone product surface | Pairs with POCKET desk / phone / tunnel |
| Manual “use subagents” | **Auto-RAH** when task scores independent parallel work |
| Ad-hoc sandboxing | **20 named capsule reasons** agents auto-select |

## Design doctrine

1. **Everything is programmatic** — REPL is the model tool surface.  
2. **Harness is durable** — session state outlives one chat window.  
3. **Recursion unit is the harness** when scale demands it (RAH), not only bare tokens (RLM).  
4. **Isolation is first-class** — capsules for untrusted/eval/GPU/guest code.  
5. **Paper-first economics** — no silent live custody.

## CLI parity (Prime-compatible muscle memory)

| Prime | POCKET Agent |
|-------|----------------|
| `curl …/install.sh \| sh` | `install.sh` / `install.ps1` |
| `prime-agent` in project dir | `pocket-agent` (alias `prime-agent` from installer) |
| `/login` | `/login` |
| `agents` / `attach` / `--resume` | same |
| `status` / `doctor` / `update` / `shutdown` | same |
| goals / heartbeat / schedule / autonomous | `/goal` `/heartbeat` `schedule` `/autonomous` |
| — | `capsule reasons\|spin` · auto-RAH |

## Trust model (same warning, better isolation path)

Prime warns: worker/kernel isolation is **not** a security sandbox.  
We ship the **same warning** and a concrete fix path: **WASM multi-sandbox capsules** with 20 agent reasons (`untrusted_eval`, `sandbox_tests`, …).

## One-liner

> Prime Agent: excellent MIT RLM + continual harness agent.  
> **POCKET Agent: same long-running surface + RAH + WASM capsules + optional POCKET host economy — still MIT for the agent package.**
