# POCKET Agent Mail slice — our own agent email accounts + inboxes
#   irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/mail.ps1 | iex
$ErrorActionPreference = "Continue"
$Repo = if ($env:POCKET_AGENT_REPO) { $env:POCKET_AGENT_REPO } else { "https://github.com/ItsNotAILABS/pocket-agent.git" }
$Dir = if ($env:POCKET_MAIL_HOME) { $env:POCKET_MAIL_HOME } else { Join-Path $HOME ".pocket\mail-slice" }
$HostUrl = if ($env:POCKET_URL) { $env:POCKET_URL.TrimEnd("/") } else { "http://127.0.0.1:8787" }

Write-Host "==> POCKET Agent Mail -> $Dir"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$repoDir = Join-Path $Dir "repo"
if (Test-Path (Join-Path $repoDir ".git")) {
  try { git -C $repoDir pull --ff-only 2>$null } catch {}
} else {
  try { git clone --depth 1 $Repo $repoDir 2>$null } catch {
    Write-Host "git clone optional - writing knowledge without clone"
  }
}

$know = Join-Path $Dir "knowledge"
New-Item -ItemType Directory -Force -Path $know | Out-Null

$agentMailMd = @"
# POCKET Agent Mail

Domain: agents.pocket.local - our own accounts, not Gmail.

## Host APIs

- GET  /v1/agent-mail
- GET  /v1/agent-mail/accounts
- POST /v1/agent-mail/accounts
- GET  /v1/agent-mail/inbox?agent=assist
- POST /v1/agent-mail/send
- UI: /mail

## Skills / MCP

mail_status, mail_accounts, mail_account_create, mail_inbox, mail_send, mail_read

## Python (on host)

from pocket.agent_mail import create_account, send, inbox, status
status()
send(from_agent='scribe', to='assist', subject='hi', body='hello')
"@
Set-Content -Path (Join-Path $know "AGENT_MAIL.md") -Value $agentMailMd -Encoding utf8

$agentsMd = @"
# Agent Mail plug-in for coding agents

Host: $HostUrl

1. List: GET $HostUrl/v1/agent-mail/accounts
2. Send: POST $HostUrl/v1/agent-mail/send
3. Inbox: GET $HostUrl/v1/agent-mail/inbox?agent=assist
4. Skills: mail_inbox, mail_send via POST /v1/skills/run
"@
Set-Content -Path (Join-Path $know "AGENTS.md") -Value $agentsMd -Encoding utf8

$skillDir = Join-Path $Dir "skills\agent-mail"
New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
$skillMd = @"
---
name: agent-mail
description: POCKET Agent Mail - accounts, inboxes, agent-to-agent send on agents.pocket.local
---

# Agent Mail skill

Prefer host /v1/agent-mail/* over third-party mail. Create accounts, send, read inbox.
"@
Set-Content -Path (Join-Path $skillDir "SKILL.md") -Value $skillMd -Encoding utf8

$manifestObj = [ordered]@{
  schema = "pocket.mail.slice.v1"
  product = "POCKET Agent Mail"
  domain = "agents.pocket.local"
  host = $HostUrl
  apis = @("/v1/agent-mail", "/v1/agent-mail/accounts", "/v1/agent-mail/inbox", "/v1/agent-mail/send", "/mail")
  skills = @("mail_status", "mail_accounts", "mail_inbox", "mail_send", "mail_read")
  installed_at = (Get-Date).ToUniversalTime().ToString("o")
}
$manifestObj | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $Dir "manifest.json") -Encoding utf8

Write-Host "OK. Agent Mail slice at $Dir"
Write-Host "  Host UI: $HostUrl/mail"
Write-Host "  Probe:   curl $HostUrl/v1/agent-mail"
