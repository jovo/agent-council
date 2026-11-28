#!/usr/bin/env python3
"""agent-council MCP server: unified-review for any MCP client (Copilot, VS Code, Claude).

A stdio server with no dependencies beyond Python 3.9. It speaks the MCP
JSON-RPC protocol, one message per line, and runs bin/unified-review from this
repository. A review takes minutes, longer than many clients wait for one tool
call, so review starts it in the background and review_status reports on it.

Tools:
  review          start a review of a file; returns a job id
  review_status   a job's progress, and the notes file when it is done
  review_item     a finding's current text, location, and diff, by number
  review_decide   record findings as applied or declined
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "unified-review"
JOBS = Path(os.environ.get("UNIFIED_REVIEW_MCP_JOBS",
                           Path.home() / ".local" / "share" / "unified-review" / "mcp-jobs"))
VERSION = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text()).get("version", "0")
SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"]  # MCP protocol versions, newest first
JOB_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
# Drafts must sit under these folders (os.pathsep-separated), resolved through
# symlinks. The default is the home folder. A path through a hidden folder
# (~/.ssh, ~/.config) is refused, since the review sends the file's text to the
# panel's model CLIs.
ROOTS = [Path(r).expanduser().resolve() for r in
         os.environ.get("UNIFIED_REVIEW_MCP_ROOTS", str(Path.home())).split(os.pathsep) if r]
_CLI_MODULE = None

TOOLS = [
    {"name": "review",
     "description": "Start a unified review of a draft (Markdown, Word, or PDF). GPT and Gemini review and vote "
                    "on each other's findings, and Claude Opus settles disputes. Takes 1 to 5 minutes. Returns a "
                    "job id: call review_status with it. The review writes notes/review.md beside the draft.",
     "inputSchema": {"type": "object", "properties": {
         "file": {"type": "string", "description": "Absolute path of the draft to review."},
         "panel": {"type": "string", "description": "Reviewers, comma-separated, e.g. 'gpt,argon'. Omit for the default."},
         "focus": {"type": "string", "description": "Extra focus for the reviewers."},
         "context": {"type": "array", "items": {"type": "string"},
                     "description": "Absolute paths of supporting files the panel reads but does not review."},
         "verify": {"type": "boolean", "description": "Also run the web fact-check."}},
         "required": ["file"]}},
    {"name": "review_status",
     "description": "Report a review job: running with its latest progress lines, or done with the notes file's path.",
     "inputSchema": {"type": "object", "properties": {"job": {"type": "string"}}, "required": ["job"]}},
    {"name": "review_item",
     "description": "Print numbered findings from the latest review of a file: each one's current line, quoted "
                    "text, votes, and diff, and the file's current text. Run this before applying a finding.",
     "inputSchema": {"type": "object", "properties": {
         "file": {"type": "string", "description": "Absolute path of the reviewed draft."},
         "items": {"type": "string", "description": "Finding numbers from unified.md, e.g. '3' or '2,4,7' or '3b'."}},
         "required": ["file", "items"]}},
    {"name": "review_decide",
     "description": "Record findings as applied or declined, so the next review neither raises them again nor forgets them.",
     "inputSchema": {"type": "object", "properties": {
         "file": {"type": "string", "description": "Absolute path of the reviewed draft."},
         "decision": {"type": "string", "enum": ["applied", "ignore"]},
         "items": {"type": "string", "description": "Finding numbers, e.g. '3,4'."},
         "note": {"type": "string", "description": "The author's reason, if given."}},
         "required": ["file", "decision", "items"]}},
]


def cli_module():
    """bin/unified-review as a module, for its run lookup."""
    global _CLI_MODULE
    if _CLI_MODULE is None:
        sys.path.insert(0, str(CLI.parent))
        loader = importlib.machinery.SourceFileLoader("unified_review_cli", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        _CLI_MODULE = importlib.util.module_from_spec(spec)
        loader.exec_module(_CLI_MODULE)
    return _CLI_MODULE


def run_of(f):
    """The newest review run of exactly this file (of its Markdown copy, for a
    Word file or PDF), so --item and decisions never land on another draft's review."""
    ur = cli_module()
    target = ur.converted_path(f) if (ur.is_docx(f) or ur.is_pdf(f)) else f
    runs = ur.runs_for(target.resolve())
    if not runs:
        raise ValueError(f"no review of {f} yet: run review first")
    return runs[0]


def run_cli(args, cwd):
    r = subprocess.run([sys.executable, str(CLI), *args], cwd=cwd, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=120)
    return (r.stdout + ("\n" + r.stderr if r.returncode else "")).strip(), r.returncode != 0


def text_arg(a, key, required=True):
    v = a.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return v


