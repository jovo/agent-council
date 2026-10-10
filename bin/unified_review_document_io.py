"""Document conversion, export, and bibliography support for unified-review."""
import collections
import copy
import difflib
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

RUNS_DIR = Path(os.environ.get("UNIFIED_REVIEW_RUNS") or Path.home() / ".local/share/unified-review/runs")
TIMEOUT = int(os.environ.get("UNIFIED_REVIEW_TIMEOUT", "900"))
CLAUDE = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
LEAKY = re.compile(r"^(CLAUDECODE|CLAUDE_CODE_|CLAUDE_AGENT_SDK_|CODEX_SANDBOX|CURSOR_AGENT)")
CHILD_ENV = {k: v for k, v in os.environ.items() if not LEAKY.match(k)}
QUOTES = str.maketrans("‘’“”", "''\"\"")
MARKUP = re.compile(r"\*\*|(?<!\\)\*|</?(?:u|sup|sub)>|\\(?=[!-/:-@\[-`{-~])")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def fingerprint(text):
    """Short content hash that names a version of a file."""
    return "v" + hashlib.sha256(text.encode()).hexdigest()[:7]


def plain_view(text):
    """(text without inline markup, idx) where idx[i] indexes the source text."""
    plain, idx, at = [], [], 0
    for m in MARKUP.finditer(text):
        plain.append(text[at:m.start()])
        idx.extend(range(at, m.start()))
        at = m.end()
    plain.append(text[at:])
    idx.extend(range(at, len(text)))
    return "".join(plain), idx


def is_pdf(p):
    return Path(p).suffix.lower() == ".pdf"


def is_docx(p):
    return Path(p).suffix.lower() == ".docx"


def doc_text(p):
    """A file's text. The panel reads a PDF itself. The script uses its text,
    pages separated by form feeds, only to place quotes and number versions."""
    p = Path(p)
    if is_docx(p):
        r = subprocess.run(["pandoc", str(p), "-t", "plain", "--wrap=none"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"error: could not read {p} (is pandoc installed?)")
        return r.stdout
    if not is_pdf(p):
        return p.read_text()
    r = subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True)
    return re.sub(r"(\w)-\n(?=[a-z])", r"\1", r.stdout)  # rejoin words hyphenated at line ends


MATH_FONT = re.compile(r"Math|CMMI|CMSY|CMEX|MSAM|MSBM|STIX|Symbol", re.I)
PGM = re.compile(rb"P5\s+(?:#[^\n]*\n\s*)*(\d+)\s+(\d+)\s+\d+\s")  # a page of gs output


def pdf_extras(p):
    """What pdftotext would miss in a PDF: graphics (figures, images, table
    rules: ink left on a page rendered without its text) or equations (by their
    fonts). Empty when the text alone carries the document."""
    out = []
    pages = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dFILTERTEXT",
                            "-sDEVICE=pgmraw", "-r18", "-sOutputFile=-", str(p)], capture_output=True).stdout
    i = 0
    while (m := PGM.match(pages, i)):
        n = int(m.group(1)) * int(m.group(2))
        i = m.end() + n
        if sum(b < 200 for b in pages[m.end():i]) > 0.005 * n:
            out.append("graphics")
            break
    fonts = subprocess.run(["pdffonts", str(p)], capture_output=True, text=True).stdout
    if MATH_FONT.search(fonts):
        out.append("equations")
    return out


TO_MD = """Convert this PDF to GitHub-flavored Markdown: {path}
Read every page. Copy the text exactly, word for word: do not fix, reword,
summarize, or drop anything. Use # headings for the document's headings,
Markdown tables for tables (join a table that continues onto the next page),
$...$ and $$...$$ for math, and [text](url) for links. Keep each figure's
caption as a paragraph. Separate paragraphs with blank lines. Leave out page
numbers and running headers and footers. Output only the Markdown, with no
note or comment of your own.
{links}"""


def pdf_links(p):
    """(link text, URL) pairs for a PDF's web links, in page order. A model
    reading the PDF sees the link text but not where it points."""
    import html
    r = subprocess.run(["pdftohtml", "-xml", "-i", "-stdout", "-q", str(p)], capture_output=True, text=True)
    out = []
    for url, text in re.findall(r'<a href="((?:https?|mailto):[^"]+)">(.*?)</a>', r.stdout, re.S):
        url, text = html.unescape(url), " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())
        if out and out[-1][1] == url:  # one link split across lines or runs of text
            out[-1] = (out[-1][0] + " " + text, url)
        else:
            out.append((text, url))
    return [(t.strip(" .,;:()"), u) for t, u in out if t.strip(" .,;:()")]


def words(text):
    return collections.Counter(re.findall(r"\w+", text.translate(QUOTES).lower()))


