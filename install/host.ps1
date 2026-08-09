# irm …/install/host.ps1 | iex
Write-Host "==> POCKET host slice"
Write-Host "Full host: pocket-os  →  python -m pocket serve --port 8787"
Write-Host "Desk: http://127.0.0.1:8787/desk"
Write-Host "Installing agent plug-n-play on this machine…"
irm https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/plug.ps1 | iex
Write-Host "Host APIs: /health /v1/protocols /v1/economy /v1/identity"
Write-Host "OK."
