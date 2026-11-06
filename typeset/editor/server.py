#!/usr/bin/env python3
"""edit-md: edit a Markdown file in place, in pages styled like its make-pdf PDF.

The server splits the file into blocks (paragraphs, headings, lists, tables,
comments), renders all of them in one pandoc call (so citation numbers match
the PDF), and returns each block's source beside its HTML. The page edits the
HTML and turns each edited block back into Markdown. Blocks you do not touch
are written back byte for byte.

Usage: edit-md FILE.md [--twocol] [--csl STYLE.csl] [--bibliography BIB] [--port N]
"""
import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent / "fonts"
BIB_DIR = Path(os.environ.get("BIB_DIR", Path.home() / "github" / "bib"))
MARK = "<!--BLK {}-->"
MARK_RE = re.compile(r"<!--BLK (\d+)-->")
LIST_RE = re.compile(r"(\s*)([*+-]|\d+[.)])\s")
KEY_RE = re.compile(r"@([A-Za-z0-9_][\w:.#$%&\-+?<>~/]*)")

# Page geometry, as make-pdf sets it (US Letter, 1 in margins, 11 pt) and as
# --twocol sets it (landscape, 0.75 in margins, two columns 0.4 in apart).
LAYOUTS = {
    "default": {"width": 8.5, "height": 11, "margin": 1.0, "columns": 1, "gap": 0, "twocol": False},
    "twocol": {"width": 11, "height": 8.5, "margin": 0.75, "columns": 2, "gap": 0.4, "twocol": True},
}

_bib = {"path": None, "mtime": None, "entries": {}}


def bib_entries(path):
    """Parse a .bib file once per change: key -> entry text."""
    m = path.stat().st_mtime_ns
    if _bib["path"] != path or _bib["mtime"] != m:
        entries = {}
        for e in re.split(r"\n(?=@)", path.read_text(encoding="utf-8")):
            k = re.match(r"\s*@\w+\{([^,]+),", e)
            if k:
                entries[k.group(1)] = e.strip()
        _bib.update(path=path, mtime=m, entries=entries)
    return _bib["entries"]


def split_front(text):
    m = re.match(r"---\n.*?\n---\n", text, re.S)
    return (m.group(0), text[m.end():]) if m else ("", text)


def chunk(body):
    """Split Markdown into top-level blocks: (lead, [[source, separator_after]]).
    lead + every source + separator reproduces body exactly. A list whose items
    are separated by blank lines stays one block, and so do indented
    continuation paragraphs."""
    parts = re.split(r"(\n[ \t]*\n\s*)", body)
    lead = ""
    if parts and parts[0].strip() == "":
        lead = parts[0] + (parts[1] if len(parts) > 1 else "")
        parts = parts[2:]
    chunks = []
    for i in range(0, len(parts), 2):
        src, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        if not src.strip():
            if chunks:
                chunks[-1][1] += src + sep
            else:
                lead += src + sep
            continue
        prev = chunks[-1][0] if chunks else None
        cur_item, prev_item = LIST_RE.match(src), LIST_RE.match(prev or "")
        cont = prev is not None and (
            src[:1] in " \t"
            or (cur_item and prev_item and cur_item.group(2)[-1:] == prev_item.group(2)[-1:]))
        if cont:
            chunks[-1][0] += chunks[-1][1] + src
            chunks[-1][1] = sep
        else:
            chunks.append([src, sep])
    return lead, chunks


def kind(src):
    s = src.strip()
    if s.startswith("<!--"):
        return "comment"
    if re.fullmatch(r"<a\s+id=\"[^\"]*\"\s*>\s*</a>", s):
        return "anchor"
    if re.fullmatch(r"<div[^>]*page-break[^>]*>\s*</div>", s):
        return "pagebreak"
    if s.startswith("#"):
        return "heading"
    if LIST_RE.match(src):
        return "list"
    if s.startswith("|") or re.match(r"[-+=: ]{3,}\n", s):
        return "table"
    return "para"


def find_bib(front, doc_dir, override=None):
    """The bibliography make-pdf would use: a local file, or a URL pandoc fetches.
    A front matter pointing at the jovo/bib URL reads the local clone instead."""
    if override:
        return Path(override).expanduser().resolve()
    m = re.search(r"^bibliography:\s*(\S+)", front, re.M)
    if not m:
        return None
    b = m.group(1).strip("'\"")
    local = BIB_DIR / "references.bib"
    if "githubusercontent.com/jovo/bib" in b and local.exists():
        return local
    if re.match(r"https?://", b):
        return b
    p = Path(b).expanduser()
    return p if p.is_absolute() else doc_dir / p