def conversion_gaps(pdf, md):
    """(words of the PDF missing from the Markdown, words the Markdown added),
    counting repeats. Left out: link targets and HTML tags in the Markdown, and
    page numbers and running headers and footers in the PDF."""
    raw = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    md = re.sub(r"<[^>]+>", " ", re.sub(r"\]\([^)\s]*\)", "]", md))
    # A running header or footer: the same line among the first or last three of every page.
    pages = [[l.strip() for l in pg.splitlines() if l.strip()] for pg in raw.split("\f") if pg.strip()]
    edges = [set(pg[:3] + pg[-3:]) for pg in pages]
    running = set.intersection(*edges) if len(edges) > 1 else set()
    page_number = lambda l: l.strip().isdigit() and int(l) <= len(pages)
    raw = "\n".join(l for l in raw.splitlines() if l.strip() not in running and not page_number(l))
    # A word hyphenated at a line end is one word if the Markdown has it joined.
    joined = set(words(md))
    raw = re.sub(r"(\w+)-\n\s*(\w+)", lambda m: m[1] + m[2] if (m[1] + m[2]).lower() in joined
                 else f"{m[1]}-{m[2]}", raw)
    a = words(raw)
    # pdftotext can drop a hyphen the page shows ("fine-tuning" reads "finetuning").
    # Join as many of the Markdown's compounds as the PDF text has joined.
    left = collections.Counter(a)
    def join(m):
        w = m[0].replace("-", "")
        if left[w.lower()] > 0:
            left[w.lower()] -= 1
            return w
        return m[0]
    b = words(re.sub(r"\w+(?:-\w+)+", join, md))
    return sorted((a - b).elements()), sorted((b - a).elements())


def converted_path(p, text=None):
    """Where a PDF's or Word file's Markdown copy lives, named by its text."""
    text = doc_text(p) if text is None else text
    return RUNS_DIR / "converted" / f"{p.stem}-{fingerprint(text)[1:]}" / f"{p.stem}.md"


