#!/usr/bin/env sh
# POCKET Agent installer (Prime-style one-liner)
#   curl -fsSL https://raw.githubusercontent.com/ItsNotAILABS/pocket-agent/main/install.sh | sh
#
# Downloads/clones the repo, installs the pocket-agent command, prepares Python runtime.
set -eu

REPO_URL="${POCKET_AGENT_REPO:-https://github.com/ItsNotAILABS/pocket-agent.git}"
INSTALL_DIR="${POCKET_AGENT_HOME:-$HOME/.pocket/agent-install}"
BIN_DIR="${POCKET_AGENT_BIN:-$HOME/.local/bin}"
PYTHON="${POCKET_AGENT_PYTHON:-python3}"

echo "==> POCKET Agent installer"
echo "    repo: $REPO_URL"
echo "    dir:  $INSTALL_DIR"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found (need Python 3.11+)" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "==> Updating existing clone"
  git -C "$INSTALL_DIR" pull --ff-only || true
else
  echo "==> Cloning"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# Optional checksum file if release artifacts present
if [ -f "$INSTALL_DIR/SHA256SUMS" ]; then
  echo "==> Verifying SHA-256 (SHA256SUMS)"
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$INSTALL_DIR" && sha256sum -c SHA256SUMS --ignore-missing) || true
  fi
fi

echo "==> Installing package (user)"
"$PYTHON" -m pip install --user -e "$INSTALL_DIR" || "$PYTHON" -m pip install -e "$INSTALL_DIR"

# shim
cat > "$BIN_DIR/pocket-agent" <<EOF
#!/usr/bin/env sh
exec "$PYTHON" -m pocket_agent.cli "\$@"
EOF
chmod +x "$BIN_DIR/pocket-agent"

# also prime-agent alias for muscle memory
cp "$BIN_DIR/pocket-agent" "$BIN_DIR/prime-agent" 2>/dev/null || true

echo "==> Preparing control runtime"
"$PYTHON" - <<'PY'
import pathlib
p = pathlib.Path.home() / ".pocket" / "agent"
for d in ("sessions", "schedules", "harness", "bus", "capsules"):
    (p / d if d != "capsules" else pathlib.Path.home() / ".pocket" / "capsules").mkdir(parents=True, exist_ok=True)
print("runtime dirs ok:", p)
PY

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo ""
    echo "Add to PATH:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

echo ""
echo "Installed. Start in a project directory:"
echo "  cd /path/to/project"
echo "  pocket-agent"
echo ""
echo "Warning: executes model-generated Python with your user permissions."
echo "Not a security sandbox — use: pocket-agent capsule spin --reason untrusted_eval"
echo "Useful: pocket-agent agents | attach <id> | status | doctor --fix | capsule reasons"
