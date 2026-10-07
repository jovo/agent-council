"""Tests for unified-review. Run: python3 -m unittest discover tests"""
import json
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

    def group(self, title, quote, where, pos, contested=False, rejected=False):
        return {"rep": {"title": title, "quote": quote, "body": "Point."}, "where": where, "pos": pos,
                "severity": "Substantive", "frac": 1, "score": 2, "n_votes": 2, "raised_by": ["claude"],
                "votes": {"claude": vote("agree"), "gpt": vote("disagree" if contested else "agree")},
                "contested": contested, "rejected": rejected}

    def test_layout_line_numbers_and_labels(self):
        draft_norm = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        pos = ur.position(draft_norm, "Rome was founded in 1066.")
        self.results([self.group("Late finding", "More text here.", "draft", ur.position(draft_norm, "More text here.")),
                      self.group("Overall", "", "overview", 0),
                      self.group("Date", "Rome was founded in 1066.", "draft", pos, contested=True)])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        order = [md.index(t) for t in ("## Overview", "### 1. Overall", "## Intro", "### 2. Date", "## Body", "### 3. Late finding")]
        self.assertEqual(order, sorted(order))
        self.assertIn("### 2. Date (Substantive, contested)", md)
        self.assertIn("draft.md, line 4:", md)  # not line 3: the off-by-one regression
        self.assertNotIn("Warning", md)

    def test_failures_and_warning(self):
        self.results([], reviewers=("claude",), voters=("claude", "gpt"),
                     failures=[{"stage": "review", "model": "gpt", "reason": "timed out after 900 s after one retry"}])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        self.assertIn("*Failed: GPT review (timed out after 900 s after one retry).*", md)
        self.assertIn("**Warning: fewer than two models reviewed.", md)



if __name__ == "__main__":
    unittest.main()