def to_markdown(p):
    """Convert a PDF to Markdown with Claude, so it can be reviewed and edited in
    place. The Markdown lives under RUNS_DIR/converted, named by the PDF's
    text, and is reused when the same PDF comes back, keeping your edits.
    Returns its path, or None if the conversion failed."""
    text = doc_text(p)
    md = converted_path(p, text)
    if md.exists():
        keep_original(p, md)
        log(f"{p.name}: reviewing its Markdown copy {md}")
        return md
    if is_docx(p):
        return docx_to_markdown(p, md)
    if not CLAUDE:
        log(f"{p.name}: claude not found, so the panel reads the PDF itself")
        return None
    links = pdf_links(p)
    links = ("Its links (link text -> URL). Use these URLs exactly:\n"
             + "\n".join(f"{t} -> {u}" for t, u in links)) if links else ""
    log(f"{p.name}: converting to Markdown")
    try:
        r = subprocess.run([CLAUDE, "-p", TO_MD.format(path=p, links=links), "--tools", "Read",
                            "--allowedTools", "Read", "--model", "sonnet"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, env=CHILD_ENV, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        r = SimpleNamespace(returncode=1, stdout="", stderr=str(e))
    out = re.sub(r"\A\s*```(?:markdown|md)?\n(.*)\n```\s*\Z", r"\1", r.stdout, flags=re.S).strip()
    if r.returncode != 0 or not out:
        log(f"{p.name}: conversion failed ({(r.stderr.strip().splitlines() or ['no output'])[0][:120]}), "
            "so the panel reads the PDF itself")
        return None
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(out + "\n")
    keep_original(p, md)
    missing, added = conversion_gaps(p, out)
    report = (f"Words of {p.name} missing from {md.name} ({len(missing)}):\n{' '.join(missing)}\n\n"
              f"Words {md.name} added ({len(added)}):\n{' '.join(added)}\n")
    (md.parent / "conversion-check.txt").write_text(report)
    log(f"{p.name}: Markdown copy at {md}")
    if missing or added:
        show = lambda ws: " ".join(ws[:15]) + (" ..." if len(ws) > 15 else "")
        log(f"  check: {len(missing)} words missing ({show(missing)}), {len(added)} added ({show(added)}). "
            f"Full list: {md.parent / 'conversion-check.txt'}")
    else:
        log("  check: every word of the PDF is in the Markdown, and nothing was added")
    return md


# Word files convert to GitHub Markdown with $...$ math, which reads back the same.
DOCX_MD = "gfm-tex_math_gfm+tex_math_dollars"


def docx_to_markdown(p, md):
    """Convert a Word file to Markdown with pandoc: tracked changes accepted,
    images saved in media/ beside the copy. Returns the copy's path."""
    md.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["pandoc", str(p), "-t", DOCX_MD, "--wrap=none", "--track-changes=accept",
                        "--extract-media=.", "-o", md.name], cwd=md.parent, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: could not convert {p.name} to Markdown: {r.stderr.strip()[:200]}")
    keep_original(p, md)
    log(f"{p.name}: Markdown copy at {md}")
    return md


def keep_original(p, md):
    """Keep the converted file beside its Markdown copy, so the edited draft can
    be downloaded in its format (a Word file also lends its styles)."""
    if not md.with_suffix(p.suffix.lower()).exists():
        shutil.copyfile(p, md.with_suffix(p.suffix.lower()))


def original_of(path):
    """The PDF or Word file a Markdown copy was converted from, or None."""
    path = Path(path)
    if (RUNS_DIR / "converted").resolve() not in path.resolve().parents:
        return None
    return next((path.with_suffix(e) for e in (".docx", ".pdf") if path.with_suffix(e).exists()), None)


MD_MIME = "text/markdown; charset=utf-8"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def to_docx(md, reader, folder):
    """A Word file of Markdown text, through pandoc. Images resolve from `folder`."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.docx"
        r = subprocess.run(["pandoc", "-f", reader, "-o", str(out), "--resource-path", str(folder)],
                           input=md, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"could not make the Word file: {(r.stderr.strip().splitlines() or ['no output'])[-1][:200]}")
        return out.read_bytes()


def export_draft(path, fmt=None, notes=()):
    """(file name, MIME type, bytes, edits not placed) of the draft as it is now,
    as Markdown, Word, or (for a draft that came as a PDF) PDF. The default is the
    format it came in. A draft that came as a Word file comes back as the original
    with the edits as tracked changes. Any other Word file is made by pandoc. In a
    Word file, each note {"quote", "text"} is a comment on its passage, and so is
    each edit the tracked changes could not place."""
    path, orig = Path(path), original_of(path)
    fmt = fmt or (orig.suffix[1:] if orig else "md")
    name = f"{path.stem}-edited.{fmt}"
    if fmt == "md":
        return name, MD_MIME, path.read_bytes(), []
    if fmt == "docx":
        missed = []
        if orig is not None and orig.suffix == ".docx":
            data, missed = patch_docx(orig, path.read_text())
        else:
            data = to_docx(path.read_text(), "markdown", path.parent)
        text = path.read_text()
        blanks = [{"quote": line[max(0, k - 60):m.end()],  # the words before the blank, and the blank
                   "text": f"Fill this in: {m[0]} is a placeholder from an accepted finding, and it is in the text as written."}
                  for line in text.splitlines() for m in re.finditer(r"\{\{[^{}]*\}\}", line) for k in [m.start()]]
        with zipfile.ZipFile(io.BytesIO(data)) as z:  # a blank whose edit was not placed is not in the file
            body = ET.fromstring(z.read("word/document.xml")).find(w_("body"))
        words = "\n".join("".join(x["text"] for x in para_atoms(q)) for q in body.iter(w_("p")))  # as Word shows it
        blanks = [x for x in blanks if x["text"].split(" is a placeholder")[0][len("Fill this in: "):] in words]
        unplaced = blanks + [{"quote": m.get("anchor") or m["old"] or m["new"], "text": "This edit is in the reviewed draft but could not be "
                     f"placed here as a tracked change ({m['why']}). Make it by hand.\nWas: {m['old'] or '(nothing)'}"
                     f"\nNow: {m['new'] or '(removed)'}"} for m in missed]
        return name, DOCX_MIME, add_comments(data, list(notes) + unplaced), missed
    if fmt == "pdf" and orig is not None and orig.suffix == ".pdf":
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / name
            r = subprocess.run([str(Path(__file__).resolve().parent / "make-pdf"), path.name, "-o", str(out)],
                               cwd=path.parent, capture_output=True, text=True)
            if r.returncode != 0 or not out.exists():
                raise RuntimeError(f"could not make the PDF: {(r.stderr.strip().splitlines() or ['no output'])[-1][:200]}")
            return name, "application/pdf", out.read_bytes(), []
    raise ValueError(f"the draft cannot be downloaded as .{fmt}")


# Patching a Word file in place. The Markdown copy is compared with a fresh
# conversion of the original, line by line (a table cell counts as a line), and
# each changed line is written into its paragraph in the original as tracked
# changes. Nothing else in the file is touched: comments, citation fields,
# styles, and layout stay as they were. Text inside equations, fields, and
# footnote marks is not edited, and footnotes, tables' shape, and new
# formatting are not carried over. Those edits are returned, to make by hand.
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
OBJECT = "\ufffc"  # one character for an equation, image, or footnote mark
OBJECT_MD = re.compile(r"\$\$.+?\$\$|(?<![\\$])\$(?!\$).+?(?<!\\)\$|!\[[^\]]*\]\([^)]*\)|\[\^[^\]]+\]")
w_ = lambda tag: f"{{{W}}}{tag}"


def md_units(md):
    """[(kind, Markdown)] for each line of the draft that is one paragraph in
    Word: a paragraph, heading, list item, or table cell."""
    units = []
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = []
        for line in block.splitlines():
            starts = re.match(r"\s*([-*+]|\d+[.)])\s|\s*#|\s*>|\s*\||\s*\[\^[^\]]+\]:|\s*\$\$", line)
            if lines and not starts and not lines[-1].lstrip().startswith("|"):
                lines[-1] += " " + line.strip()  # a paragraph wrapped over lines
            else:
                lines.append(line)
        for line in lines:
            t = line.strip()
            if re.fullmatch(r"\|?[\s:|-]+\|?", t) and "-" in t:
                continue  # a table's header rule
            if t.startswith("|"):
                cells = re.split(r"(?<!\\)\|", t.strip("|"))
                units += [("cell", c.strip()) for c in cells]
            elif re.match(r"\[\^[^\]]+\]:", t):
                units.append(("footnote", t))
            elif re.match(r"<(table|div|figure|img|!--)\b", t, re.I):  # block HTML; <u> and <sup> are text
                units.append(("html", t))
            else:
                units.append(("text", t))
    return units


def md_plain(units):
    """Each unit's text as Word shows it: markup removed, and each equation,
    image, and footnote mark one OBJECT character."""
    def prep(t):
        t = re.sub(r"^\s*(#+|>|[-*+]|\d+[.)])\s+", "", t)
        t = OBJECT_MD.sub(OBJECT, t)
        return t
    if not units:
        return []
    sep = "XQXSEPXQX"
    src = f"\n\n{sep}\n\n".join(prep(t) or "​" for t in units)
    r = subprocess.run(["pandoc", "-f", DOCX_MD, "-t", "plain", "--wrap=none"], input=src,
                       capture_output=True, text=True, check=True)
    out = [p.strip().replace("​", "") for p in re.split(rf"\n*^{sep}$\n*", r.stdout, flags=re.M)]
    if len(out) != len(units):
        raise RuntimeError("could not read the Markdown's text")
    return out


def para_atoms(p):
    """The paragraph's text in pieces: [{text, el, run, locked}], where el is the
    w:t (or other) element and run its w:r. Locked pieces (equations, fields,
    footnote marks, images) are never edited."""
    atoms, field = [], [0]

    def walk(el, locked):
        for c in el:
            tag = c.tag
            if tag == w_("r"):
                for k in c:
                    if k.tag == w_("fldChar"):
                        kind = k.get(w_("fldCharType"))
                        field[0] += {"begin": 1, "end": -1}.get(kind, 0)
                    elif k.tag == w_("t"):
                        atoms.append({"text": k.text or "", "el": k, "run": c, "locked": locked or field[0] > 0})
                    elif k.tag in (w_("tab"), w_("br"), w_("cr")):
                        atoms.append({"text": " ", "el": k, "run": c, "locked": True})
                    elif k.tag == w_("noBreakHyphen"):
                        atoms.append({"text": "-", "el": k, "run": c, "locked": True})
                    elif k.tag in (w_("drawing"), w_("pict"), w_("object"), w_("sym"),
                                   w_("footnoteReference"), w_("endnoteReference")):
                        atoms.append({"text": OBJECT, "el": k, "run": c, "locked": True})
            elif tag in (f"{{{M}}}oMath", f"{{{M}}}oMathPara"):
                atoms.append({"text": OBJECT, "el": c, "run": None, "locked": True})
            elif tag == w_("fldSimple"):
                walk(c, True)
            elif tag in (w_("hyperlink"), w_("ins"), w_("smartTag"), w_("sdt"), w_("sdtContent"), w_("customXml")):
                walk(c, locked)
            # w:del (text already deleted), w:pPr, bookmarks, and comment marks hold no text
    walk(p, False)
    at = 0
    for a in atoms:
        a["start"], a["end"] = at, at + len(a["text"])
        at = a["end"]
    return atoms


def wnorm(t):
    return re.sub(r"\s+", " ", t.translate(QUOTES).replace(" ", " ")).strip()


def tokens(t):
    """Words, numbers, spaces, and marks. Letters and digits split, since a
    citation number set after a word ("pneumonitis55") is often a field."""
    return re.findall(r"\s+|[^\W\d]+|\d+|[^\w\s]", t)


class Tracker:
    """Writes tracked insertions and deletions into one document.xml tree."""

    def __init__(self, root):
        self.root = root
        ids = [int(v) for e in root.iter() for k, v in e.attrib.items() if k == w_("id") and v.lstrip("-").isdigit()]
        self.next_id = max(ids, default=0) + 1
        self.date = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.parents = {}

    def mark(self, tag):
        self.next_id += 1
        return ET.Element(w_(tag), {w_("id"): str(self.next_id), w_("author"): "Unified review", w_("date"): self.date})

    def parent(self, el):
        if el not in self.parents:
            self.parents = {c: p for p in self.root.iter() for c in p}
        return self.parents[el]

    def split_run(self, run, at):
        """Move the run's children from index `at` on into a new run after it."""
        new = ET.Element(run.tag, dict(run.attrib))
        rpr = run.find(w_("rPr"))
        if rpr is not None:
            new.append(copy.deepcopy(rpr))
        for k in list(run)[at:]:
            run.remove(k)
            new.append(k)
        par = self.parent(run)
        par.insert(list(par).index(run) + 1, new)
        self.parents = {}

    def split_at(self, p, off):
        """Make `off` fall between runs."""
        for a in para_atoms(p):
            if a["start"] < off < a["end"]:  # inside a w:t: cut it in two
                t, k = a["el"], off - a["start"]
                t2 = ET.Element(w_("t"), {XML_SPACE: "preserve"})
                t2.text, t.text = t.text[k:], t.text[:k]
                t.set(XML_SPACE, "preserve")
                kids = list(a["run"])
                a["run"].insert(kids.index(t) + 1, t2)
                break
        for a in para_atoms(p):
            if a["start"] == off and a["run"] is not None:
                kids = list(a["run"])
                i = kids.index(a["el"])
                if any(k.tag != w_("rPr") for k in kids[:i]):
                    self.split_run(a["run"], i)
                return

    def text_run(self, ref, text, own=False):
        """A run of text formatted like `ref`. Unless it replaces ref's own text
        (own), it is not super- or subscript: words added after a citation number
        are not part of the citation."""
        r = ET.Element(w_("r"))
        rpr = ref.find(w_("rPr")) if ref is not None else None
        if rpr is not None:
            rpr = copy.deepcopy(rpr)
            for va in [] if own else rpr.findall(w_("vertAlign")):
                rpr.remove(va)
            r.append(rpr)
        t = ET.SubElement(r, w_("t"), {XML_SPACE: "preserve"})
        t.text = text
        return r

    def replace(self, p, s, e, new):
        """Replace the paragraph's text [s, e) with `new`, as tracked changes."""
        if e > s:
            self.split_at(p, e)
            self.split_at(p, s)
        else:
            self.split_at(p, s)
        atoms = para_atoms(p)
        runs = []
        for a in atoms:
            if s <= a["start"] and a["end"] <= e and a["end"] > a["start"] and a["run"] not in runs:
                runs.append(a["run"])
        before = [a for a in atoms if a["end"] <= s and a["run"] is not None]
        after = [a for a in atoms if a["start"] >= max(s, e) and a["run"] is not None]
        ref = runs[0] if runs else (before[-1]["run"] if before else after[0]["run"] if after else None)
        last = None
        for run in runs:
            for k in run:
                if k.tag == w_("t"):
                    k.tag = w_("delText")
            par = self.parent(run)
            d = self.mark("del")
            par.insert(list(par).index(run), d)
            par.remove(run)
            d.append(run)
            self.parents = {}
            last = d
        if not new:
            return
        ins = self.mark("ins")
        ins.append(self.text_run(ref, new, own=bool(runs)))
        if last is not None:
            par = self.parent(last)
            par.insert(list(par).index(last) + 1, ins)
        elif before:
            run = before[-1]["run"]
            par = self.parent(run)
            par.insert(list(par).index(run) + 1, ins)
        elif after:
            el = after[0]["run"]
            par = self.parent(el)
            par.insert(list(par).index(el), ins)
        else:
            p.append(ins)
        self.parents = {}

    def mark_paragraph(self, p, tag):
        """Mark the paragraph's own mark as inserted or deleted."""
        ppr = p.find(w_("pPr"))
        if ppr is None:
            ppr = ET.Element(w_("pPr"))
            p.insert(0, ppr)
        rpr = ppr.find(w_("rPr"))
        if rpr is None:
            rpr = ET.Element(w_("rPr"))
            tail = [i for i, k in enumerate(ppr) if k.tag in (w_("sectPr"), w_("pPrChange"))]
            ppr.insert(tail[0] if tail else len(ppr), rpr)
        rpr.insert(0, self.mark(tag))

    def edit(self, p, old, new):
        """Write the change from old to new (both plain text) into paragraph p.
        Returns why it could not, or None, or for a paragraph changed in several
        places, a list of the changes it could not place, as (why, was, now) with
        a few words around each: the others are placed."""
        atoms = para_atoms(p)
        text = "".join(a["text"] for a in atoms)
        if wnorm(text) != wnorm(old):
            return "its paragraph in the Word file reads differently"
        if wnorm(old) == wnorm(new):
            return "it changes an equation, image, footnote mark, or formatting, which stays as it was"
        # Keep the paragraph's own leading and trailing spaces (a footnote starts with one).
        new = text[:len(text) - len(text.lstrip())] + new.strip() + text[len(text.rstrip()):]
        a_tok, b_tok = tokens(text), tokens(new)
        key = lambda ts: [" " if t.isspace() else t.translate(QUOTES) for t in ts]
        offs = [0]
        for t in a_tok:
            offs.append(offs[-1] + len(t))
        codes = difflib.SequenceMatcher(None, key(a_tok), key(b_tok), autojunk=False).get_opcodes()
        # Changes with only spaces between them read as one change ("in this" -> "at low").
        merged = []
        for c in codes:
            if (merged and c[0] != "equal" and len(merged) > 1 and merged[-1][0] == "equal"
                    and merged[-2][0] != "equal" and "".join(a_tok[merged[-1][1]:merged[-1][2]]).isspace()):
                gap, prev = merged.pop(), merged.pop()
                c = ("replace", prev[1], c[2], prev[3], c[4])
            merged.append(c)
        ops = []
        for tag, i1, i2, j1, j2 in merged:
            if tag == "equal":
                continue
            s, e, n = offs[i1], offs[i2], "".join(b_tok[j1:j2])
            locked = lambda k: any(a["locked"] and a["start"] <= k < a["end"] for a in atoms)
            while e > s and n and text[e - 1] == n[-1] and locked(e - 1):  # leave unchanged locked text out
                e, n = e - 1, n[:-1]
            while e > s and n and text[s] == n[0] and locked(s):
                s, n = s + 1, n[1:]
            ops.append((s, e, n))
        hits = lambda s, e: any(a["locked"] and (a["start"] < e and a["end"] > s if e > s else a["start"] < s < a["end"])
                                for a in atoms)
        bad = [(s, e, n) for s, e, n in ops if hits(s, e)]
        for s, e, n in reversed([o for o in ops if o not in bad]):
            self.replace(p, s, e, n)
        if not bad:
            return None
        why = "it changes an equation, citation or other field, footnote mark, or image"
        if len(bad) == len(ops):
            return why
        around = lambda s, e, n: (text[max(0, s - 40):s] + "[" + n + "]" + text[e:e + 40]).strip()
        return [(why, (text[max(0, s - 40):s] + "[" + text[s:e] + "]" + text[e:e + 40]).strip(), around(s, e, n))
                for s, e, n in bad]

    def delete_paragraph(self, p):
        atoms = para_atoms(p)
        if any(a["locked"] and a["text"] != " " for a in atoms):
            return "the paragraph holds an equation, citation or other field, footnote mark, or image"
        if atoms:
            self.replace(p, 0, atoms[-1]["end"], "")
        self.mark_paragraph(p, "del")
        return None

    def insert_paragraph(self, anchor, text, before=False):
        """A new paragraph after (or before) `anchor`, styled like it. Returns it."""
        p = ET.Element(w_("p"))
        ppr = anchor.find(w_("pPr"))
        if ppr is not None:
            ppr = copy.deepcopy(ppr)
            for k in list(ppr):
                if k.tag in (w_("rPr"), w_("sectPr"), w_("pPrChange")):
                    ppr.remove(k)
            p.append(ppr)
        self.mark_paragraph(p, "ins")
        ref = next((a["run"] for a in para_atoms(anchor) if a["run"] is not None and not a["locked"]), None)
        ins = self.mark("ins")
        ins.append(self.text_run(ref, text))
        p.append(ins)
        par = self.parent(anchor)
        par.insert(list(par).index(anchor) + (0 if before else 1), p)
        self.parents = {}
        return p


def align(a, b):
    """[(i, j)] pairing the original's units with the edited draft's, in order:
    (i, None) for a unit deleted, (None, j) for a unit added. Within a changed
    stretch, units pair when they are of one kind and alike."""
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [u[1] for u in a], [u[1] for u in b],
                                                        autojunk=False).get_opcodes():
        if tag == "equal" or (i2 - i1 == j2 - j1 and all(a[i][0] == b[j][0] for i, j in
                                                         zip(range(i1, i2), range(j1, j2)))):
            out += zip(range(i1, i2), range(j1, j2))  # lines edited in place
            continue
        j = j1
        for i in range(i1, i2):
            k = next((k for k in range(j, j2) if a[i][0] == b[k][0] and
                      difflib.SequenceMatcher(None, a[i][1], b[k][1]).ratio() >= 0.4), None)
            if k is None:
                out.append((i, None))
                continue
            out += [(None, n) for n in range(j, k)] + [(i, k)]
            j = k + 1
        out += [(None, n) for n in range(j, j2)]
    return out


def patch_docx(orig, md):
    """(bytes of the Word file `orig` with the Markdown `md`'s changes written in
    as tracked changes, [edits not placed, as {"old", "new", "why"}])."""
    with tempfile.TemporaryDirectory() as tmp:
        # The same command as docx_to_markdown, so image paths match.
        r = subprocess.run(["pandoc", str(Path(orig).resolve()), "-t", DOCX_MD, "--wrap=none", "--track-changes=accept",
                            "--extract-media=."], cwd=tmp, capture_output=True, text=True, check=True)
    a, b = md_units(r.stdout), md_units(md)
    pairs = align(a, b)
    if all(i is not None and j is not None and a[i][1] == b[j][1] for i, j in pairs):
        return Path(orig).read_bytes(), []
    footnote = lambda t: re.sub(r"^\[\^[^\]]+\]:\s*", "", t)
    plain_a = md_plain([footnote(t) for _, t in a])
    plain_b = md_plain([footnote(t) for _, t in b])
    parts, roots = {}, {}
    with zipfile.ZipFile(orig) as z:
        for name in ("word/document.xml", "word/footnotes.xml"):
            if name in z.namelist():
                parts[name] = z.read(name).decode("utf-8")
    for xml in parts.values():
        for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', xml):
            ET.register_namespace(prefix, uri)
    roots = {n: ET.fromstring(x) for n, x in parts.items()}
    trackers = {n: Tracker(r) for n, r in roots.items()}
    start = max(t.next_id for t in trackers.values())
    for t in trackers.values():  # revision ids unique across both parts
        t.next_id = start
    body = trackers["word/document.xml"]
    notes = trackers.get("word/footnotes.xml")

    class Paras:
        """A part's paragraphs, found by their text, searching forward first."""
        def __init__(self, root):
            self.paras = list(root.iter(w_("p")))
            self.at = collections.defaultdict(list)
            for k, p in enumerate(self.paras):
                self.at[wnorm("".join(x["text"] for x in para_atoms(p)))].append(k)
            self.last = -1

        def find(self, text):
            hits = self.at.get(wnorm(text), [])
            k = next((k for k in hits if k > self.last), hits[0] if hits else None)
            if k is None:
                return None
            self.last = k
            return self.paras[k]

    body_paras = Paras(body.root)
    note_paras = Paras(notes.root) if notes else None
    missed = []
    miss = lambda old, new, why, anchor=None: missed.append({"old": old, "new": new, "why": why, **({"anchor": anchor} if anchor else {})})

    def where(i):
        """(tracker, paragraph) of the original's unit i, or (None, None)."""
        if a[i][0] == "footnote":
            return (notes, note_paras.find(plain_a[i])) if notes else (None, None)
        if a[i][0] == "html":
            return None, None
        return body, body_paras.find(plain_a[i])

    prev, waiting = None, []  # the last paragraph placed, and new units with none before them yet
    for i, j in pairs:
        if i is None:
            if b[j][0] != "text":
                miss("", b[j][1], "new table cells and footnotes are not added to the Word file")
            elif prev is None:
                waiting.append(j)
            else:
                prev = body.insert_paragraph(prev, plain_b[j])
            continue
        tr, p = where(i)
        if j is not None and a[i][1] == b[j][1]:
            pass
        elif p is None:
            miss(a[i][1], b[j][1] if j is not None else "",
                 "HTML tables are not edited in the Word file" if a[i][0] == "html"
                 else "its paragraph was not found in the Word file")
        elif j is None:
            why = tr.delete_paragraph(p) if a[i][0] == "text" else "table cells and footnotes are not removed"
            if why:
                miss(a[i][1], "", why)
        else:
            why = tr.edit(p, plain_a[i], plain_b[j])
            if isinstance(why, list):  # the rest of the paragraph's changes are placed
                here = "".join(x["text"] for x in para_atoms(p))[:80]  # the paragraph as Word now reads it
                for w, was, now in why:
                    miss(was, now, w, here)
            elif why:
                miss(a[i][1], b[j][1], why)
            elif OBJECT_MD.findall(footnote(a[i][1])) != OBJECT_MD.findall(footnote(b[j][1])):
                miss(a[i][1], b[j][1], "its text changed in the Word file, but not its equation, image, or footnote mark")
        if p is not None and tr is body:
            if waiting:  # new units at the very start go before the first paragraph found
                for n in waiting:
                    body.insert_paragraph(p, plain_b[n], before=True)
                waiting = []
            prev = p
    for n in waiting:
        miss("", b[n][1], "there was no paragraph to place it by")

    out = io.BytesIO()
    with zipfile.ZipFile(orig) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in roots:
                data = xml_bytes(roots[item.filename], parts[item.filename])
            zout.writestr(item, data)
    return out.getvalue(), missed


def xml_bytes(root, original):
    """A Word part's XML tree as bytes. ElementTree drops namespace declarations
    it does not use, but Word needs the ones mc:Ignorable names, so the original
    root tag is kept, with any declarations ElementTree moved up to the root."""
    for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', original):
        ET.register_namespace(prefix, uri)
    new = ET.tostring(root, encoding="unicode")
    head, keep = re.match(r"<[^>]+>", new)[0], re.search(r"<(?!\?)[^>]+>", original)[0]
    keep = re.sub(r"\s*/>$", ">", keep)  # an empty part's root closes itself
    if head.endswith("/>"):  # and so may the tree's, when it is still empty
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + original.split("?>", 1)[-1].lstrip()).encode("utf-8")
    more = "".join(f" {d}" for d in re.findall(r'xmlns:\w+="[^"]*"', head) if d not in keep)
    new = keep[:-1] + more + ">" + new[len(head):]
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + new).encode("utf-8")