def render(text, doc_dir, csl=None, bib_override=None):
    front, body = split_front(text)
    lead, chunks = chunk(body)
    # One pandoc run for the whole document, with a marker before each block.
    md = "".join(f"{MARK.format(i)}\n\n{src}\n\n" for i, (src, _) in enumerate(chunks))
    args = ["pandoc", "-f", "markdown-smart-implicit_figures", "-t", "html5", "--katex",
            "--wrap=preserve", "--citeproc", "--resource-path", str(doc_dir),
            "--metadata", "link-citations=true", "--metadata", "reference-section-title=References"]
    if csl:
        args += ["--csl", str(csl)]
    tmp = Path(tempfile.mkdtemp(prefix="edit-md-"))
    try:
        bib = find_bib(front, doc_dir, bib_override)
        if isinstance(bib, Path) and bib.exists():
            # Pass only the cited entries: parsing a large file takes most of a second.
            ents = bib_entries(bib)
            keys = {k.rstrip(".:") for k in KEY_RE.findall(body)}
            (tmp / "refs.bib").write_text("\n\n".join(ents[k] for k in sorted(keys) if k in ents) + "\n",
                                          encoding="utf-8")
            args += ["--bibliography", str(tmp / "refs.bib")]
        elif isinstance(bib, str):
            args += ["--bibliography", bib]
        p = subprocess.run(args, input=md, capture_output=True, text=True, cwd=doc_dir, timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if p.returncode != 0:
        return {"error": p.stderr}
    pieces = MARK_RE.split(p.stdout)
    out = {int(pieces[i]): pieces[i + 1] for i in range(1, len(pieces) - 1, 2)}
    refs = ""
    if chunks:
        last = out.get(len(chunks) - 1, "")
        m = re.search(r'(<h[1-6][^>]*>\s*References\s*</h[1-6]>\s*)?<div id="refs"', last)
        if m:
            out[len(chunks) - 1], refs = last[:m.start()], last[m.start():]
    blocks = [{"src": src, "sep": sep, "html": out.get(i, "").strip(), "kind": kind(src)}
              for i, (src, sep) in enumerate(chunks)]
    refs_break = not re.search(r"^references-page-break:\s*false\s*$", front, re.M)
    return {"front": front, "lead": lead, "blocks": blocks, "refs": refs, "refsBreak": refs_break,
            "warnings": [l for l in p.stderr.splitlines() if l.strip()]}


class Handler(BaseHTTPRequestHandler):
    src = None      # Path of the Markdown file
    csl = None
    bib = None
    layout = LAYOUTS["default"]

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if ctype.startswith("font/") else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def mtime(self):
        # A string: nanosecond times exceed what a JavaScript number holds exactly.
        return str(self.src.stat().st_mtime_ns)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif re.fullmatch(r"/fonts/[\w-]+\.otf", path):
            f = FONTS / path[len("/fonts/"):]
            self.send(200, f.read_bytes(), "font/otf") if f.exists() else self.send(404, {})
        elif path == "/api/source":
            self.send(200, {"name": self.src.name, "text": self.src.read_text(encoding="utf-8"),
                            "mtime": self.mtime(), "layout": self.layout})
        elif path == "/api/mtime":
            self.send(200, {"mtime": self.mtime()})
        else:
            self.serve_doc_file(path)

    def serve_doc_file(self, path):
        """Figures and other files the document links to, from its own folder."""
        from urllib.parse import unquote
        root = self.src.parent.resolve()
        f = (root / unquote(path).lstrip("/")).resolve()
        if root not in f.parents or any(p.startswith(".") for p in f.relative_to(root).parts) or not f.is_file():
            self.send(404, {"error": "not found"})
            return
        self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        if path == "/api/render":
            self.send(200, render(data["text"], self.src.parent, self.csl, self.bib))
        elif path == "/api/save":
            # Refuse to overwrite a file changed on disk since the page loaded it.
            if not data.get("force") and data.get("mtime") != self.mtime():
                self.send(409, {"error": "changed on disk", "mtime": self.mtime()})
                return
            self.src.write_text(data["text"], encoding="utf-8")
            self.send(200, {"mtime": self.mtime()})
        else:
            self.send(404, {"error": "not found"})


def bind(start):
    """A server on the first free port from start. Binding, not probing, so two
    editors started at once cannot pick the same port."""
    for port in range(start, start + 20):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError:
            continue
    raise SystemExit(f"edit-md: no free port in {start}-{start + 19}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="edit-md", description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="the Markdown file to edit")
    ap.add_argument("--twocol", action="store_true",
                    help="landscape two-column pages (0.75 in margins, 0.4 in column gap)")
    ap.add_argument("--csl", help="citation style, as make-pdf --csl")
    ap.add_argument("--bibliography", help="a .bib file, instead of the front matter's")
    ap.add_argument("--port", type=int, default=8765, help="first port to try (default 8765)")
    args = ap.parse_args(argv)
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"edit-md: {args.file} is not a file")
    if not shutil.which("pandoc"):
        raise SystemExit("edit-md: pandoc is not on the PATH")
    Handler.src = src
    Handler.csl = Path(args.csl).expanduser().resolve() if args.csl else None
    Handler.bib = args.bibliography
    Handler.layout = LAYOUTS["twocol" if args.twocol else "default"]
    server = bind(args.port)
    print(f"Editing {src} at http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
