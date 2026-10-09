#!/usr/bin/env bash
# Set up unified-review in a GitHub Codespace. install.sh runs this when $CODESPACES is set.
# Each step warns and moves on if it fails, so one missing tool does not block the rest.
set -uo pipefail

warn() { echo "codespaces/setup.sh: $*" >&2; }

sudo apt-get update -qq && sudo apt-get install -y -qq poppler-utils ghostscript fontconfig \
  || warn "could not install poppler and ghostscript (PDF review will not work)"
command -v fc-cache >/dev/null && fc-cache -f >/dev/null

command -v claude >/dev/null || curl -fsSL https://claude.ai/install.sh | bash || warn "could not install claude"
command -v codex >/dev/null || npm install -g @openai/codex || warn "could not install codex"
command -v cursor-agent >/dev/null || curl -fsS https://cursor.com/install | bash || warn "could not install cursor-agent"

# A fixed port gives the review page one forwarded URL. The CLIs install into ~/.local/bin.
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  grep -qF UNIFIED_REVIEW_PORT "$rc" 2>/dev/null && continue
  printf '%s\n' 'export UNIFIED_REVIEW_PORT=${UNIFIED_REVIEW_PORT:-8737}' \
    'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
done

cat <<'MSG'
unified-review is set up. Log in to each CLI once in this codespace:
  claude          (then /login), or set a CLAUDE_CODE_OAUTH_TOKEN secret from `claude setup-token`
  codex login
  cursor-agent login, or set a CURSOR_API_KEY secret
MSG
