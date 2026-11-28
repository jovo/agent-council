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
import json
import os
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
PROTOCOL = "2025-06-18"
RUNNING = {}  # job id -> Popen, for jobs this server started

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


def run_cli(args, cwd):
    r = subprocess.run([sys.executable, str(CLI), *args], cwd=cwd, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=120)
    return (r.stdout + ("\n" + r.stderr if r.returncode else "")).strip(), r.returncode != 0


def draft(path):
    p = Path(path).expanduser()
    if not p.is_absolute() or not p.is_file():
        raise ValueError(f"not a file (give an absolute path): {path}")
    return p


def start_review(a):
    f = draft(a["file"])
    args = []
    if a.get("panel"):
        args += ["-p", a["panel"]]
    if a.get("focus"):
        args += ["-n", a["focus"]]
    for c in a.get("context") or []:
        args += ["--context", str(draft(c))]
    if a.get("verify"):
        args.append("--verify")
    job = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    d = JOBS / job
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"file": str(f), "args": args, "started": time.time()}))
    with open(d / "stdout.txt", "w") as out, open(d / "log.txt", "w") as log:
        RUNNING[job] = subprocess.Popen([sys.executable, str(CLI), *args, str(f)], cwd=f.parent, stdout=out,
                                        stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    return f"Review started. Job: {job}. Call review_status with this job in about a minute."


def status(a):
    job = a["job"]
    d = JOBS / job
    if "/" in job or not (d / "job.json").exists():
        raise ValueError(f"no such job: {job}")
    p = RUNNING.get(job)
    code = p.poll() if p else None
    out = (d / "stdout.txt").read_text()
    log = (d / "log.txt").read_text().strip().splitlines()
    notes = next((l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("Notes: ")), None)
    done = code is not None or (p is None and notes)
    if not done:
        return ("Running" if p else "Unknown: this server did not start the job, and it has written no notes yet") + \
            ". Latest progress:\n" + "\n".join(log[-6:])
    if code not in (None, 0):
        return f"Failed (exit {code}). Last log lines:\n" + "\n".join(log[-15:])
    unified = out.strip().splitlines()[-1] if out.strip() else ""
    return "\n".join(x for x in ["Done.", f"Notes file: {notes}" if notes else "",
                                 f"Full review: {unified}" if unified.endswith(".md") else "",
                                 "Log:", *log[-8:]] if x)


def item(a):
    f = draft(a["file"])
    text, failed = run_cli(["--item", a["items"]], f.parent)
    if failed:
        raise ValueError(text)
    return text


def decide(a):
    f = draft(a["file"])
    flag = {"applied": "--applied", "ignore": "--ignore"}[a["decision"]]
    args = [flag, a["items"]] + (["--note", a["note"]] if a.get("note") else [])
    text, failed = run_cli(args, f.parent)
    if failed:
        raise ValueError(text)
    return text or "Recorded."


HANDLERS = {"review": start_review, "review_status": status, "review_item": item, "review_decide": decide}


def handle(msg):
    """The reply to one JSON-RPC message, or None for a notification."""
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if mid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "agent-council", "version": VERSION}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        fn = HANDLERS.get(params.get("name"))
        if not fn:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {params.get('name')}"}}
        try:
            result = {"content": [{"type": "text", "text": fn(params.get("arguments") or {})}], "isError": False}
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
            reply = handle(msg) if isinstance(msg, dict) else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
