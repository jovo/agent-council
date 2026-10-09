"""Tests for unified-review. Run: python3 -m unittest discover tests"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
        # Claude raised A1, so its agree does not count: no other model agreed.
        self.assertFalse(rejected["contested"])
        kept = ur.score_group([finding("A1")], {"claude": {"A1": vote("agree")}, "gpt": {"A1": vote("partial")},
                                                "gemini": {"A1": vote("agree")}}, voters, owner)
        self.assertFalse(kept["rejected"])
        self.assertFalse(kept["contested"])
        self.assertEqual(kept["score"], 1.5)
        split = ur.score_group([finding("A1")], {"claude": {"A1": vote("agree")}, "gpt": {"A1": vote("agree")},
                                                 "gemini": {"A1": vote("disagree")}}, voters, owner)
        self.assertTrue(split["contested"])

    def test_score_group_does_not_count_the_raisers_vote(self):
        owner = {"A": "claude", "B": "gpt"}
        voters = ["claude", "gpt", "gemini"]
        # Gemini did not vote. Counting Claude's vote on its own finding would make
        # this 1 disagree of 2, not a majority. Without it, 1 of 1 rejects.
        g = ur.score_group([finding("A1")], {"claude": {"A1": vote("agree", severity="Critical")},
                                             "gpt": {"A1": vote("disagree", severity="Polish")}, "gemini": {}},
                           voters, owner)
        self.assertTrue(g["rejected"])
        self.assertEqual(g["severity"], "Polish")
        self.assertIn("claude", g["votes"])  # still shown
        self.assertEqual(ur.vote_tag(g), "No majority")

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

    def test_preflight_keeps_panelist_with_api_key(self):
        def fake(cmd, **kw):
            return SimpleNamespace(returncode=1, stdout="Not logged in", stderr="")
        with mock.patch.object(ur.subprocess, "run", fake), \
                mock.patch.dict(ur.CHILD_ENV, {"CODEX_API_KEY": "k", "CURSOR_API_KEY": "k"}):
            self.assertEqual(ur.preflight(["gpt", "gemini"]), ["gpt", "gemini"])
        self.assertEqual(ur.FAILURES, [])


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

    def test_locate_pdf_quote_across_table_columns(self):
        pdf = self.tmp / "report.pdf"
        pdf.write_bytes(b"%PDF")
        page = ("Intro.\f GeCo-SRT          training on corrections; focuses on geometry\n"
                "                   reaches 56.7% success versus 43.3% from scratch\n")
        with mock.patch.object(ur, "doc_text", lambda p: page):
            self.assertEqual(ur.locate("GeCo-SRT          reaches 56.7% success versus 43.3% from scratch", [pdf]),
                             (pdf, 2, "page"))
            self.assertIsNone(ur.locate("GeCo-SRT          reaches 99% success", [pdf]))

    def test_conversion_gaps(self):
        raw = ("Title\nWe fine-tune at 56.7% on the furni-\nture task, then finetuning again.\nAcme Confidential\n1\n\f"
               "Table\n2026\nRows here.\nAcme Confidential\n2\n\f")
        md = "# Title\n\nWe fine-tune at 56.7% on the furniture task, then fine-tuning again.\n\nTable\n\n2026<br>Rows here.\n"
        run = lambda cmd, **k: SimpleNamespace(stdout=raw, returncode=0)
        with mock.patch.object(ur.subprocess, "run", run):
            self.assertEqual(ur.conversion_gaps("x.pdf", md), ([], []))
            self.assertEqual(ur.conversion_gaps("x.pdf", md.replace("56.7", "57.6").replace("Rows here.", "")),
                             (["56", "7", "here", "rows"], ["57", "6"]))

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


class Linux(unittest.TestCase):
    """Off macOS (e.g. a codespace) nothing calls `open` or `osascript`."""
    def run_with(self, env, fn, which=lambda c: "/usr/bin/" + c):
        cmds, out = [], []
        with mock.patch.object(ur.sys, "platform", "linux"), \
             mock.patch.dict(ur.os.environ, env, clear=True), \
             mock.patch.object(ur.shutil, "which", which), \
             mock.patch.object(ur.subprocess, "run", lambda cmd, **k: cmds.append(cmd) or SimpleNamespace(returncode=0)), \
             mock.patch("builtins.print", lambda *a, **k: out.append(" ".join(map(str, a)))):
            fn()
        return cmds, out

    def test_open_file(self):
        f = lambda: ur.open_file("/r/unified.md")
        self.assertEqual(self.run_with({"CODESPACES": "true"}, f)[0], [["code", "/r/unified.md"]])
        self.assertEqual(self.run_with({}, f)[0], [["xdg-open", "/r/unified.md"]])
        cmds, out = self.run_with({}, f, which=lambda c: None)
        self.assertEqual(cmds, [])
        self.assertEqual(out, ["Result: /r/unified.md"])

    def test_page_opens_the_forwarded_url_in_a_codespace(self):
        env = {"CODESPACE_NAME": "cs", "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
               "BROWSER": "/vscode/helpers/browser.sh"}
        with mock.patch.object(ur, "page_url", lambda p: "http://127.0.0.1:8737/"):
            cmds, out = self.run_with(env, lambda: ur.open_page("/d/memo.md"))
        self.assertEqual(cmds, [["/vscode/helpers/browser.sh", "https://cs-8737.app.github.dev/"]])
        self.assertEqual(out, ["Review page: https://cs-8737.app.github.dev/"])

    def test_page_url_is_unchanged_outside_a_codespace(self):
        with mock.patch.dict(ur.os.environ, {}, clear=True):
            self.assertEqual(ur.public_url("http://127.0.0.1:5000/"), "http://127.0.0.1:5000/")


class ChildEnv(unittest.TestCase):
    def child_env(self, env):
        with mock.patch.dict(ur.os.environ, env, clear=True):
            mod = SourceFileLoader("ur_env", str(REPO / "bin" / "unified-review")).load_module()
        return mod.CHILD_ENV

    def test_oauth_token_kept_only_outside_claude_code(self):
        self.assertEqual(self.child_env({"CLAUDE_CODE_OAUTH_TOKEN": "t"}), {"CLAUDE_CODE_OAUTH_TOKEN": "t"})
        self.assertEqual(self.child_env({"CLAUDE_CODE_OAUTH_TOKEN": "t", "CLAUDECODE": "1"}), {})


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

    def run_review(self, panel, fails=(), draft_text="The sky is green today. Grass grows slowly.", reply=None):
        prompts = {}

        def fake_call(m, prompt, out, workdir, web=False, stage=""):
            prompts.setdefault(stage, {})[m] = prompt
            if m in fails or (stage, m) in fails:
                ur.fail(stage, m, "fake failure")
                return None
            if stage == "review" and reply is not None:
                return reply
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


    def test_a_review_may_find_nothing(self):
        prompts, r, md = self.run_review(["claude", "gpt", "gemini"], reply="NO FINDINGS")
        self.assertEqual(sorted(r["reviewers_ok"]), ["claude", "gemini", "gpt"])
        self.assertNotIn("grok", r["panel"])  # finding nothing is not a failure
        self.assertNotIn("vote", prompts)
        self.assertEqual(r["groups"], [])
        self.assertNotIn("Failed", md)

    def test_a_reply_in_the_wrong_format_still_fails(self):
        with self.assertRaises(SystemExit):  # every reviewer, and the stand-in, fails after a retry
            self.run_review(["claude", "gpt", "gemini"], reply="Looks fine to me.")


def typo_group(old, new, votes=None, where="draft"):
    body = f"Fix it.\n\n~~{old}~~ 🟢 **{new}**"
    return {"rep": {"body": body, "quote": old, "title": "t"}, "where": where, "self_voter": "claude",
            "votes": votes or {"claude": vote("agree"), "gpt": vote("agree"), "gemini": vote("partial")},
            "severity": "Polish", "rejected": False, "frac": 1, "pos": 0}


class Typos(unittest.TestCase):
    def test_typo_change(self):
        self.assertEqual(ur.typo_change("the recieve step", "the receive step"), ("recieve", "receive"))
        self.assertEqual(ur.typo_change("teh cortex", "the cortex"), ("teh", "the"))
        self.assertEqual(ur.typo_change("in the the cortex", "in the cortex"), ("the the", "the"))
        self.assertEqual(ur.typo_change("english prose", "English prose"), ("english", "English"))
        self.assertIsNone(ur.typo_change("not here", "now here"))  # short words: a real change
        self.assertIsNone(ur.typo_change("in 2019 we", "in 2018 we"))  # numbers
        self.assertIsNone(ur.typo_change("However we", "However, we"))  # punctuation
        self.assertIsNone(ur.typo_change("a large effect", "a modest effect"))
        self.assertIsNone(ur.typo_change("the recieve and teh", "the receive and the"))  # two words

    def test_typo_needs_no_dissent(self):
        self.assertTrue(ur.is_typo(typo_group("recieve", "receive")))
        disputed = typo_group("recieve", "receive", {"claude": vote("agree"), "gpt": vote("disagree")})
        self.assertFalse(ur.is_typo(disputed))
        own = typo_group("recieve", "receive", {"claude": vote("disagree"), "gpt": vote("agree")})
        self.assertTrue(ur.is_typo(own))  # only the raiser's own vote disagrees

    def test_typos_are_numbered_last(self):
        polish = typo_group("a large effect", "a modest effect")
        typo = typo_group("recieve", "receive")
        polish["pos"], typo["pos"] = 50, 10
        r = {"groups": [typo, polish], "headings": []}
        self.assertEqual([sev for _, sev, _, _ in ur.ordered_findings(r)], ["Polish", "Typo"])


class MechanicalChecks(unittest.TestCase):
    def run_checks(self, text, bib=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "refs.bib").write_text(bib or "@article{Friston10,\n title={x}}\n")
            doc = d / "memo.md"
            doc.write_text(text)
            with mock.patch.object(ur, "BIB", d / "refs.bib"):
                return [c["what"] for c in ur.checks(text, doc)]

    def test_equations(self):
        text = "$$a\\tag{1}$$\n\n$$b\\tag{3}$$\n\nBy Eq. (1) and Eq. (2), and Eq. (3)."
        out = self.run_checks(text)
        self.assertIn("Equation 3 follows Equation 1.", out)
        self.assertIn("Equation 2 is cited but does not exist.", out)

    def test_figures(self):
        text = "**Figure 1.** Caption.\n\n**Figure 2.** Another.\n\nSee Figure 1 and Figure 4."
        out = self.run_checks(text)
        self.assertIn("Figure 4 is cited but does not exist.", out)
        self.assertIn("Figure 2 is never cited in the text.", out)
        self.assertNotIn("Figure 1 is never cited in the text.", out)  # its caption is not a citation

    def test_links_citations_and_terms(self):
        text = ("# Methods\n\n<a id=\"table-1-1\"></a>\n\nSee [Table 1.1](#table-1-1), [above](#methods), "
                "and [gone](#nowhere). As in [@Friston10; @Nobody99]. A multi-model panel. "
                "Multimodel panels vote. `multi-model` in code does not count.")
        out = self.run_checks(text)
        self.assertEqual(out, ["Link to #nowhere has no matching anchor or heading.",
                               "Citation key @Nobody99 is not in the bibliography.",
                               '"multi-model" (1×) and "multimodel" (1×) are both used.'])

    def test_double_spaces(self):
        text = ("One sentence.  Two words  apart.\n\n| a  | b |\n|---|---|\n\nKeep `x  y` in code.  "
                "Indented lines keep their indentation.\nHard break at the end  \nnext line.")
        out = self.run_checks(text)
        self.assertEqual(out, ["Two or more spaces where one belongs (3×, lines 1, 6)."])
        fixed = ur.fix_double_spaces(text)
        self.assertIn("One sentence. Two words apart.", fixed)
        self.assertIn("| a  | b |", fixed)  # tables are aligned on purpose
        self.assertIn("`x  y` in code. Indented", fixed)
        self.assertIn("at the end  \n", fixed)

    def test_clean_draft_has_no_checks(self):
        self.assertEqual(self.run_checks("A plain paragraph with no numbering at all."), [])


class CarryOver(unittest.TestCase):
    def group(self, title, quote, rejected=False):
        return {"rep": {"title": title, "quote": quote}, "rejected": rejected}

    def test_keys_follow_a_repeated_finding(self):
        prev = [{"key": "Kaaaaaa", "title": "Overclaim in intro", "quote": "The effect is large.", "seen": 2},
                {"key": "Kbbbbbb", "title": "Vague term", "quote": "many things happen here", "seen": 1},
                {"key": "Kccccc0", "title": "Missing baseline", "quote": "We beat the baseline easily.", "seen": 1}]
        same_title = self.group("overclaim in intro", "The effect is big.")
        same_quote = self.group("A different title", "many things happen here")
        new = self.group("New point", "Something else entirely here.")
        dnorm = ur.norm("The effect is big. many things happen here. Something else entirely here.")
        since = ur.carry_over([same_title, same_quote, new], prev, dnorm)
        self.assertEqual((same_title["key"], same_title["seen"]), ("Kaaaaaa", 3))
        self.assertEqual((same_quote["key"], same_quote["seen"]), ("Kbbbbbb", 2))
        self.assertEqual(new["seen"], 1)
        self.assertTrue(new["key"].startswith("K"))
        # The baseline sentence is gone from the draft, so its finding counts as resolved.
        self.assertEqual(since, {"resolved": ["Missing baseline"], "dropped": []})

    def test_unchanged_passage_not_raised_again_is_dropped(self):
        prev = [{"key": "Kaaaaaa", "title": "Vague term", "quote": "many things happen here", "seen": 1}]
        rejected = self.group("Vague term", "many things happen here", rejected=True)
        since = ur.carry_over([rejected], prev, ur.norm("many things happen here."))
        self.assertEqual(since, {"resolved": [], "dropped": ["Vague term"]})

    def test_open_block(self):
        self.assertEqual(ur.open_block([]), "")
        block = ur.open_block([{"title": "Vague term", "quote": "many things", "key": "K1", "seen": 1}])
        self.assertIn("Vague term (quote: many things)", block)
        self.assertIn("same title", block)


DECK = """---
marp: true
theme: base
---

