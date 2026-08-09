# POCKET install slices — one-liners

Copy any line. Each slice is **plug-and-play** for humans and AI agents.

> **Base (GitHub raw):** `https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main`  
> **Live host (when online):** `https://pocket.medinatechlabs.net`

---

## One-line installs

### Agent (long-running RLM + harness + RAH + capsules)

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.ps1 | iex
```

### Python SDK (talk to any POCKET host)

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/sdk.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/sdk.ps1 | iex
```

### Skills pack

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/skills.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/skills.ps1 | iex
```

### App knowledge (AGENTS.md + protocols + API map)

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/knowledge.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/knowledge.ps1 | iex
```

### WASM capsules only

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/capsules.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/capsules.ps1 | iex
```

### Full agent plug-n-play (SDK + skills + knowledge + agent)

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/plug.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/plug.ps1 | iex
```

### Host operator notes

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/host.sh | sh
```

```powershell
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/host.ps1 | iex
```

---

## Machine catalog

```bash
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/slices.json
```

---

## After install — for AI agents

```bash
# point any agent at local knowledge
cat .pocket/knowledge/AGENTS.md

# Python
python -c "from pocket_sdk import Pocket; print(Pocket().health())"

# Capsules
pocket-agent capsule reasons
pocket-agent capsule spin --reason untrusted_eval
```

Env:

| Variable | Meaning |
|----------|---------|
| `POCKET_URL` | Host base URL (default `http://127.0.0.1:8787`) |
| `POCKET_TOKEN` | Bearer session token |
| `POCKET_HOME` | Install root (default `~/.pocket`) |
