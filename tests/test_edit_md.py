"""Tests for edit-md's server: block splitting, saving, and file serving.
They run offline. The render test needs pandoc and is skipped without it."""
import importlib.util
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "typeset" / "editor" / "server.py"
spec = importlib.util.spec_from_file_location("edit_md_server", SCRIPT)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

DOC = """---
bibliography: refs.bib
---

# Title: a subtitle

Author Name

## 1. Introduction

First sentence [@Alpha20].
Second sentence with $x^2$ and `code`.

1. **One.** Item one.
2. **Two.** Item two.

3. **Three.** A loose item after a blank line.
   An indented continuation line.

<!-- a note the PDF hides -->

<a id="table-1"></a>
*Table 1: A caption.*

| a | b |
|---|---|
| 1 | 2 |

<div style="page-break-after: always;"></div>

Last paragraph [@Beta21; @Alpha20].
"""

BIB = """@article{Alpha20,
  author = {Alpha, A.},
  title = {First},
  journal = {J},
  year = {2020}
}

@article{Beta21,
  author = {Beta, B.},
  title = {Second},
  journal = {J},
  year = {2021}
}
"""


def reassemble(text):
    front, body = server.split_front(text)
    lead, chunks = server.chunk(body)
    return front + lead + "".join(src + sep for src, sep in chunks), chunks


class ChunkTests(unittest.TestCase):
    def test_reassembles_exactly(self):
        for text in (DOC, "\n\n\nLeading blank lines.\n\nTwo\n", "No trailing newline", "", "\n\n"):
            self.assertEqual(reassemble(text)[0], text)

    def test_block_kinds(self):
        _, chunks = reassemble(DOC)
        kinds = [server.kind(src) for src, _ in chunks]
        self.assertEqual(kinds, ["heading", "para", "heading", "para", "list", "comment",
                                 "para", "table", "pagebreak", "para"])

    def test_loose_list_and_continuation_stay_one_block(self):
        _, chunks = reassemble(DOC)
        lists = [src for src, _ in chunks if server.kind(src) == "list"]
        self.assertEqual(len(lists), 1)
        self.assertIn("3. **Three.**", lists[0])
        self.assertIn("An indented continuation line.", lists[0])

    def test_bullet_and_numbered_lists_stay_apart(self):
        _, chunks = server.chunk("* a\n\n1. b\n")
        self.assertEqual([src.strip() for src, _ in chunks], ["* a", "1. b"])

    def test_find_bib(self):
        d = Path("/doc")
        self.assertEqual(server.find_bib("---\nbibliography: refs.bib\n---\n", d), d / "refs.bib")
        self.assertEqual(server.find_bib("---\nbibliography: https://x.org/a.bib\n---\n", d), "https://x.org/a.bib")
        self.assertIsNone(server.find_bib("", d))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.md = self.dir / "doc.md"
        self.md.write_text(DOC, encoding="utf-8")
        (self.dir / "refs.bib").write_text(BIB, encoding="utf-8")
        (self.dir / "fig.svg").write_text("<svg/>", encoding="utf-8")
        (self.dir / ".secret").write_text("x", encoding="utf-8")
        server.Handler.src = self.md
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.dir)

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read()

    def post(self, path, data):
        req = urllib.request.Request(self.base + path, json.dumps(data).encode(), method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_source_reports_mtime_as_string(self):
        _, body = self.get("/api/source")
        src = json.loads(body)
        self.assertEqual(src["text"], DOC)
        self.assertIsInstance(src["mtime"], str)
        self.assertEqual(src["layout"], server.LAYOUTS["default"])

    def test_save_refuses_a_stale_page(self):
        mtime = json.loads(self.get("/api/source")[1])["mtime"]
        code, _ = self.post("/api/save", {"text": "stale", "mtime": "1"})
        self.assertEqual(code, 409)
        self.assertEqual(self.md.read_text(encoding="utf-8"), DOC)
        code, body = self.post("/api/save", {"text": "fresh", "mtime": mtime})
        self.assertEqual(code, 200)
        self.assertEqual(self.md.read_text(encoding="utf-8"), "fresh")
        code, _ = self.post("/api/save", {"text": "forced", "mtime": "1", "force": True})
        self.assertEqual(code, 200)

    def test_serves_document_files_only(self):
        self.assertEqual(self.get("/fig.svg"), (200, b"<svg/>"))
        for path in ("/.secret", "/../../../../../../etc/hosts", "/%2e%2e/%2e%2e/%2e%2e/etc/hosts", "/missing.png"):
            with self.assertRaises(urllib.error.HTTPError, msg=path):
                self.get(path)


class PortTests(unittest.TestCase):
    def test_second_editor_takes_the_next_port(self):
        a = server.bind(18765)
        try:
            b = server.bind(a.server_address[1])
            self.assertNotEqual(a.server_address[1], b.server_address[1])
            b.server_close()
        finally:
            a.server_close()


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
class RenderTests(unittest.TestCase):
    def test_render_numbers_citations_and_splits_references(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "refs.bib").write_text(BIB, encoding="utf-8")
            r = server.render(DOC, d)
            self.assertNotIn("error", r)
            self.assertEqual(r["front"] + r["lead"] + "".join(b["src"] + b["sep"] for b in r["blocks"]), DOC)
            self.assertEqual(len(r["blocks"]), 10)
            self.assertIn('data-cites="Alpha20"', r["blocks"][3]["html"])
            self.assertIn('class="math inline"', r["blocks"][3]["html"])
            self.assertIn("ref-Beta21", r["refs"])
            self.assertNotIn("ref-Beta21", r["blocks"][-1]["html"].split("citation")[0])
            self.assertNotIn('id="refs"', r["blocks"][-1]["html"])
            self.assertTrue(r["refsBreak"])
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