COMMENTS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"


def add_comments(data, notes):
    """A Word file's bytes with each note {"quote", "text"} added as a comment by
    "Unified review" on the paragraph holding its quote, or on the first
    paragraph, saying so, when the quote is not found."""
    if not notes:
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {i.filename: z.read(i.filename) for i in z.infolist()}
        infos = z.infolist()
    doc_xml = files["word/document.xml"].decode("utf-8")
    for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', doc_xml):
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(doc_xml)
    paras = list(root.find(w_("body")).iter(w_("p")))
    texts = [wnorm("".join(a["text"] for a in para_atoms(p))) for p in paras]
    old = files.get("word/comments.xml", b"").decode("utf-8")
    croot = ET.fromstring(old) if old else ET.Element(w_("comments"))
    ids = [int(c.get(w_("id"))) for c in croot if (c.get(w_("id")) or "").isdigit()]
    ids += [int(e.get(w_("id"))) for e in root.iter(w_("commentRangeStart")) if (e.get(w_("id")) or "").isdigit()]
    next_id, date = max(ids, default=-1) + 1, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    first = next((p for p, t in zip(paras, texts) if t), paras[0])
    for note in notes:
        # The quote as Word shows it: no markup, and only up to an equation or footnote mark.
        quote = re.sub(r"^[^<>]*>", "", note.get("quote") or "")  # a quote cut in the middle of a tag drops its tail
        q = wnorm(re.split(r"\$|\[\^", plain_view(quote)[0])[0])[:60]
        para = next((p for p, t in zip(paras, texts) if len(q) >= 12 and q in t), None)
        text = note["text"] if para is not None else "(Its passage was not found.) " + note["text"]
        para = para if para is not None else first
        cid = str(next_id)
        next_id += 1
        c = ET.SubElement(croot, w_("comment"), {w_("id"): cid, w_("author"): "Unified review",
                                                 w_("date"): date, w_("initials"): "UR"})
        for k, line in enumerate(text.split("\n")):
            cp = ET.SubElement(c, w_("p"))
            if k == 0:
                ET.SubElement(ET.SubElement(cp, w_("r")), w_("annotationRef"))
            t = ET.SubElement(ET.SubElement(cp, w_("r")), w_("t"), {XML_SPACE: "preserve"})
            t.text = line
        ppr = para.find(w_("pPr"))
        para.insert(1 if ppr is not None else 0, ET.Element(w_("commentRangeStart"), {w_("id"): cid}))
        para.append(ET.Element(w_("commentRangeEnd"), {w_("id"): cid}))
        ref = ET.SubElement(para, w_("r"))
        ET.SubElement(ET.SubElement(ref, w_("rPr")), w_("rStyle"), {w_("val"): "CommentReference"})
        ET.SubElement(ref, w_("commentReference"), {w_("id"): cid})
    files["word/document.xml"] = xml_bytes(root, doc_xml)
    files["word/comments.xml"] = (xml_bytes(croot, old) if old else
                                  b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                                  + ET.tostring(croot, encoding="utf-8").split(b"?>", 1)[-1].lstrip())
    rels = files["word/_rels/document.xml.rels"].decode("utf-8")
    if COMMENTS_REL not in rels:
        rid = next(f"rIdUR{k}" for k in range(1, 1000) if f'Id="rIdUR{k}"' not in rels)
        rels = rels.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{COMMENTS_REL}" Target="comments.xml"/></Relationships>')
        files["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    types = files["[Content_Types].xml"].decode("utf-8")
    if "/word/comments.xml" not in types:
        types = types.replace("</Types>", f'<Override PartName="/word/comments.xml" ContentType="{COMMENTS_TYPE}"/></Types>')
        files["[Content_Types].xml"] = types.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        names = [i.filename for i in infos]
        for i in infos:
            zout.writestr(i, files[i.filename])
        if "word/comments.xml" not in names:
            zout.writestr("word/comments.xml", files["word/comments.xml"])
    return out.getvalue()


BIB = Path(os.environ.get("BIB_DIR") or Path.home() / "github" / "bib") / "references.bib"
_BIB_KEYS = {}


def bib_file(text, path):
    """The draft's bibliography: a local file named in its front matter, else the
    shared bibliography."""
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    named = re.search(r"^bibliography:\s*(\S+)", m.group(1), re.M) if m else None
    if named and "://" not in named.group(1):
        return (Path(path).parent / named.group(1)).expanduser()
    return BIB


CITATION = re.compile(r"\[([^\[\]]*@[^\[\]]*)\]")
CITE_KEY = re.compile(r"(?<![\w@])-?@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*[\w])")


def cited_keys(text):
    """Citation keys in [@Key] and [@A; @B] citations, in order of first use."""
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    keys = []
    for m in CITATION.finditer(body):
        for k in CITE_KEY.findall(m.group(1)):
            if k not in keys:
                keys.append(k)
    return keys


def bib_field(entry, name):
    """One field of a BibTeX entry, braces and LaTeX quoting removed."""
    m = re.search(r"^\s*" + name + r"\s*=\s*\{(.*)\},?\s*$", entry, re.M | re.I)
    return re.sub(r"[{}]", "", m.group(1)).replace("\\&", "&").replace("--", "–").strip() if m else ""


PLOS_CSL = Path(__file__).resolve().parent.parent / "typeset" / "plos.csl"
_REFS_HTML = {}


def pandoc_refs(entries, keys):
    """{key: html} for the cited entries, formatted by pandoc in the book's PLOS
    style with DOIs linked. Empty when pandoc is not installed or fails."""
    if not shutil.which("pandoc") or not PLOS_CSL.exists():
        return {}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "refs.bib").write_text("\n\n".join(entries))
        md = "\n\n".join(f"[@{k}]" for k in keys)
        r = subprocess.run(["pandoc", "--citeproc", "-t", "html", "--bibliography", str(Path(d) / "refs.bib"),
                            "--csl", str(PLOS_CSL), "-M", "link-bibliography=true"],
                           input=md, capture_output=True, text=True, timeout=60)
    return {m.group(1): m.group(2).strip() for m in re.finditer(
        r'<div id="ref-([^"]+)" class="csl-entry"[^>]*>\s*<div class="csl-left-margin">.*?</div>'
        r'<div\s+class="csl-right-inline">(.*?)</div>\s*</div>', r.stdout, re.S)}


