# irm …/install/capsules.ps1 | iex
$ErrorActionPreference = "Continue"
if (-not (Get-Command pocket-agent -ErrorAction SilentlyContinue)) {
  irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.ps1 | iex
}
Write-Host "==> WASM capsule reasons"
try { pocket-agent capsule reasons } catch { python -m pocket_agent.cli capsule reasons }
$k = Join-Path $env:USERPROFILE ".pocket\knowledge"
New-Item -ItemType Directory -Force -Path $k | Out-Null
try {
  Invoke-WebRequest -UseBasicParsing `
    "https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/docs/WASM_CAPSULES.md" `
    -OutFile (Join-Path $k "WASM_CAPSULES.md")
} catch {}
Write-Host "Spin: pocket-agent capsule spin --reason untrusted_eval"
Write-Host "OK."
