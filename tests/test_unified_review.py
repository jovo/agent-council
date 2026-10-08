"""Tests for unified-review. Run: python3 -m unittest discover tests"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
ur = SourceFileLoader("unified_review", str(REPO / "bin" / "unified-review")).load_module()

REVIEW = """Some preamble the parser should ignore.

=== FINDING
severity: Critical
title: Date is wrong
quote: Rome was founded in 1066.
---
The founding date is wrong.

~~1066~~ **🟢 753 BC**

=== FINDING
severity: polish (minor)
title: Wordy opener
quote:
---
Cut the throat-clearing.

=== FINDING
severity: Substantive
title: Missing separator, so this one is skipped
"""

VOTES = """A1 | agree | Critical | same:none | Wrong date.
**A2** | Partial | polish | same: none | Minor.
- B1 | disagree | Substantive | same:A1 | Not wrong.
B2 | maybe | Polish | same:none | Not a valid vote word.
"""


def finding(fid, quote="", severity="Substantive", pos=0):
    return {"id": fid, "quote": quote, "severity": severity, "title": fid, "body": fid, "pos": pos}


def vote(v, same="NONE", severity="Substantive"):
    return {"vote": v, "severity": severity, "same": same, "reason": v}


class Parsing(unittest.TestCase):
    def test_parse_findings(self):
        fs = ur.parse_findings(REVIEW)
        self.assertEqual([f["title"] for f in fs], ["Date is wrong", "Wordy opener"])
        self.assertEqual(fs[0]["severity"], "Critical")
        self.assertEqual(fs[1]["severity"], "Polish")
        self.assertEqual(fs[0]["quote"], "Rome was founded in 1066.")
        self.assertEqual(fs[1]["quote"], "")
        self.assertIn("753 BC", fs[0]["body"])

    def test_parse_votes_is_tolerant_but_strict_on_vote_words(self):
        v = ur.parse_votes(VOTES)
        self.assertEqual(set(v), {"A1", "A2", "B1"})
        self.assertEqual(v["A2"]["vote"], "partial")
        self.assertEqual(v["A2"]["severity"], "Polish")
        self.assertEqual(v["B1"]["same"], "A1")

    def test_parse_rows(self):
        rows = ur.parse_rows("K1 | a sentence | a claim | @Key01\nnot a row\n**K2** | s | c | none | extra", 4)
        self.assertEqual(rows["K1"], ["a sentence", "a claim", "@Key01"])
        self.assertEqual(rows["K2"], ["s", "c", "none | extra"])


class GroupingAndScoring(unittest.TestCase):
    def test_two_voters_merge_duplicates(self):
        flat = [finding("A1", "alpha beta"), finding("B1", "gamma delta")]
        votes = {"claude": {"B1": vote("agree", "A1")}, "gpt": {"A1": vote("agree", "B1")}}
        self.assertEqual(len(ur.group_findings(flat, votes)), 1)

    def test_one_voter_merges_only_with_overlapping_quotes(self):
        overlap = [finding("A1", "the cortex stores skills and beliefs"), finding("B1", "cortex stores skills and beliefs")]
        apart = [finding("A1", "alpha beta gamma"), finding("B1", "something else entirely")]
        votes = {"claude": {"B1": vote("agree", "A1")}}
        self.assertEqual(len(ur.group_findings(overlap, votes)), 1)
        self.assertEqual(len(ur.group_findings(apart, votes)), 2)

    def test_score_group_rejects_and_marks_contested(self):
        owner = {"A": "claude", "B": "gpt"}
        voters = ["claude", "gpt", "gemini"]
        rejected = ur.score_group([finding("A1")], {"claude": {"A1": vote("agree")}, "gpt": {"A1": vote("disagree")},
                                                    "gemini": {"A1": vote("disagree")}}, voters, owner)
        self.assertTrue(rejected["rejected"])
        self.assertTrue(rejected["contested"])
        kept = ur.score_group([finding("A1")], {"claude": {"A1": vote("agree")}, "gpt": {"A1": vote("partial")},
                                                "gemini": {"A1": vote("agree")}}, voters, owner)
        self.assertFalse(kept["rejected"])
        self.assertFalse(kept["contested"])
        self.assertEqual(kept["score"], 2.5)

    def test_score_group_takes_median_severity_and_raisers(self):
        owner = {"A": "claude", "B": "gpt"}
        g = ur.score_group([finding("A1"), finding("B1")],
                           {"claude": {"A1": vote("agree", severity="Critical")},
                            "gpt": {"A1": vote("agree", severity="Polish")},
                            "gemini": {"A1": vote("agree", severity="Substantive")}},
                           ["claude", "gpt", "gemini"], owner)
        self.assertEqual(g["severity"], "Substantive")
        self.assertEqual(g["raised_by"], ["claude", "gpt"])



class Agreement(unittest.TestCase):
    def test_alpha_matches_krippendorff_2011_example(self):
        # Krippendorff (2011), "Computing Krippendorff's alpha-reliability": 4 coders,
        # 12 units, values 1-5, missing data. Published ordinal alpha is 0.815.
        coders = [[1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None], [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
                  [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None], [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]]
        units = [[c[u] - 1 for c in coders if c[u] is not None] for u in range(12)]
        self.assertAlmostEqual(ur.krippendorff_alpha_ordinal(units, levels=5), 0.815, places=3)

    def test_alpha_undefined_without_variation_or_pairs(self):
        self.assertIsNone(ur.krippendorff_alpha_ordinal([[2, 2], [2, 2, 2]]))
        self.assertIsNone(ur.krippendorff_alpha_ordinal([[1], [0]]))

    def test_perfect_agreement_is_one(self):
        self.assertAlmostEqual(ur.krippendorff_alpha_ordinal([[0, 0], [2, 2], [1, 1], [2, 2]]), 1.0)

    def test_vote_agreement_leaves_out_self_votes(self):
        flat = [finding("A1"), finding("B1"), finding("A2")]
        owner = {"A": "claude", "B": "gpt"}
        votes = {"claude": {"A1": vote("agree"), "B1": vote("disagree"), "A2": vote("agree")},
                 "gpt": {"A1": vote("disagree"), "B1": vote("agree"), "A2": vote("agree")},
                 "gemini": {"A1": vote("disagree"), "B1": vote("disagree"), "A2": vote("agree")}}
        ag = ur.vote_agreement(flat, votes, owner, boot=50)
        # Without self-votes, every finding has two votes and they match: alpha is 1.
        self.assertEqual(ag["units"], 3)
        self.assertEqual(ag["alpha"], 1.0)


class Calls(unittest.TestCase):
    def setUp(self):
        ur.FAILURES.clear()
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_call(self, results):
        """Fake subprocess.run returning the given (returncode, stdout, stderr) in turn."""
        calls = []

        def fake(cmd, stdin, stdout, stderr, text, env, timeout):
            rc, out, err = results[len(calls)]
            calls.append(cmd)
            stderr.write(err)
            stderr.flush()
            return SimpleNamespace(returncode=rc, stdout=out)
        with mock.patch.object(ur.subprocess, "run", fake):
            text = ur.call("claude", "prompt", self.tmp / "out.md", self.tmp, stage="review")
        return text, len(calls)

    def test_retry_once_then_succeed(self):
        text, n = self.run_call([(1, "", "boom"), (0, "fine", "")])
        self.assertEqual((text, n), ("fine", 2))
        self.assertEqual(ur.FAILURES, [])

    def test_give_up_after_one_retry(self):
        text, n = self.run_call([(0, "", ""), (0, "", "")])
        self.assertEqual((text, n), (None, 2))
        self.assertEqual(ur.FAILURES[0]["reason"], "empty output after one retry")

    def test_no_retry_when_not_logged_in(self):
        text, n = self.run_call([(1, "", "Invalid API key · Please run /login")])
        self.assertEqual((text, n), (None, 1))
        self.assertTrue(ur.FAILURES[0]["reason"].startswith("not logged in"))

    def test_preflight_drops_logged_out_panelists(self):
        def fake(cmd, **kw):
            out = {"auth": '{"loggedIn": true}', "login": "Not logged in", "status": "Logged in as x"}[cmd[1]]
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        with mock.patch.object(ur.subprocess, "run", fake):
            self.assertEqual(ur.preflight(["claude", "gpt", "gemini"]), ["claude", "gemini"])
        self.assertEqual(ur.FAILURES[0]["model"], "gpt")


class Rendering(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.doc = self.tmp / "draft.md"
        self.doc.write_text("# Intro\n\nFirst line.\nRome was founded in 1066.\n\n# Body\n\nMore text here.\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def results(self, groups, reviewers=("claude", "gpt"), voters=("claude", "gpt"), failures=()):
        draft = "===== draft.md =====\n" + self.doc.read_text()
        (self.tmp / "results.json").write_text(json.dumps({
            "files": [str(self.doc)], "labels": {"claude": "Claude", "gpt": "GPT"},
            "reviewers_ok": list(reviewers), "voters": list(voters), "verify": False,
            "failures": list(failures), "headings": ur.draft_headings(draft), "groups": groups}))

    def group(self, title, quote, where, pos, contested=False, rejected=False, severity="Substantive"):
        return {"rep": {"title": title, "quote": quote, "body": "Point."}, "where": where, "pos": pos,
                "severity": severity, "frac": 1, "score": 2, "n_votes": 2, "raised_by": ["claude"],
                "votes": {"claude": vote("agree"), "gpt": vote("disagree" if contested else "agree")},
                "contested": contested, "rejected": rejected}

    def test_layout_severity_then_draft_order(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        at = lambda q: ur.position(dn, q)
        self.results([self.group("Late polish", "More text here.", "draft", at("More text here."), severity="Polish"),
                      self.group("Late substantive", "More text here.", "draft", at("More text here.")),
                      self.group("Overall", "", "overview", 0),
                      self.group("Date", "Rome was founded in 1066.", "draft", at("Rome was founded in 1066."),
                                 contested=True, severity="Critical"),
                      self.group("Early substantive", "First line.", "draft", at("First line."))])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        order = [md.index(t) for t in ("## Critical", "### 1. Date (contested)", "## Substantive", "### 2. Overall",
                                       "### 3. Early substantive", "### 4. Late substantive", "## Polish",
                                       "### 5. Late polish")]
        self.assertEqual(order, sorted(order))
        self.assertIn("*Intro · draft.md, line 4:*", md)  # line 4, not 3: the off-by-one regression
        self.assertIn("*Body · draft.md, line 8:*", md)
        self.assertIn("*Whole draft*", md)
        self.assertNotIn("Warning", md)

    def test_failures_and_warning(self):
        self.results([], reviewers=("claude",), voters=("claude", "gpt"),
                     failures=[{"stage": "review", "model": "gpt", "reason": "timed out after 900 s after one retry"}])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        self.assertIn("*Failed: GPT review (timed out after 900 s after one retry).*", md)
        self.assertIn("**Warning: fewer than two models reviewed.", md)



class Versions(unittest.TestCase):
    def test_numbers_count_up_and_repeat_for_same_text(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(ur, "RUNS_DIR", tmp):
                f = "/x/draft.md"
                self.assertEqual(ur.version_number(f, "va"), 1)
                self.assertEqual(ur.version_number(f, "vb"), 2)
                self.assertEqual(ur.version_number(f, "va"), 1)  # unchanged text keeps its number
                self.assertIsNone(ur.version_number(f, "vc", register=False))
                self.assertEqual(ur.version_number("/x/other.md", "va"), 1)  # numbered per file
        finally:
            shutil.rmtree(tmp)


class Opening(unittest.TestCase):
    def opened(self, bundle, which=True):
        cmds, out = [], []
        env = {"__CFBundleIdentifier": bundle} if bundle else {}
        with mock.patch.dict(ur.os.environ, env, clear=True), \
             mock.patch.object(ur, "OPEN_APP", ""), \
             mock.patch.object(ur.shutil, "which", lambda c: "/bin/" + c if which else None), \
             mock.patch.object(ur.subprocess, "run", lambda cmd, **k: cmds.append(cmd) or SimpleNamespace(returncode=0)), \
             mock.patch("builtins.print", lambda *a, **k: out.append(" ".join(map(str, a)))):
            ur.open_file("/r/unified.md")
        return cmds, out

    def test_cursor_and_vscode_open_in_the_editor(self):
        self.assertEqual(self.opened("com.todesktop.230313mzl4w4u92")[0], [["cursor", "/r/unified.md"]])
        self.assertEqual(self.opened("com.microsoft.VSCode")[0], [["code", "/r/unified.md"]])
        self.assertEqual(self.opened("com.microsoft.VSCode", which=False)[0],
                         [["open", "-b", "com.microsoft.VSCode", "/r/unified.md"]])

    def test_agent_apps_get_a_line_instead(self):
        cmds, out = self.opened("com.anthropic.claudefordesktop")
        self.assertEqual(cmds, [])
        self.assertEqual(out[0], "OPEN IN APP: /r/unified.md")

    def test_terminal_uses_default_app(self):
        self.assertEqual(self.opened("com.apple.Terminal")[0], [["open", "/r/unified.md"]])
        self.assertEqual(self.opened("")[0], [["open", "/r/unified.md"]])


class Decisions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.doc = self.tmp / "draft.md"
        self.doc.write_text("# Intro\n\nRome was founded in 1066.\n")
        self.run = self.tmp / "run"
        self.run.mkdir()
        g = {"rep": {"title": "Date is wrong", "quote": "Rome was founded in 1066.", "body": "Wrong date.\n\n~~1066~~"},
             "where": "draft", "pos": 0, "severity": "Critical", "frac": 1, "rejected": False, "members": ["A1"]}
        (self.run / "results.json").write_text(json.dumps({"files": [str(self.doc)], "headings": [], "groups": [g],
                                                           "versions": [{"path": str(self.doc), "number": 2}]}))
        self.patch = mock.patch.object(ur, "RUNS_DIR", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def test_record_lift_and_expire(self):
        with mock.patch("builtins.print"):
            ur.record_decisions("1", "ignore", "intentional", self.run)
        d = ur.load_decisions()[str(self.doc)][0]
        self.assertEqual((d["id"], d["decision"], d["note"], d["version"]), ("D1", "ignore", "intentional", 2))
        dnorm = ur.norm(self.doc.read_text())
        self.assertEqual([x["id"] for x in ur.active_decisions([self.doc], dnorm)[0]], ["D1"])
        # Rewriting the quoted sentence ends the decline.
        self.assertEqual(ur.active_decisions([self.doc], ur.norm("Rome was founded in 753 BC."))[0], [])
        with mock.patch("builtins.print"):
            ur.record_decisions("D1", "lifted", "", None)
        self.assertEqual(ur.active_decisions([self.doc], dnorm)[0], [])

    def test_prompt_lists_declines_and_applied(self):
        block = ur.decisions_block([{"id": "D1", "title": "Date is wrong", "quote": "Rome", "note": "keep"}], ["Fix typo"])
        self.assertIn("[D1] Date is wrong", block)
        self.assertIn("Author's reason: keep", block)
        self.assertIn("- Fix typo", block)

    def test_votes_can_point_at_declines(self):
        self.assertEqual(ur.parse_votes("A1 | agree | Polish | same:D3 | repeats it")["A1"]["same"], "D3")


class Context(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_text_and_pdf_reach_the_prompts(self):
        (self.tmp / "comments.md").write_text("Reviewer 2: the bandwidth claim lacks a baseline.")
        (self.tmp / "call.pdf").write_bytes(b"%PDF-1.4 fake")
        fake = lambda cmd, **k: SimpleNamespace(returncode=0, stdout="Call text: aims must be testable.")
        with mock.patch.object(ur.subprocess, "run", fake):
            block, text, names = ur.load_context([self.tmp / "comments.md", self.tmp / "call.pdf"])
        self.assertEqual(names, ["comments.md", "call.pdf"])
        self.assertIn("Reviewer 2", text)
        self.assertIn('<supporting_material file="call.pdf">', block)
        prompt = ur.review_prompt("draft text", "", "rules", "", block)
        self.assertIn("not under review", prompt)
        self.assertIn("aims must be testable", prompt)
        vote = ur.VOTE.format(draft="d", findings="f", decided="", focus="", context=ur.CONTEXT_INTRO + block)
        self.assertIn("Reviewer 2", vote)

    def test_long_material_is_trimmed(self):
        (self.tmp / "big.txt").write_text("x" * (ur.MAX_CONTEXT + 50_000))
        with mock.patch("builtins.print"):
            block, text, _ = ur.load_context([self.tmp / "big.txt"])
        self.assertLess(len(text), ur.MAX_CONTEXT + 100)
        self.assertIn("truncated", text)

    def test_binary_files_are_refused(self):
        (self.tmp / "photo.png").write_bytes(bytes(range(256)) * 4)
        with self.assertRaises(SystemExit):
            ur.load_context([self.tmp / "photo.png"])

class FactcheckCarryOver(unittest.TestCase):
    """A rerun keeps confirmed verdicts for unchanged claims and rechecks the rest."""

    def run_fc(self, runs, name, draft_text, prompts):
        run = runs / name
        run.mkdir()
        f = runs / "memo.md"
        f.write_text(draft_text)
        (run / "results.json").write_text(json.dumps({"files": [str(f)]}))
        draft = f"===== memo.md =====\n{draft_text}"

        def fake_call(m, prompt, out, workdir, web=False, stage=""):
            if stage == "claims":
                s1, s2 = [x.strip() + "." for x in draft_text.split(".")[:2]]
                return f"K1 | {s1} | sky is blue | none\nK2 | {s2} | boiling point | none"
            prompts.append(prompt)
            return "\n".join(f"{k} | confirmed | https://x.org | ok" for k in ("K1", "K2") if k + " |" in prompt)
        with mock.patch.object(ur, "call", fake_call), \
             mock.patch.object(ur, "open_file", lambda p: None), \
             mock.patch.object(ur.subprocess, "run", lambda *a, **k: None):
            ur.background([f], draft, ["claude"], run, runs)
        return json.loads((run / "factcheck.json").read_text()), (run / "factcheck.md").read_text()

    def test_unchanged_confirmed_claim_is_carried_over(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d)):
            runs, first, second = Path(d), [], []
            self.run_fc(runs, "memo-v1", "The sky is blue. Water boils at 90 C.", first)
            fc, md = self.run_fc(runs, "memo-v2", "The sky is blue. Water boils at 90 C.", second)
            self.assertEqual(len(second), 0)  # nothing left to check
            self.assertTrue(all(c["carried"] == "memo-v1" for c in fc["claims"]))
            self.assertIn("Carried over from memo-v1", md)

    def test_changed_claim_is_rechecked(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d)):
            runs, first, second = Path(d), [], []
            self.run_fc(runs, "memo-v1", "The sky is blue. Water boils at 80 C.", first)
            fc, _ = self.run_fc(runs, "memo-v2", "The sky is blue. Water boils at 90 C.", second)
            self.assertEqual(len(second), 1)
            self.assertIn("K2 |", second[0])
            self.assertNotIn("K1 |", second[0])
            carried = {c["k"]: c.get("carried") for c in fc["claims"]}
            self.assertEqual(carried, {"K1": "memo-v1", "K2": None})


@unittest.skipUnless(shutil.which("gs") and shutil.which("pdffonts"), "needs Ghostscript and poppler")
class PdfExtras(unittest.TestCase):
    """A PDF goes to the panel as text unless the text would miss something."""

    def pdf(self, d, name, ps):
        out = Path(d) / name
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
                        f"-sOutputFile={out}", "-c", ps], check=True, capture_output=True)
        return out

    def test_text_only_and_graphics(self):
        with tempfile.TemporaryDirectory() as d:
            text = self.pdf(d, "text.pdf", "/Times-Roman findfont 12 scalefont setfont 72 700 moveto (Plain prose.) show showpage")
            box = self.pdf(d, "box.pdf", "100 300 300 200 rectfill showpage")
            self.assertEqual(ur.pdf_extras(text), [])
            self.assertIn("graphics", ur.pdf_extras(box))


class Pipeline(unittest.TestCase):
    """A whole review with fake model calls."""

    def run_review(self, panel, fails=(), draft_text="The sky is green today. Grass grows slowly."):
        prompts = {}

        def fake_call(m, prompt, out, workdir, web=False, stage=""):
            prompts.setdefault(stage, {})[m] = prompt
            if m in fails or (stage, m) in fails:
                ur.fail(stage, m, "fake failure")
                return None
            if stage == "review":
                return (f"=== FINDING\nseverity: Substantive\ntitle: Sky color by {m}\n"
                        "quote: The sky is green today.\n---\nThe sky is blue.")
            ids = re.findall(r"^\[([A-H]\d+)\]", prompt, re.M)
            return "\n".join(f"{i} | agree | Substantive | same:none | fine" for i in ids)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            f = d / "memo.md"
            f.write_text(draft_text)
            out = d / "run"
            out.mkdir()
            draft = f"===== memo.md =====\n{draft_text}"
            ur.FAILURES.clear()
            with mock.patch.object(ur, "call", fake_call), mock.patch.object(ur, "RUNS_DIR", d), \
                 mock.patch.object(ur, "LAST_RUN", d / "last-run"), \
                 mock.patch.object(ur, "open_file", lambda p: None), mock.patch.object(ur, "log", lambda *a: None):
                ur.foreground([f], draft, panel, "", "rules", out, d, False, [])
            return prompts, json.loads((out / "results.json").read_text()), (out / "unified.md").read_text()

    def test_voters_see_the_draft(self):
        prompts, _, _ = self.run_review(["claude", "gpt", "gemini"])
        for m, p in prompts["vote"].items():
            self.assertIn("Grass grows slowly.", p.split("<draft>")[1], m)  # not in any quote

    def test_grok_stands_in_for_a_failed_reviewer(self):
        _, r, md = self.run_review(["claude", "gpt", "gemini"], fails=("claude",))
        self.assertEqual(sorted(r["reviewers_ok"]), ["gemini", "gpt", "grok"])
        self.assertEqual(sorted(r["voters"]), ["gemini", "gpt", "grok"])
        self.assertIn("Failed: Claude", md)

    def test_grok_stands_in_for_a_failed_voter(self):
        _, r, _ = self.run_review(["claude", "gpt", "gemini"], fails=(("vote", "gpt"),))
        self.assertEqual(sorted(r["reviewers_ok"]), ["claude", "gemini", "gpt"])
        self.assertEqual(sorted(r["voters"]), ["claude", "gemini", "grok"])

    def test_no_stand_in_when_all_succeed(self):
        prompts, r, _ = self.run_review(["claude", "gpt", "gemini"])
        self.assertNotIn("grok", r["panel"])
        self.assertNotIn("grok", prompts["review"])


class Iterating(unittest.TestCase):
    def test_changes_format(self):
        old = "# T\n\n## A\n\nField teams pair notebooks with sensors and are very useful.\n\nSame text.\n\nOld idea entirely here.\n"
        new = "# T\n\n## A\n\nField teams pair notebooks with sensors and help.\n\nSame text.\n\nA completely different sentence now stands.\n\nAdded line.\n"
        out = ur.changes(old, new)
        self.assertEqual(out[0], "## A")
        self.assertIn("Field teams pair notebooks with sensors and ~~are very useful.~~ 🟢 **help.**", out)
        self.assertIn("~~Old idea entirely here.~~\n\n🟢 **A completely different sentence now stands.**", out)
        self.assertIn("🟢 **Added line.**", out)
        self.assertNotIn("Same text.", "\n".join(out))

    def test_snapshot_names_and_ignores_copies(self):
        if not shutil.which("git"):
            self.skipTest("needs git")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"), \
             mock.patch.object(ur, "log", lambda *a: None):
            repo = Path(d) / "repo"
            (repo / "docs").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            f = repo / "docs" / "memo.md"
            f.write_text("One.\n")
            self.assertEqual(ur.snapshot(f).name, "memo-v1.md")
            f.write_text("Two.\n")
            self.assertEqual(ur.snapshot(f).name, "memo-v2.md")
            self.assertEqual((repo / ".gitignore").read_text(), "/docs/memo-v*.md\n")  # added once
            out = ur.write_changes(f, "1")
            self.assertEqual(out.name, "memo-v1-to-v2.md")
            self.assertIn("~~One.~~", out.read_text())


class AuthErrors(unittest.TestCase):
    def test_draft_words_are_not_login_errors(self):
        self.assertIsNone(ur.AUTH_ERROR.search("Records stay local unless authorized. Users log in to the app."))
        for msg in ["Error: not logged in", "401 Unauthorized", "Please log in with codex login", "Invalid API key"]:
            self.assertIsNotNone(ur.AUTH_ERROR.search(msg), msg)


if __name__ == "__main__":
    unittest.main()