def cited_refs(text, path):
    """The draft's references in order of first citation: [{key, html, text, url}].
    html is the book's PLOS format from pandoc; text and url are a plain
    fallback. An entry not in the bibliography has empty text and html."""
    keys = cited_keys(text)
    try:
        src = bib_file(text, path).read_text(errors="replace") if keys else ""
    except OSError:
        src = ""
    found = {k: m for k in keys if (m := re.search(r"^@\w+\{" + re.escape(k) + r",(.*?)^\}", src, re.M | re.S))}
    cache_key = tuple((k, found[k].group(0) if k in found else "") for k in keys)
    if cache_key not in _REFS_HTML:
        _REFS_HTML[cache_key] = pandoc_refs([m.group(0) for m in found.values()], list(found)) if found else {}
    html = _REFS_HTML[cache_key]
    out = []
    for k in keys:
        m = found.get(k)
        if not m:
            out.append({"key": k, "html": "", "text": "", "url": ""})
            continue
        e = m.group(1)
        names = [a.strip() for a in bib_field(e, "author").split(" and ") if a.strip()]
        def short(a):
            last, _, first = a.partition(",")
            return (last.strip() + " " + "".join(w[0] for w in re.split(r"[\s.-]+", first) if w)).strip()
        who = ", ".join(map(short, names[:3])) + (" et al." if len(names) > 3 else "")
        year = (bib_field(e, "date") or bib_field(e, "year"))[:4]
        venue = bib_field(e, "journaltitle") or bib_field(e, "journal") or bib_field(e, "booktitle") or bib_field(e, "publisher")
        doi = bib_field(e, "doi")
        parts = [p for p in [f"{who} ({year})." if who else (f"({year})." if year else ""),
                             bib_field(e, "title").rstrip(".") + ".", venue + "." if venue else ""] if p and p != "."]
        out.append({"key": k, "html": html.get(k, ""), "text": " ".join(parts),
                    "url": f"https://doi.org/{doi}" if doi else bib_field(e, "url")})
    return out


def bib_keys(text, path):
    """Citation keys in the draft's bibliography. None when it cannot be read."""
    bib = bib_file(text, path)
    try:
        stamp = bib.stat().st_mtime
    except OSError:
        return None
    if _BIB_KEYS.get(bib, (None,))[0] != stamp:
        _BIB_KEYS[bib] = (stamp, set(re.findall(r"^@\w+\{([^,\s]+),", bib.read_text(errors="replace"), re.M)))
    return _BIB_KEYS[bib][1]
