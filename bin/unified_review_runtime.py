"""Shared runtime primitives for unified-review: the model harness binaries, the
child process environment, the per-call timeout, logging, and the small text
helpers several parts of the tool use."""
import hashlib
import json
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

AGY = os.environ.get("AGY_BIN") or shutil.which("agy")  # Google's Antigravity CLI

HARNESS_BIN = {"claude": CLAUDE, "codex": CODEX, "cursor": CURSOR, "agy": AGY}

# In one-prompt mode agy runs shell commands, reads files outside its folder, and
# searches the web without asking, even with --sandbox. So a panelist runs as an
# agent with only the tools its call needs, in an empty folder of its own, with
# every other permission denied. An unknown --agent makes agy exit 1, so a missing
# file fails closed. agy cannot confine reads to a folder (its permission rules
# match only "*"), so a call that reads files can read any file the user can, as
# Codex, Cursor, and Claude can when they read files. Shell commands, writes, URL
# execution, and MCP stay denied on every call.
def agy_agent(read=False, web=False):
    """The agent file for one agy call: file reading for a PDF or figures, web
    search and page reading for a fact-check, otherwise no tools."""
    tools = ["ask_question"] + (["read_file"] if read else []) + (["search_web", "read_url_content"] if web else [])
    does = ("Read the files the prompt names. " if read else "") + ("Search the web and read pages. " if web else "")
    return ("---\nname: unified-reviewer\ndescription: Answers from the prompt"
            + (" and the files it names" if read else "") + (", and the web" if web else "") + ".\ntools:\n"
            + "".join(f"  - {x}\n" for x in tools) + "mainAgent: true\nsubagent: false\n---\n"
            + (does + "Do not change any file.\n" if read or web else "Answer from the prompt alone.\n"))


def agy_settings(read=False, web=False):
    deny = ["command(*)", "unsandboxed(*)"] + ([] if read else ["read_file(*)"]) + ["write_file(*)"] + (
        [] if web else ["read_url(*)"]) + ["execute_url(*)", "mcp(*)"]
    return json.dumps({"permissions": {"deny": deny}, "allowNonWorkspaceAccess": False}, separators=(",", ":"))


AGY_AGENT = agy_agent()  # the review's own call: no tools
AGY_SETTINGS = agy_settings()

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
