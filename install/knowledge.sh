#!/usr/bin/env sh
# curl -fsSL …/install/knowledge.sh | sh
set -eu
REPO="${POCKET_AGENT_REPO:-https://github.com/ItsNotAILABS/pocket-agent.git}"
DEST="${POCKET_KNOWLEDGE_HOME:-$HOME/.pocket/knowledge}"
TMP="${TMPDIR:-/tmp}/pocket-know-$$"
echo "==> POCKET app knowledge → $DEST"
mkdir -p "$DEST"
git clone --depth 1 "$REPO" "$TMP"
cp -R "$TMP/knowledge/." "$DEST/"
# project drop-in
mkdir -p .pocket/knowledge
cp -R "$DEST/." .pocket/knowledge/ 2>/dev/null || true
# AGENTS.md at project root for coding agents
if [ ! -f AGENTS.md ]; then
  cp "$DEST/AGENTS.md" ./AGENTS.md 2>/dev/null || true
  echo "Wrote ./AGENTS.md"
fi
rm -rf "$TMP"
echo "OK. Knowledge at $DEST and ./.pocket/knowledge"
echo "Plug-n-play: .pocket/knowledge/plug-n-play/"
