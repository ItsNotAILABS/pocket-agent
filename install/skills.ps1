# irm …/install/skills.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo = if ($env:POCKET_AGENT_REPO) { $env:POCKET_AGENT_REPO } else { "https://github.com/ItsNotAILABS/pocket-agent.git" }
$Dest = if ($env:POCKET_SKILLS_HOME) { $env:POCKET_SKILLS_HOME } else { Join-Path $env:USERPROFILE ".pocket\skills" }
$Tmp = Join-Path $env:TEMP ("pocket-skills-" + [guid]::NewGuid().ToString("n"))
Write-Host "==> POCKET skills → $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
git clone --depth 1 $Repo $Tmp
Copy-Item -Recurse -Force (Join-Path $Tmp "skills\*") $Dest
if (Test-Path ".\.agents" -or Test-Path ".\.claude" -or Test-Path ".\.grok") {
  New-Item -ItemType Directory -Force -Path ".\.pocket\skills" | Out-Null
  Copy-Item -Recurse -Force (Join-Path $Dest "*") ".\.pocket\skills\"
  Write-Host "Also copied to .\.pocket\skills"
}
Remove-Item -Recurse -Force $Tmp
Write-Host "OK. Catalog: $Dest\catalog.json"