<!-- _class: cover -->

# Learning that looks ahead

---

# Models forget old tasks

- One
- Two
- Three
- Four

> First takeaway

> Second takeaway

---

# Prospective learners plan

Fragments<br>here

---

<!-- _class: full -->

![bg](https://example.com/thumb.jpg)

[Play · 2:10](https://example.com/v)

---

# References

- A
- B
- C
- D
"""


class Decks(unittest.TestCase):
    def test_detection(self):
        self.assertTrue(ur.is_deck(Path("deck.md"), DECK))
        self.assertFalse(ur.is_deck(Path("memo.md"), "# Memo\n\nText."))
        self.assertFalse(ur.is_deck(Path("deck.txt"), DECK))

    def test_slides_and_titles(self):
        got = [(n, title, cls) for _, _, n, title, cls in ur.slides(DECK)]
        self.assertEqual(got, [(1, "Learning that looks ahead", "cover"), (2, "Models forget old tasks", ""),
                               (3, "Prospective learners plan", ""), (4, "Play · 2:10", "full"), (5, "References", "")])
        heads = ur.slide_headings("===== deck.md =====\n" + DECK)
        self.assertEqual([h for _, h in heads][:2], ["Slide 1: Learning that looks ahead", "Slide 2: Models forget old tasks"])

    def test_deck_checks(self):
        out = [w for _, w in ur.deck_checks(DECK)]
        self.assertIn("Slide 2 has a plain list of 4 items. The deck rules allow three, and longer parallel "
                      "content goes in cols.", out)
        self.assertIn("Slide 2 has 2 takeaways. One per slide.", out)
        self.assertIn("Slide 3 uses <br>, which the deck rules forbid.", out)
        self.assertFalse(any("Slide 5" in w for w in out))  # a reference list may be long
        self.assertFalse(any("in a row" in w for w in out))  # the full slide breaks the run

    def test_a_handle_link_is_not_a_citation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "refs.bib").write_text("@article{Friston10,\n}\n")
            with mock.patch.object(ur, "BIB", Path(d) / "refs.bib"):
                out = ur.checks("Play at [@Floyd](https://lichess.org/@/Floyd).", Path(d) / "x.md")
        self.assertEqual(out, [])


class Placement(unittest.TestCase):
    TEXT = ("| A | Does not learn; task examples follow. |\n| B | Measures robustness; texture is not friction. |\n\n"
            "Each method will have the same budget and safety limits.\n")

    def test_same_fix_in_separate_cells(self):
        body = ("Semicolons.\n\nDoes not learn~~;~~🟢 **.** ~~task~~ 🟢 **Task** examples follow.\n\n"
                "Measures robustness~~;~~🟢 **.** ~~texture~~ 🟢 **Texture** is not friction.")
        old, new, edits = ur.placed_diff(self.TEXT, body, "")
        self.assertEqual(len(edits), 2)
        self.assertIn("Does not learn. Task examples follow.", new)

    def test_addition_bolded_without_marker(self):
        body = "Budget.\n\nEach method will have the same budget~~ and~~🟢 **,** safety limits**, and compute.**"
        self.assertIsNone(ur.locate_edits(self.TEXT, *ur.diff_parts(body)))
        old, new, edits = ur.placed_diff(self.TEXT, body, "")
        self.assertEqual(new, "Each method will have the same budget, safety limits, and compute.")
        self.assertTrue(edits)

    def test_addition_with_no_anchor(self):
        reason = ur.unplaced_reason(self.TEXT, self.TEXT, "(no row)", "| C | new |", "")
        self.assertTrue(reason.startswith("the change adds text without quoting where it goes"))


class Summary(unittest.TestCase):
    def test_written_once_in_background_then_kept(self):
        run = Path(tempfile.mkdtemp())
        (run / "unified.md").write_text("## Critical\n\n### 1. F1 is never defined\n")
        calls = []
        def call(name, prompt, out, workdir, stage=""):
            calls.append(prompt)
            return 'Here: {"themes": [{"theme": "Definitions", "gist": "F1 is undefined.", "findings": [1, "x"]}]}'
        with mock.patch.object(ur, "call", call), mock.patch.object(ur, "load_rules", lambda p: ("rules", "")):
            self.assertEqual(ur.summary_state(run), {"status": "pending"})
            for _ in range(100):
                if (run / "summary.json").exists():
                    break
                time.sleep(0.01)
            self.assertEqual(ur.summary_state(run), {"status": "done", "themes": [
                {"theme": "Definitions", "gist": "F1 is undefined.", "findings": [1]}]})
        self.assertEqual(len(calls), 1)
        self.assertIn("F1 is never defined", calls[0])
        shutil.rmtree(run)


class Churn(unittest.TestCase):
    def test_times_changed(self):
        history = ["Alpha one.\n\nBeta one.", "Alpha two.\n\nBeta one.", "Alpha three.\n\nBeta one."]
        self.assertEqual(ur.times_changed("Alpha four.", history), [True, True, True])
        self.assertEqual(ur.times_changed("Beta one.", history), [False, False, False])
        self.assertEqual(ur.times_changed("Something entirely unrelated here.", history), [])

    def test_restores_earlier(self):
        text = "The model predicts spikes well. Next sentence."
        history = ["The model predicts spikes accurately. Next sentence."]
        undo = ur.locate_edits(text, "spikes well", "spikes accurately")
        other = ur.locate_edits(text, "spikes well", "spikes reliably")
        self.assertTrue(ur.restores_earlier(text, undo, history))
        self.assertFalse(ur.restores_earlier(text, other, history))

    def test_churn_holds_polish_on_a_passage_that_just_changed(self):
        text = "Alpha four words here.\n\nBeta stays the same."
        history = ["Alpha three words here.\n\nBeta stays the same."]
        g = typo_group("Alpha four words", "Alpha five words")
        self.assertIn("changed since the last review", ur.churn(g, text, history))
        g["severity"] = "Substantive"
        self.assertIsNone(ur.churn(g, text, history))
        steady = typo_group("Beta stays", "Beta remains")
        self.assertIsNone(ur.churn(steady, text, history))

    def test_churn_allows_only_critical_after_two_changes(self):
        text = "Alpha four words here."
        history = ["Alpha two words here.", "Alpha three words here."]
        g = typo_group("Alpha four words", "Alpha five words")
        g["severity"] = "Substantive"
        self.assertIn("2 of the last 2", ur.churn(g, text, history))
        g["severity"] = "Critical"
        self.assertIsNone(ur.churn(g, text, history))

    def test_typos_are_never_held(self):
        text = "Alpha recieve words here."
        history = ["Alpha two words here.", "Alpha three words here."]
        self.assertIsNone(ur.churn(typo_group("recieve", "receive"), text, history))


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


class ReviewPage(unittest.TestCase):
    def test_diff_parts_variants(self):
        body = "Point.\n\nThe sky ~~is green~~ 🟢 **is blue** today."
        self.assertEqual(ur.diff_parts(body), ("The sky is green today.", "The sky is blue today."))
        body = "Point.\n\nOur own eyes.**~~ .~~**"
        self.assertEqual(ur.diff_parts(body), ("Our own eyes. .", "Our own eyes."))
        body = "Point.\n\n~~Old sentence here.~~ **🟢 New sentence here.**"
        self.assertEqual(ur.diff_parts(body), ("Old sentence here.", "New sentence here."))
        body = "Point.\n\n```\n| Pillar | A |\n| Pillar or wedge | A |\n```"
        self.assertEqual(ur.diff_parts(body), ("| Pillar | A |", "| Pillar or wedge | A |"))
        body = "Point.\n\nA separate source, ~~much ~~like glasses."
        self.assertEqual(ur.diff_parts(body), ("A separate source, much like glasses.", "A separate source, like glasses."))
        body = "Point.\n\nKeep this ~~extra~~\nnext line."
        self.assertEqual(ur.diff_parts(body), ("Keep this extra\nnext line.", "Keep this\nnext line."))
        body = "Point.\n\n```markdown\nThe sky ~~is green~~ 🟢 **is blue** today.\n```"
        self.assertEqual(ur.diff_parts(body), ("The sky is green today.", "The sky is blue today."))
        self.assertIsNone(ur.diff_parts("Point.\n\n```markdown\nOur plan:~~ ~~\n```")[0])
        self.assertIsNone(ur.diff_parts("Point only.")[0])
        self.assertIsNone(ur.diff_parts("Point.\n\nx ~~a~~ 🟢 **[name the barrier]**")[0])
        self.assertIsNone(ur.diff_parts("Point.\n\nRECAP 🟢 **{{citation: Author, year}}** works.")[0])

    def test_transcribe_needs_a_key(self):
        with mock.patch.dict(ur.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "ELEVENLABS_API_KEY"):
                ur.transcribe(b"audio", "webm")

    def test_slot_diff_is_placed_but_not_applicable(self):
        body = "Point.\n\nWe test F1 🟢 **, defined as {{one-line definition}},** on data."
        self.assertEqual(ur.diff_parts(body)[1], ur.SLOT)
        old, new = ur.diff_parts(body, slots=True)
        self.assertEqual((old, new), ("We test F1 on data.", "We test F1, defined as {{one-line definition}}, on data."))

    def test_find_span_and_fuzzy(self):
        text = "Records stay local.  The person\u2019s data stays home."
        s = ur.find_span(text, "The person's data stays home.")
        self.assertEqual(text[s[0]:s[1]], "The person\u2019s data stays home.")
        text = "We test voluntary initiation, intelligible feedback, interruptibility, and influence."
        q = ur.find_span(text, "intelligible feedback, interruptibility")
        old = "We test voluntary initiation, intelligible feedback, and interruptibility, and influence."
        self.assertIsNone(ur.find_span(text, old))
        f = ur.fuzzy_span(text, old, q)
        self.assertEqual(text[f[0]:f[1]], text)
        self.assertIsNone(ur.fuzzy_span(text, "Something else entirely about robots and pay.", q))

    def test_accept_decline_and_conflict(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            doc = Path(d).resolve() / "memo.md"
            doc.write_text("# Memo\n\nThe sky is green today. Grass grows.\n\nWater is dry.\n")
            run = Path(d) / "runs" / "r1"
            run.mkdir(parents=True)
            g = lambda t, q, body: {"rep": {"title": t, "quote": q, "body": body}, "severity": "Substantive",
                                    "where": "draft", "pos": 0, "rejected": False, "votes": {"claude": {"vote": "agree"}},
                                    "raised_by": ["claude"], "frac": 1.0}
            (run / "results.json").write_text(json.dumps({
                "files": [str(doc)], "labels": {"claude": "Claude Sonnet"}, "reviewers_ok": ["claude"],
                "headings": [], "groups": [
                    g("Sky", "The sky is green today.", "Wrong.\n\nThe sky ~~is green~~ 🟢 **is blue** today."),
                    g("Water", "Water is dry.", "Wrong.\n\nWater is ~~dry~~ 🟢 **wet**.")]}))
            page = ur.PageServer(doc)
            code, _, out = page.handle("GET", "/api/state", {})
            st = json.loads(out)
            self.assertEqual([f["applicable"] for f in st["findings"]], [True, True])
            self.assertEqual(page.handle("POST", "/api/accept", {"n": 1})[0], 200)
            self.assertIn("The sky is blue today.", doc.read_text())
            doc.write_text(doc.read_text().replace("Water is dry.", "Water is arid."))
            code, _, out = page.handle("POST", "/api/accept", {"n": 2})
            self.assertEqual(code, 409)
            self.assertIn("Water is arid.", doc.read_text())
            self.assertEqual(page.handle("POST", "/api/decline", {"n": 2, "note": "fine"})[0], 200)
            st = json.loads(page.handle("GET", "/api/state", {})[2])
            self.assertEqual([f["status"] for f in st["findings"]], ["accepted", "declined"])

    def test_parse_answer(self):
        cur = "Intro. We test the links first, which leave one link open. End."
        ans, old, new, ok = ur.parse_answer("Not Critical.\n\nREVISED: We test the links first~~, which leave one link open~~ 🟢 **and name what would refute them**.", cur)
        self.assertEqual(ans, "Not Critical.")
        self.assertTrue(ok)
        self.assertEqual(new, "We test the links first and name what would refute them.")
        self.assertEqual(ur.parse_answer("Fine as is.\nREVISED: none", cur)[1:], (None, None, False))
        self.assertFalse(ur.parse_answer("x\nREVISED: Text ~~not~~ 🟢 **never** in the draft at all.", cur)[3])

    def test_kind_parsing_and_majority(self):
        fs = ur.parse_findings("=== FINDING\nseverity: Critical\nkind: Logic\ntitle: T\nquote: q\n---\nPoint.")
        self.assertEqual(fs[0]["kind"], "logic")
        v = ur.parse_votes("A1 | agree | Polish | style | same:none | ok\nA2 | partial | Critical | same:none | old format")
        self.assertEqual((v["A1"]["kind"], v["A2"]["kind"]), ("style", ""))
        self.assertEqual(ur.majority_kind(["logic", "clarity", "clarity"], "logic"), "clarity")
        self.assertEqual(ur.majority_kind(["logic", "clarity"], ""), "logic")  # ties go to logic
        self.assertEqual(ur.majority_kind([], "evidence"), "evidence")

    def test_parse_changes(self):
        cur = "One sentence here. Another sentence there."
        ans, ch = ur.parse_changes("Do this.\n\nCHANGES:\nOne ~~sentence~~ 🟢 **line** here.\n\nAnother ~~sentence~~ 🟢 **line** there.", cur)
        self.assertEqual(ans, "Do this.")
        self.assertEqual([c["new"] for c in ch], ["One line here.", "Another line there."])
        self.assertTrue(all(c["applicable"] for c in ch))
        self.assertEqual(ur.parse_changes("Fine.\nCHANGES: none", cur)[1], [])

    def test_panelist_specs(self):
        with mock.patch.object(ur, "cursor_models", lambda: {"kimi-k3-low": "Kimi K3 Low"}):
            k = ur.panelist("cursor:kimi-k3-low")
            self.assertEqual(ur.PANELISTS[k], ("cursor", "kimi-k3-low", "Kimi K3 Low"))
            k = ur.panelist("codex:gpt-5.6-luna@medium")
            self.assertEqual((ur.PANELISTS[k][1], ur.EFFORT[k]), ("gpt-5.6-luna", "medium"))
            self.assertEqual(ur.panelist("claude"), "claude")
            with self.assertRaises(ValueError):
                ur.panelist("nonsense")

    def test_change_mark(self):
        t = "Within primates, neuron number scales with brain size, and it correlates with behavior."
        mark = lambda old, new: (lambda s: (lambda m: t[m[0]:m[1]])(ur.change_mark(t, s, old, new)))(ur.find_span(t, old))
        self.assertEqual(mark("size, and it correlates", "size, and neuron number correlates"), "it")
        self.assertEqual(mark("and it correlates", "and it strongly correlates"), "it")
        self.assertEqual(mark("Within primates, neuron", "Across species, cell"), "Within primates, neuron")

    def test_ellipsis_diff(self):
        body = "Point.\n\nThe kit ~~combines~~ 🟢 **pairs** cameras ... and ~~also records~~ 🟢 **records** demos."
        old, new = ur.diff_parts(body)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "m.md"
            f.write_text("The kit combines cameras, phones, and rings, and also records demos. End.")
            self.assertIsNone(ur.apply_change(f, old, new))
            self.assertEqual(f.read_text(), "The kit pairs cameras, phones, and rings, and records demos. End.")
            f.write_text("The kit combines cameras, and nothing else.")
            self.assertIsNotNone(ur.apply_change(f, old, new))  # a part is missing: refuse
            self.assertEqual(f.read_text(), "The kit combines cameras, and nothing else.")

    def test_no_review_markup_reaches_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "m.md"
            f.write_text("A because the model acts. B [@S04].  We explore. Keep **bold**.")
            self.assertIsNone(ur.apply_change(f, "because the model", "because\n=== END FINDINGthe model"))
            self.assertIsNone(ur.apply_change(f, "[@S04].  We", "[@S04].🟢 We"))
            self.assertIsNone(ur.apply_change(f, "acts.", "~~acts~~ 🟢 **works**."))
            self.assertEqual(f.read_text(), "A because the model works. B [@S04]. We explore. Keep **bold**.")
            self.assertIsNone(ur.edit_block(f, "Keep **bold**.", "Keep **bold**. 🟢 More.\n=== END FINDING"))
            self.assertNotRegex(f.read_text(), r"🟢|~~|FINDING")

    def test_why_a_change_cannot_be_placed(self):
        reviewed = "The archive keeps records local, and they leave only when exported. Other text."
        why = lambda text, old, new: ur.unplaced_reason(text, reviewed, old, new, "")
        fixed = "The archive keeps records local, and the records leave only when exported. Other text."
        self.assertIn("already in the file",
                      why(fixed, "and they leave", "and the records leave"))
        self.assertIn('now reads: "The archive keeps records local, and the records leave only when exported."',
                      why(fixed, "The archive keeps records local, and they leave only when exported.",
                          "The archive keeps records local, and records then leave only when exported."))
        self.assertIn("not in the draft as reviewed",
                      why(fixed, "and it leaves", "and the data leaves"))

    def test_cited_refs_in_order_of_first_citation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "refs.bib").write_text(
                "@article{Cohen80,\n  title = {{Preserved learning}},\n  author = {Cohen, Neal J and Squire, Larry R},\n"
                "  date = {1980},\n  journaltitle = {{Science}},\n  doi = {10.1126/science.7414331}\n}\n")
            text = "---\nbibliography: refs.bib\n---\nA [@Missing; @Cohen80]. B [@Cohen80].\n"
            refs = ur.cited_refs(text, Path(d) / "m.md")
        self.assertEqual([r["key"] for r in refs], ["Missing", "Cohen80"])
        self.assertEqual(refs[0]["text"], "")
        self.assertEqual(refs[1]["text"], "Cohen NJ, Squire LR (1980). Preserved learning. Science.")
        self.assertEqual(refs[1]["url"], "https://doi.org/10.1126/science.7414331")
        if shutil.which("pandoc"):  # the book's PLOS format, DOI linked
            self.assertIn('Science</span>. 1980. doi:<a href="https://doi.org/10.1126/science.7414331">',
                          " ".join(refs[1]["html"].split()))

    def test_settled_findings_show_as_done(self):
        """A finding is done when another review's decision covered its sentence (as
        when you accept while Update runs), or when its change is already in the file."""
        quote = "The archive keeps records local, and they leave only when exported."
        g = lambda title, new: {"rep": {"title": title, "quote": quote, "body": f"Point.\n\n~~{quote}~~ 🟢 **{new}**"},
                                "votes": {}, "raised_by": [], "where": "", "kind": "clarity"}
        groups = [g("Pronoun", "The archive keeps records local, and the records go only when exported."),
                  g("Present", "The archive keeps records local, and the records leave only when exported.")]
        earlier = [{"decision": "applied", "title": "Resolve the pronoun", "quote": quote, "run": "2026-10-08-2132-x-v15"}]
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "2026-10-08-2140-x-v16"
            (run / "reviewed").mkdir(parents=True)
            (run / "results.json").write_text('{"labels": {}, "reviewers_ok": []}')
            draft = Path(d) / "m.md"
            draft.write_text("The archive keeps records local, and the records leave only when exported.\n")

            def state(decisions):
                with mock.patch.object(ur, "ordered_findings", lambda r: [(1, "Polish", "", groups[0]), (2, "Polish", "", groups[1])]), \
                     mock.patch.object(ur, "load_decisions", lambda: {str(draft): decisions}), \
                     mock.patch.object(ur, "load_questions", lambda run: {}), \
                     mock.patch.object(ur, "page_panel", lambda p: []):
                    return [(f["status"], f["note"]) for f in ur.page_state(draft, run)["findings"]]
            done_earlier = ("accepted", "Done: accepted in the 21:32 review as \u201cResolve the pronoun\u201d")
            self.assertEqual(state(earlier), [done_earlier, done_earlier])
            self.assertEqual(state([]), [(None, ""), ("accepted", "Done: the change is already in the file")])

    def test_a_filled_slot_becomes_the_proposed_text(self):
        quote = "These systems interact."
        g = {"rep": {"title": "Cite it", "quote": quote, "body": f"Point.\n\n~~{quote}~~ 🟢 **These systems interact {{{{citation: Author, year}}}}.**"},
             "votes": {}, "raised_by": [], "where": "", "kind": "evidence"}
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "2026-10-09-1000-x-v1"
            (run / "reviewed").mkdir(parents=True)
            (run / "results.json").write_text('{"labels": {}, "reviewers_ok": []}')
            draft = Path(d) / "m.md"
            draft.write_text(quote + "\n")

            def state():
                with mock.patch.object(ur, "ordered_findings", lambda r: [(1, "Substantive", "", g)]), \
                     mock.patch.object(ur, "load_decisions", lambda: {}), \
                     mock.patch.object(ur, "load_questions", lambda run: {}), \
                     mock.patch.object(ur, "page_panel", lambda p: []):
                    f = ur.page_state(draft, run)["findings"][0]
                    return f["applicable"], f["slot"], f["reason"], f["new"]
            self.assertEqual(state()[:3], (True, True, ur.SLOT))  # Accept writes the blank, Fill fills it
            ur.save_fill(run, 1, {"status": "done", "text": "These systems interact [@Squire04].", "sources": []})
            self.assertEqual(state(), (True, False, None, "These systems interact [@Squire04]."))

    def test_a_comment_about_a_selected_passage_sends_it(self):
        prompts = []
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run"
            run.mkdir()
            draft = Path(d) / "m.md"
            draft.write_text("The sky is green.\n")
            with mock.patch.object(ur, "call", lambda m, prompt, *a, **k: prompts.append(prompt) or "Fine.\nCHANGES: none"), \
                 mock.patch.object(ur, "page_panel", lambda p: ["claude"]), \
                 mock.patch.object(ur, "load_rules", lambda p: ("rules", "")):
                ur.comment_panel(draft, run, "Is this right?", False, "The sky is green.")
                for _ in range(200):
                    if ur.load_comments(run)[0]["answers"]["claude"]["status"] != "pending":
                        break
                    time.sleep(0.01)
            self.assertIn("<passage>\nThe sky is green.\n</passage>", prompts[0])
            self.assertEqual(ur.load_comments(run)[0]["passage"], "The sky is green.")

    def test_end_marker_dropped(self):
        fs = ur.parse_findings("=== FINDING\nseverity: Polish\ntitle: T\nquote: a b\n---\nPoint.\n\na ~~b~~ 🟢 **c**.\n=== END FINDING\n")
        self.assertNotIn("END FINDING", fs[0]["body"])
        self.assertEqual(ur.diff_parts("Point.\n\na ~~b~~ 🟢 **c**.\n=== END FINDING"), ("a b.", "a c."))

    def test_parse_model_id(self):
        p = lambda m: ur.parse_model_id(m)[:3]
        self.assertEqual(p("claude-opus-5-5-thinking-high-fast"), ("Opus", "5.5", "High, thinking, fast"))
        self.assertEqual(p("claude-4.6-opus-high-thinking"), ("Opus", "4.6", "High, thinking"))
        self.assertEqual(p("gpt-5.6-luna-xhigh"), ("Luna", "5.6", "Extra high"))
        self.assertEqual(p("gpt-5.5-extra-high-fast"), ("GPT", "5.5", "Extra high, fast"))
        self.assertEqual(p("gemini-3.8-flash-low"), ("Flash", "3.8", "Low"))
        self.assertEqual(p("cursor-grok-4.6-medium"), ("Grok", "4.6", "Medium"))
        self.assertEqual(p("kimi-k3-low"), ("Kimi", "K3", "Low"))

    def test_edit_block(self):
        with tempfile.TemporaryDirectory() as d:
            doc = Path(d) / "memo.md"
            doc.write_text("# Memo\n\nFirst paragraph.\n\nSecond paragraph.\n")
            self.assertIsNone(ur.edit_block(doc, "First paragraph.", "First, rewritten.", 8))
            self.assertIn("First, rewritten.", doc.read_text())
            err = ur.edit_block(doc, "First paragraph.", "Again.", 8)  # stale copy
            self.assertIn("changed", err)
            self.assertEqual(doc.read_text(), "# Memo\n\nFirst, rewritten.\n\nSecond paragraph.\n")

    def test_upload_reviews_a_copy_and_returns_unified(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d)):
            page = ur.UploadServer()
            code, _, _ = page.handle("POST", "/api/upload/notes.docx", b"x")
            self.assertEqual(code, 400)
            with mock.patch.object(ur.subprocess, "Popen") as popen:
                popen.return_value.poll.return_value = None
                code, _, data = page.handle("POST", "/api/upload/my%20paper.pdf", b"%PDF-1.4")
                uid = json.loads(data)["id"]
                folder = Path(d) / "uploads" / uid
                self.assertEqual((folder / "upload" / "my paper.pdf").read_bytes(), b"%PDF-1.4")
                self.assertEqual(popen.call_args[0][0][-1], str(folder / "upload" / "my paper.pdf"))
                self.assertTrue(json.loads(page.handle("GET", "/api/job/" + uid, b"")[2])["running"])
                popen.return_value.poll.return_value = 0
                st = json.loads(page.handle("GET", "/api/job/" + uid, b"")[2])
                self.assertIn("did not finish", st["error"])
            unified = Path(d) / "run" / "unified.md"
            unified.parent.mkdir()
            unified.write_text("# my paper.pdf\n\n### 1. A finding\n")
            (folder / "stdout.log").write_text(f"{unified}\n")
            st = json.loads(page.handle("GET", "/api/job/" + uid, b"")[2])
            self.assertEqual(st["markdown"], unified.read_text())
            self.assertEqual(st["name"], "my paper.pdf")
            self.assertEqual(page.handle("GET", "/api/job/nope", b"")[0], 404)

    def test_open_reviews_the_chosen_file_in_place(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"), \
                mock.patch.object(ur.sys, "platform", "darwin"):
            draft, other = Path(d) / "draft.md", Path(d) / "other.md"
            draft.write_text("# Draft\n")
            other.write_text("# Other\n")
            page = ur.PageServer(draft)
            self.assertIn("<html", page.handle("GET", "/open", b"")[2])
            with mock.patch.object(ur, "choose_file", lambda start: (None, None)):
                self.assertEqual(json.loads(page.handle("POST", "/api/open", {})[2]), {"cancelled": True})
            with mock.patch.object(ur, "choose_file", lambda start: (str(Path(d) / "notes.docx"), None)):
                self.assertEqual(page.handle("POST", "/api/open", {})[0], 400)
            with mock.patch.object(ur, "choose_file", lambda start: (str(other), None)), \
                    mock.patch.object(ur.subprocess, "Popen") as popen:
                popen.return_value.poll.return_value = None
                st = json.loads(page.handle("POST", "/api/open", {})[2])
            self.assertEqual(popen.call_args[0][0][-1], str(other.resolve()))  # the original, not a copy
            self.assertEqual(popen.call_args[1]["cwd"], str(other.resolve().parent))
            job = json.loads(page.handle("GET", "/api/job/" + st["id"], b"")[2])
            self.assertTrue(job["running"])
            self.assertEqual(job["name"], "other.md")

    def test_review_markdown_puts_the_summary_under_the_title(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "unified.md").write_text("# draft.md, version 1\n\n## Critical\n\n### 1. A finding\n")
            self.assertEqual(ur.review_markdown(run), (run / "unified.md").read_text())
            (run / "summary.json").write_text(json.dumps({"themes": [
                {"theme": "Logic", "gist": "A step fails.", "findings": [1]}]}))
            self.assertEqual(ur.review_markdown(run), "# draft.md, version 1\n\n## Summary\n\nThe draft's main weaknesses are:\n\n"
                             "- **Logic**: A step fails. (1)\n\n## Critical\n\n### 1. A finding\n")

    def test_review_markdown_says_when_there_is_nothing_to_list(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "unified.md").write_text("# draft.md\n\n## Rejected by vote\n\n- A point\n")
            (run / "summary.json").write_text(json.dumps({"themes": []}))
            self.assertEqual(ur.review_markdown(run), "# draft.md\n\n## Summary\n\nNo new findings on this version.\n\n"
                             "## Rejected by vote\n\n- A point\n")

    def test_review_markdown_lists_each_themes_findings_after_it(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "unified.md").write_text("# draft.md\n\n## Critical\n\n" + "".join(f"### {n}. F\n\n" for n in range(1, 6)))
            (run / "summary.json").write_text(json.dumps({"themes": [
                {"theme": "Logic", "gist": "Steps fail.", "findings": [3, 1, 9]},
                {"theme": "Style", "gist": "", "findings": [1, 4]},
                {"theme": "Gone", "gist": "Only repeats.", "findings": [3]}]}))
            block = ur.review_markdown(run).split("## Critical")[0]
            self.assertEqual(block, "# draft.md\n\n## Summary\n\nThe draft's main weaknesses are:\n\n- **Logic**: Steps fail. (1, 3)\n"
                             "- **Style** (4)\n- **Other** (2, 5)\n\n")

    def test_review_prompt_proposes_text_and_keeps_slots_for_citations(self):
        prompt = ur.review_prompt("draft", "", "rules")
        self.assertIn("propose that content as the 🟢 text", prompt)
        self.assertIn("{{citation: Author, year}}", prompt)

    def test_dropped_file_is_found_by_name_and_bytes(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"), \
                mock.patch.object(ur.sys, "platform", "darwin"):
            a, b, c = Path(d) / "a" / "memo.md", Path(d) / "b" / "memo.md", Path(d) / "c" / "memo.md"
            for f, text in ((a, "# Memo\n"), (b, "# Other memo\n"), (c, "# Memo\n")):
                f.parent.mkdir()
                f.write_text(text)
            hits = [str(a), str(b)]
            spotlight = lambda cmd, **k: SimpleNamespace(stdout="\n".join(hits) + "\n", returncode=0)
            with mock.patch.object(ur.subprocess, "run", spotlight):
                self.assertEqual(ur.find_original("memo.md", b"# Memo\n"), [a.resolve()])  # b differs
                page = ur.PageServer(Path(d) / "draft.md")
                with mock.patch.object(ur.subprocess, "Popen") as popen:
                    st = json.loads(page.handle("POST", "/api/locate/memo.md", b"# Memo\n")[2])
                self.assertEqual(popen.call_args[0][0][-1], str(a.resolve()))  # the original
                self.assertEqual(st["name"], "memo.md")
                self.assertEqual(page.handle("POST", "/api/locate/memo.md", b"# Nowhere\n")[0], 404)
                hits.append(str(c))  # two identical copies: refuse rather than guess
                code, _, data = page.handle("POST", "/api/locate/memo.md", b"# Memo\n")
                self.assertEqual(code, 404)
                self.assertIn("2 identical copies", json.loads(data)["error"])

if __name__ == "__main__":
    unittest.main()
