"""Run store for unified-review: where reviews, decisions, and file versions are
kept on disk under RUNS_DIR, and how runs are found."""
import json
import os
import sys
from pathlib import Path

import unified_review_runtime as runtime

LAST_RUN = Path.home() / ".local/state/unified-review/last-run"
# Runs live in one folder outside every project.
RUNS_DIR = Path(os.environ.get("UNIFIED_REVIEW_RUNS") or Path.home() / ".local/share/unified-review/runs")
RUN_METADATA = {}  # results.json path -> (mtime_ns, reviewed files)


# The author's decisions on past findings, per reviewed file, in RUNS_DIR/decisions.json:
# {path: [{"id": "D1", "decision": "ignore" | "applied" | "lifted", "title", "quote",
#          "point", "severity", "note", "version", "run", "date"}]}

def load_decisions():
    f = RUNS_DIR / "decisions.json"
    return json.loads(f.read_text()) if f.exists() else {}


def show_decisions(here):
    """List recorded decisions for reviewed files under a folder, newest last."""
    dec = load_decisions()
    shown = 0
    for path, entries in sorted(dec.items()):
        if not (path == here or path.startswith(here + os.sep)):
            continue
        print(f"== {path}")
        for d in entries:
            note = f"  Note: {d['note']}" if d.get("note") else ""
            print(f"{d['id']}  {d['decision']:<8} {d.get('date', '')}  version {d.get('version') or '?'}  "
                  f"{d['title']}  (run {d.get('run', '?')}){note}")
            shown += 1
    if not shown:
        print(f"No recorded decisions for files under {here}.")


def decision_for(run_name, title):
    """The latest recorded decision on a finding from a given run, if any."""
    hits = [d for ds in load_decisions().values() for d in ds
            if d.get("run") == run_name and d["title"] == title]
    return hits[-1] if hits else None


def write_atomic(path, text):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    tmp.replace(path)


def version_number(path, fp, register=True):
    """SVN-style version of a file: 1 for the first text reviewed, 2 for the next
    different text, and so on. Unchanged text keeps its number. The registry
    lives in RUNS_DIR/versions.json. Returns None for unseen text if not register."""
    reg_file = RUNS_DIR / "versions.json"
    reg = json.loads(reg_file.read_text()) if reg_file.exists() else {}
    seen = reg.setdefault(str(path), [])
    if fp not in seen:
        if not register:
            return None
        seen.append(fp)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        write_atomic(reg_file, json.dumps(reg, indent=1) + "\n")
    return seen.index(fp) + 1


def version_text(v):
    g = v.get("git") or {}
    gtxt = (f", git {g['commit']}" + (" plus uncommitted edits" if g["dirty"] else "")) if g else ""
    name = f"version {v['number']}" if v.get("number") else f"version `{v['version']}`"
    return name + gtxt


def latest_run():
    """Newest run that reviewed a file under the current folder, else the last run made."""
    here = str(Path.cwd().resolve())
    runs = []
    for rj in RUNS_DIR.glob("*/results.json"):
        try:
            files = json.loads(rj.read_text()).get("files", [])
        except ValueError:
            continue
        if any(f == here or f.startswith(here + os.sep) for f in files):
            runs.append(rj)
    if runs:
        return max(runs, key=lambda p: p.stat().st_mtime).parent
    if LAST_RUN.exists() and (Path(LAST_RUN.read_text().strip()) / "results.json").exists():
        return Path(LAST_RUN.read_text().strip())
    sys.exit(f"error: no unified-review run found in {RUNS_DIR}")


def reviewed_history(path, current):
    """Earlier reviewed texts of a file, oldest first, one per version, not
    counting the current text."""
    seen, out = {runtime.fingerprint(current)}, []
    for run in reversed(runs_for(Path(path).resolve())):
        copy = run / "reviewed" / Path(path).name
        if copy.exists():
            t = copy.read_text()
            if runtime.fingerprint(t) not in seen:
                seen.add(runtime.fingerprint(t))
                out.append(t)
    return out


def runs_for(path):
    """Run folders that reviewed exactly this file, newest first."""
    target, out, seen = str(path), [], set()
    for rj in RUNS_DIR.glob("*/results.json"):
        seen.add(rj)
        try:
            stamp = rj.stat().st_mtime_ns
            cached = RUN_METADATA.get(rj)
            if not cached or cached[0] != stamp:
                cached = (stamp, json.loads(rj.read_text()).get("files"))
                RUN_METADATA[rj] = cached
            if cached[1] == [target]:
                out.append((stamp, rj.parent))
        except (OSError, ValueError):
            continue
    for rj in list(RUN_METADATA):
        if rj not in seen:
            RUN_METADATA.pop(rj, None)  # another thread may have pruned it
    return [run for _, run in sorted(out, key=lambda row: row[0], reverse=True)]
