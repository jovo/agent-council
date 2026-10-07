#!/usr/bin/env bash
# Link agent-council into place: the unified-review and make-pdf commands on your PATH, and
# every skill in skills/ into Claude Code, Codex, and Cursor.
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

for tool in unified-review make-pdf; do
  chmod +x "$repo/bin/$tool"
done
link "$repo/bin/unified-review" "$bin_dir/unified-review"
link "$repo/bin/make-pdf" "$bin_dir/make-pdf"
# House fonts (New Computer Modern, GUST Font License) for PDFs, installed for the user.
font_dir=${FONT_DIR:-$HOME/Library/Fonts}
mkdir -p "$font_dir"
for f in "$repo"/typeset/fonts/*.otf; do
  cp -n "$f" "$font_dir/" 2>/dev/null && echo "installed font $(basename "$f")"
done
for skill in "$repo"/skills/*/; do
  name=$(basename "$skill")
  for agent in .claude .codex .cursor; do
    link "$repo/skills/$name" "$HOME/$agent/skills/$name"
  done
done

case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "note: add $bin_dir to your PATH" >&2 ;;
esac
