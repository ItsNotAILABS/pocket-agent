# irm …/install/plug.ps1 | iex
$ErrorActionPreference = "Continue"
$Base = "https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main"
Write-Host "==> POCKET plug-n-play bundle"
irm "$Base/install.ps1" | iex
irm "$Base/install/sdk.ps1" | iex
irm "$Base/install/skills.ps1" | iex
irm "$Base/install/knowledge.ps1" | iex
Write-Host ""
Write-Host "Plug-n-play ready."
Write-Host "  pocket-agent"
Write-Host "  python -c `"from pocket_sdk import Pocket; print(Pocket().health())`""
Write-Host "  Get-Content AGENTS.md"
Write-Host "  Env: POCKET_URL POCKET_TOKEN"
