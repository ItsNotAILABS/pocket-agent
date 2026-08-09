#!/usr/bin/env sh
# curl -fsSL …/install/skills.sh | sh
set -eu
REPO="${POCKET_AGENT_REPO:-https://github.com/ItsNotAILABS/pocket-agent.git}"
DEST="${POCKET_SKILLS_HOME:-$HOME/.pocket/skills}"
TMP="${TMPDIR:-/tmp}/pocket-skills-$$"
echo "==> POCKET skills → $DEST"
mkdir -p "$DEST"
git clone --depth 1 "$REPO" "$TMP"
cp -R "$TMP/skills/." "$DEST/"
rm -rf "$TMP"
# also drop into cwd .agents/skills if present
if [ -d ".agents" ] || [ -d ".claude" ] || [ -d ".grok" ]; then
  mkdir -p .pocket/skills
  cp -R "$DEST/." .pocket/skills/ 2>/dev/null || true
  echo "Also copied to ./.pocket/skills for this project"
fi
echo "OK. Catalog: $DEST/catalog.json"
echo "AGENTS: point your agent at $DEST and knowledge/AGENTS.md"
