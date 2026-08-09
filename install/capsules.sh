#!/usr/bin/env sh
# curl -fsSL …/install/capsules.sh | sh
set -eu
# Capsules ship inside pocket-agent; install agent CLI if missing
if ! command -v pocket-agent >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.sh | sh
fi
echo "==> WASM capsule reasons"
pocket-agent capsule reasons || python3 -m pocket_agent.cli capsule reasons
mkdir -p "$HOME/.pocket/knowledge"
curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/docs/WASM_CAPSULES.md \
  -o "$HOME/.pocket/knowledge/WASM_CAPSULES.md" 2>/dev/null || true
echo "Spin: pocket-agent capsule spin --reason untrusted_eval"
echo "OK."
