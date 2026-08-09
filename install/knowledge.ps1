# irm …/install/knowledge.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo = if ($env:POCKET_AGENT_REPO) { $env:POCKET_AGENT_REPO } else { "https://github.com/ItsNotAILABS/pocket-agent.git" }
$Dest = if ($env:POCKET_KNOWLEDGE_HOME) { $env:POCKET_KNOWLEDGE_HOME } else { Join-Path $env:USERPROFILE ".pocket\knowledge" }
$Tmp = Join-Path $env:TEMP ("pocket-know-" + [guid]::NewGuid().ToString("n"))
Write-Host "==> POCKET app knowledge → $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
git clone --depth 1 $Repo $Tmp
Copy-Item -Recurse -Force (Join-Path $Tmp "knowledge\*") $Dest
New-Item -ItemType Directory -Force -Path ".\.pocket\knowledge" | Out-Null
Copy-Item -Recurse -Force (Join-Path $Dest "*") ".\.pocket\knowledge\"
if (-not (Test-Path ".\AGENTS.md")) {
  Copy-Item (Join-Path $Dest "AGENTS.md") ".\AGENTS.md" -ErrorAction SilentlyContinue
  Write-Host "Wrote .\AGENTS.md"
}
Remove-Item -Recurse -Force $Tmp
Write-Host "OK. Knowledge at $Dest and .\.pocket\knowledge"
