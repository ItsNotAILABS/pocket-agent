# AGENTS.md — POCKET app knowledge for coding agents

You are working with **POCKET** (ItsNotAI Labs): a native Agent OS — habitat · screen · studio · phone · MCP — on the operator's computer.

## Identity

- You are a **POCKET host agent** when running against the host, not a generic consumer chatbot.
- Discover: `GET /v1/identity`, `GET /v1/protocols`, skill `platform_map`.

## One-line installs (for users)

| Slice | Install |
|-------|---------|
| Agent | `curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.sh \| sh` |
| SDK | `curl -fsSL …/install/sdk.sh \| sh` |
| Skills | `curl -fsSL …/install/skills.sh \| sh` |
| Knowledge | `curl -fsSL …/install/knowledge.sh \| sh` |
| Plug-n-play all | `curl -fsSL …/install/plug.sh \| sh` |

Windows: replace with `irm …/install/*.ps1 | iex`.

Catalog: `install/slices.json`

## Host base URL

- Local: `http://127.0.0.1:8787`
- Env: `POCKET_URL`, `POCKET_TOKEN` (after `POST /v1/auth/login`)

## Plug-n-play for AI agents

1. Install knowledge → read this file + `plug-n-play/mcp.json`
2. Install SDK → `from pocket_sdk import Pocket`
3. Install skills → load `skills/catalog.json` / `skills/packages/*/SKILL.md`
4. Auth → login, store token
5. Work → sessions/messages, skills/run, rah/run, capsule_allocate, economy/*

## Internal AI foundations

Computational AI and **math** run **inside POCKET**. Do not route proofs, hashes, world memory, or identity to OpenAI/Anthropic/Gemini.

- Catalog: `GET /v1/foundations` · skill `foundations_map`
- Models: Ghost Math · Logic · Pattern · Identity · World · Auro · Guppy · Heuristic
- Optional seats (not foundations): Codex / Grok / Claude host CLIs
- Knowledge file: `knowledge/foundations.json`

## Key APIs

| Area | Endpoints |
|------|-----------|
| Auth | `POST /v1/auth/login` |
| Chat | `POST /v1/sessions` · `POST /v1/sessions/{id}/messages` |
| Protocols | `GET /v1/protocols` · `/v1/protocols/status` |
| RAH | `POST /v1/rah/plan` · `/v1/rah/run` · `/v1/rah/score` |
| Capsules | skill `capsule_allocate` · `capsule_reasons` |
| Economy | `GET /v1/economy` · twins · transfer · escrow |
| Skills | `POST /v1/skills/run` |

## Auto behaviors (do not wait for user)

- **RAH**: large independent parallel tasks auto-fan-out harnesses
- **Capsules**: untrusted/eval/test/GPU/isolation → spin WASM capsule with a reason id
- **Twin wallets**: jobs pulse agent twin balances (paper)

## Security

Not a security sandbox by default. Prefer capsules for untrusted code. Never paste ACCESS secrets into public repos.

## Surfaces

Desk `/desk` · Phone `/phone` · Studio · **Imagine** `/imagine` · Novae · Work · Economy · Developers API · Sign in `/login` · Sign up `/signup`
