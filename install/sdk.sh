#!/usr/bin/env sh
# POCKET SDK one-liner
#   curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install/sdk.sh | sh
set -eu
REPO="${POCKET_AGENT_REPO:-https://github.com/ItsNotAILABS/pocket-agent.git}"
DIR="${POCKET_SDK_HOME:-$HOME/.pocket/sdk}"
PY="${POCKET_AGENT_PYTHON:-python3}"
echo "==> POCKET SDK → $DIR"
mkdir -p "$DIR"
if [ -d "$DIR/repo/.git" ]; then
  git -C "$DIR/repo" pull --ff-only || true
else
  git clone --depth 1 "$REPO" "$DIR/repo"
fi
"$PY" -m pip install --user -e "$DIR/repo/sdk" || "$PY" -m pip install -e "$DIR/repo/sdk"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/pocket-sdk" <<'EOF'
#!/usr/bin/env sh
python3 -c "from pocket_sdk import Pocket; import json,sys; p=Pocket(); print(json.dumps(p.health() if len(sys.argv)<2 else getattr(p,sys.argv[1])(), default=str, indent=2))" "$@"
EOF
chmod +x "$HOME/.local/bin/pocket-sdk" 2>/dev/null || true
echo "OK. Try: python -c \"from pocket_sdk import Pocket; print(Pocket().health())\""
echo "Set POCKET_URL / POCKET_TOKEN for your host."
