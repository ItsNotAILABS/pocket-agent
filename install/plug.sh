#!/usr/bin/env sh
# Full agent plug-n-play: agent + sdk + skills + knowledge
#   curl -fsSL …/install/plug.sh | sh
set -eu
BASE="https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main"
echo "==> POCKET plug-n-play bundle"
curl -fsSL "$BASE/install.sh" | sh
curl -fsSL "$BASE/install/sdk.sh" | sh
curl -fsSL "$BASE/install/skills.sh" | sh
curl -fsSL "$BASE/install/knowledge.sh" | sh
echo ""
echo "Plug-n-play ready."
echo "  pocket-agent"
echo "  python -c \"from pocket_sdk import Pocket; print(Pocket().health())\""
echo "  cat AGENTS.md   # or .pocket/knowledge/AGENTS.md"
echo "  Env: POCKET_URL POCKET_TOKEN"