def draft(path):
    if not isinstance(path, str):
        raise ValueError("a file path must be a string")
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError(f"give an absolute path: {path}")
    real = p.resolve()
    if not real.is_file():
        raise ValueError(f"not a file: {path}")
    root = next((r for r in ROOTS if real == r or r in real.parents), None)
    if root is None:
        raise ValueError(f"{path} is outside the allowed folders ({os.pathsep.join(map(str, ROOTS))}); "
                         "set UNIFIED_REVIEW_MCP_ROOTS to widen them")
    if any(part.startswith(".") for part in real.relative_to(root).parts):
        raise ValueError(f"{path} is in a hidden folder, which may hold secrets: refused")
    return real


def start_review(a):
    f = draft(a.get("file"))
    args = []
    if a.get("panel") is not None:
        args += ["-p", text_arg(a, "panel")]
    if a.get("focus") is not None:
        args += ["-n", text_arg(a, "focus")]
    ctx = a.get("context") or []
    if not isinstance(ctx, list):
        raise ValueError("context must be a list of paths")
    for c in ctx:
        args += ["--context", str(draft(c))]
    if a.get("verify") is True:
        args.append("--verify")
    job = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    d = JOBS / job
    d.mkdir(parents=True)
    # The shell records the exit code in a file, so a job's end is known even
    # after this server restarts. The arguments pass as "$@", never through the shell's parser.
    cmd = ["/bin/sh", "-c", '"$@"; echo $? > "$0"', str(d / "exit"), sys.executable, str(CLI), *args, str(f)]
    with open(d / "stdout.txt", "w") as out, open(d / "log.txt", "w") as log:
        proc = subprocess.Popen(cmd, cwd=f.parent, stdout=out, stderr=log, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    (d / "job.json").write_text(json.dumps({"file": str(f), "args": args, "pid": proc.pid,
                                            "verify": "--verify" in args, "started": time.time()}))
    return f"Review started. Job: {job}. Call review_status with this job in about a minute."


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(a):
    job = text_arg(a, "job")
    if not JOB_ID.fullmatch(job):
        raise ValueError(f"no such job: {job}")
    d = JOBS / job
    if not (d / "job.json").exists():
        raise ValueError(f"no such job: {job}")
    info = json.loads((d / "job.json").read_text())
    log = (d / "log.txt").read_text().strip().splitlines()
    if not (d / "exit").exists():
        if alive(info.get("pid", -1)):
            return "Running. Latest progress:\n" + "\n".join(log[-6:])
        return "Stopped without finishing (its process is gone). Last log lines:\n" + "\n".join(log[-15:])
    code = (d / "exit").read_text().strip()
    if code != "0":
        return f"Failed (exit {code}). Last log lines:\n" + "\n".join(log[-15:])
    out = (d / "stdout.txt").read_text()
    notes = next((l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("Notes: ")), None)
    unified = out.strip().splitlines()[-1] if out.strip() else ""
    lines = ["Done.", f"Notes file: {notes}" if notes else "", f"Full review: {unified}" if unified.endswith(".md") else ""]
    if info.get("verify") and unified.endswith(".md"):
        fc = Path(unified).with_name("factcheck.md")
        lines.append(f"Fact-check: done, {fc}" if fc.exists() else
                     f"Fact-check: still running in the background. It writes {fc} when done.")
    return "\n".join(x for x in lines + ["Log:", *log[-8:]] if x)


def item(a):
    f = draft(a.get("file"))
    text, failed = run_cli(["--item", text_arg(a, "items"), "--run", str(run_of(f))], f.parent)
    if failed:
        raise ValueError(text)
    return text


def decide(a):
    f = draft(a.get("file"))
    flag = {"applied": "--applied", "ignore": "--ignore"}.get(a.get("decision"))
    if not flag:
        raise ValueError("decision must be applied or ignore")
    note = text_arg(a, "note", required=False)
    args = [flag, text_arg(a, "items"), "--run", str(run_of(f))] + (["--note", note] if note else [])
    text, failed = run_cli(args, f.parent)
    if failed:
        raise ValueError(text)
    return text or "Recorded."


HANDLERS = {"review": start_review, "review_status": status, "review_item": item, "review_decide": decide}


def handle(msg):
    """The reply to one JSON-RPC message, or None for a notification."""
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params")
    params = {} if params is None else params
    if mid is None:
        return None
    if not isinstance(method, str) or not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32600, "message": "invalid request"}}
    if method == "initialize":
        asked = params.get("protocolVersion")
        result = {"protocolVersion": asked if asked in SUPPORTED else SUPPORTED[0],
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "agent-council", "version": VERSION}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments")
        args = {} if args is None else args
        fn = HANDLERS.get(name) if isinstance(name, str) else None
        if not fn or not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool or bad arguments: {name!r}"}}
        try:
            result = {"content": [{"type": "text", "text": fn(args)}], "isError": False}
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
            result = {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            try:
                reply = handle(msg) if isinstance(msg, dict) else None
            except Exception as e:  # one bad message never stops the server
                mid = msg.get("id") if isinstance(msg, dict) else None
                reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"internal error: {e}"}} \
                    if mid is not None else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
