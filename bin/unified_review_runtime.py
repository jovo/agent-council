"""Shared runtime primitives for unified-review: the model harness binaries, the
child process environment, the per-call timeout, logging, and the small text
helpers several parts of the tool use."""
import hashlib
import os
import re
import shutil
import sys

TIMEOUT = int(os.environ.get("UNIFIED_REVIEW_TIMEOUT", "900"))

CLAUDE = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
# The ChatGPT app has shipped its Codex CLI at more than one path. Take the first that exists.
CODEX = (os.environ.get("CODEX_BIN") or shutil.which("codex")
         or next((c for c in ["/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
                              "/Applications/ChatGPT.app/Contents/Resources/codex"]
                  if os.access(c, os.X_OK)), "codex"))
CURSOR = os.environ.get("CURSOR_BIN") or shutil.which("cursor-agent")

HARNESS_BIN = {"claude": CLAUDE, "codex": CODEX, "cursor": CURSOR}

# When launched from inside Claude Code, Codex, or Cursor, the parent agent's
# session variables leak into the child CLIs and break their auth. Drop them.
LEAKY = re.compile(r"^(CLAUDECODE|CLAUDE_CODE_|CLAUDE_AGENT_SDK_|CODEX_SANDBOX|CURSOR_AGENT)")
CHILD_ENV = {k: v for k, v in os.environ.items() if not LEAKY.match(k)}
# Outside Claude Code, CLAUDE_CODE_OAUTH_TOKEN is the user's own login token (from
# `claude setup-token`, e.g. a Codespaces secret), so keep it.
if "CLAUDECODE" not in os.environ and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
    CHILD_ENV["CLAUDE_CODE_OAUTH_TOKEN"] = os.environ["CLAUDE_CODE_OAUTH_TOKEN"]


def log(msg):
    print(msg, file=sys.stderr, flush=True)


QUOTES = str.maketrans("‘’“”", "''\"\"")  # curly quotes, as in PDFs, match straight ones


def fingerprint(text):
    """Short content hash that names a version of a file."""
    return "v" + hashlib.sha256(text.encode()).hexdigest()[:7]


# Inline markup a reviewer quoting the text as it reads leaves out: bold and italic
# asterisks, underline and super- and subscript tags (as Word files bring), and the
# backslash of an escaped character (\# for #).
MARKUP = re.compile(r"\*\*|(?<!\\)\*|</?(?:u|sup|sub)>|\\(?=[!-/:-@\[-`{-~])")


def plain_view(text):
    """(text without inline markup, idx) where idx[i] is the position in text of
    the plain text's character i."""
    plain, idx, at = [], [], 0
    for m in MARKUP.finditer(text):
        plain.append(text[at:m.start()])
        idx.extend(range(at, m.start()))
        at = m.end()
    plain.append(text[at:])
    idx.extend(range(at, len(text)))
    return "".join(plain), idx
