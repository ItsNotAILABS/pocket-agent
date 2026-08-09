# irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/sdk.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo = if ($env:POCKET_AGENT_REPO) { $env:POCKET_AGENT_REPO } else { "https://github.com/ItsNotAILABS/pocket-agent.git" }
$Dir = if ($env:POCKET_SDK_HOME) { $env:POCKET_SDK_HOME } else { Join-Path $env:USERPROFILE ".pocket\sdk" }
$Py = if ($env:POCKET_AGENT_PYTHON) { $env:POCKET_AGENT_PYTHON } else { "python" }
Write-Host "==> POCKET SDK → $Dir"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$repoDir = Join-Path $Dir "repo"
if (Test-Path (Join-Path $repoDir ".git")) { git -C $repoDir pull --ff-only } else { git clone --depth 1 $Repo $repoDir }
& $Py -m pip install --user -e (Join-Path $repoDir "sdk")
Write-Host "OK. python -c `"from pocket_sdk import Pocket; print(Pocket().health())`""
Write-Host "Set POCKET_URL and POCKET_TOKEN for remote host."
