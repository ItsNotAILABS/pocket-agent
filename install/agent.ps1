# POCKET Agent installer (Windows)
#   irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo = if ($env:POCKET_AGENT_REPO) { $env:POCKET_AGENT_REPO } else { "https://github.com/ItsNotAILABS/pocket-agent.git" }
$InstallDir = if ($env:POCKET_AGENT_HOME) { $env:POCKET_AGENT_HOME } else { Join-Path $env:USERPROFILE ".pocket\agent-install" }
$BinDir = if ($env:POCKET_AGENT_BIN) { $env:POCKET_AGENT_BIN } else { Join-Path $env:USERPROFILE ".local\bin" }
$Py = if ($env:POCKET_AGENT_PYTHON) { $env:POCKET_AGENT_PYTHON } else { "python" }

Write-Host "==> POCKET Agent installer (Windows)"
New-Item -ItemType Directory -Force -Path $InstallDir, $BinDir | Out-Null

if (Test-Path (Join-Path $InstallDir ".git")) {
  git -C $InstallDir pull --ff-only
} else {
  git clone --depth 1 $Repo $InstallDir
}

& $Py -m pip install --user -e $InstallDir

$shim = @"
@echo off
$Py -m pocket_agent.cli %*
"@
Set-Content -Path (Join-Path $BinDir "pocket-agent.cmd") -Value $shim -Encoding ASCII
Set-Content -Path (Join-Path $BinDir "prime-agent.cmd") -Value $shim -Encoding ASCII

& $Py -c "from pathlib import Path; p=Path.home()/'.pocket'/'agent'; p.mkdir(parents=True, exist_ok=True); print('runtime', p)"

Write-Host ""
Write-Host "Installed. Add to PATH if needed: $BinDir"
Write-Host "  cd path\to\project"
Write-Host "  pocket-agent"
Write-Host "Warning: not a security sandbox. Use: pocket-agent capsule spin --reason untrusted_eval"
