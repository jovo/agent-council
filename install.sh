#!/usr/bin/env bash
# Link agent-council into place: the unified-review command on your PATH, and
# the unified-review skill into Claude Code, Codex, and Cursor.
set -euo pipefail

repo=$(cd "$(dirname "$0")" && pwd)
bin_dir=${BIN_DIR:-$HOME/.local/bin}

link() {  # link SOURCE TARGET, refusing to replace a real file or folder
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "skip $2: exists and is not a symlink (move it aside to install)" >&2
    return
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
  echo "linked $2 -> $1"
}

chmod +x "$repo/bin/unified-review"
link "$repo/bin/unified-review" "$bin_dir/unified-review"
for agent in .claude .codex .cursor; do
  link "$repo/skills/unified-review" "$HOME/$agent/skills/unified-review"
done

case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "note: add $bin_dir to your PATH" >&2 ;;
esac
