#!/usr/bin/env sh
# POCKET Agent Mail slice — our own agent email accounts + inboxes
#   curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/mail.sh | sh
set -eu
REPO="${POCKET_AGENT_REPO:-https://github.com/ItsNotAILABS/pocket-agent.git}"
DIR="${POCKET_MAIL_HOME:-$HOME/.pocket/mail-slice}"
HOST="${POCKET_URL:-http://127.0.0.1:8787}"
echo "==> POCKET Agent Mail → $DIR"
mkdir -p "$DIR"
if [ -d "$DIR/repo/.git" ]; then
  git -C "$DIR/repo" pull --ff-only || true
else
  git clone --depth 1 "$REPO" "$DIR/repo"
fi

# Knowledge + API map for agents
mkdir -p "$DIR/knowledge"
cat > "$DIR/knowledge/AGENT_MAIL.md" <<'EOF'
# POCKET Agent Mail

Domain: **agents.pocket.local** — our own accounts, not Gmail.

## Host APIs (when POCKET serve is up)

- GET  /v1/agent-mail
- GET  /v1/agent-mail/accounts
- POST /v1/agent-mail/accounts  {"agent":"mybot","name":"My Bot"}
- GET  /v1/agent-mail/inbox?agent=assist
- POST /v1/agent-mail/send  {"from":"scribe","to":"assist","subject":"hi","body":"…"}
- POST /v1/agent-mail/read  {"agent":"assist","id":"am-…"}
- UI: /mail

## Skills / MCP

mail_status · mail_accounts · mail_account_create · mail_inbox · mail_send · mail_read

## Python (on host)

```python
from pocket.agent_mail import create_account, send, inbox, status
status()
send(from_agent="scribe", to="assist", subject="hi", body="hello")
print(inbox("assist"))
```

External SMTP: POCKET_SMTP_* via POCKET MAIL with external=true.
EOF

cat > "$DIR/knowledge/AGENTS.md" <<EOF
# Agent Mail plug-in for coding agents

You can use **POCKET Agent Mail** on the host ($HOST):

1. List accounts: GET $HOST/v1/agent-mail/accounts
2. Send: POST $HOST/v1/agent-mail/send JSON from/to/subject/body
3. Inbox: GET $HOST/v1/agent-mail/inbox?agent=YOUR_ID
4. Skills: mail_inbox, mail_send, mail_accounts (POST /v1/skills/run)

Default agents: assist, codex, claude, grok, auro, scribe, archon, navigator, system.
EOF

# Skills stub for Claude/Cursor/Grok
mkdir -p "$DIR/skills/agent-mail"
cat > "$DIR/skills/agent-mail/SKILL.md" <<'EOF'
---
name: agent-mail
description: POCKET Agent Mail — create accounts, read inboxes, send agent↔agent mail on agents.pocket.local
---

# Agent Mail skill

When the user mentions email, inbox, agent mail, or messaging between agents:

1. Prefer host APIs under `/v1/agent-mail/*` (not third-party Gmail).
2. Create accounts with POST /v1/agent-mail/accounts.
3. Send with POST /v1/agent-mail/send (local delivery is free).
4. Read with GET /v1/agent-mail/inbox?agent=…
5. For external SMTP, set external:true and configure POCKET_SMTP_* on the host.

See knowledge/AGENT_MAIL.md in this slice.
EOF

# Manifest for plug-n-play
cat > "$DIR/manifest.json" <<EOF
{
  "schema": "pocket.mail.slice.v1",
  "product": "POCKET Agent Mail",
  "domain": "agents.pocket.local",
  "host": "$HOST",
  "apis": [
    "/v1/agent-mail",
    "/v1/agent-mail/accounts",
    "/v1/agent-mail/inbox",
    "/v1/agent-mail/send",
    "/mail"
  ],
  "skills": ["mail_status", "mail_accounts", "mail_inbox", "mail_send", "mail_read"],
  "knowledge": ["knowledge/AGENT_MAIL.md", "knowledge/AGENTS.md"],
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
}
EOF

echo "OK. Agent Mail slice at $DIR"
echo "  knowledge: $DIR/knowledge/AGENT_MAIL.md"
echo "  skill:     $DIR/skills/agent-mail/SKILL.md"
echo "  Host UI:   $HOST/mail  (when pocket serve is up)"
echo "  Probe:     curl -s $HOST/v1/agent-mail"
