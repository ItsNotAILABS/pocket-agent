#!/usr/bin/env sh
# Operator host notes + agent tools (full desk is pocket-os clone)
set -eu
echo "==> POCKET host slice"
echo "Full host source typically lives in pocket-os (operator machine)."
echo ""
echo "If pocket-os is checked out:"
echo "  export PYTHONPATH=/path/to/pocket-os/src"
echo "  python -m pocket serve --host 0.0.0.0 --port 8787"
echo "  Desk: http://127.0.0.1:8787/desk"
echo ""
echo "Also installing agent + SDK for the same machine…"
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/plug.sh | sh
echo ""
echo "Host APIs (when serve is up):"
echo "  GET  /health  /v1/protocols  /v1/economy  /v1/identity  /v1/rah/status"
echo "  POST /v1/auth/login  /v1/sessions  /v1/rah/run  /v1/economy/transfer"
echo "OK."
