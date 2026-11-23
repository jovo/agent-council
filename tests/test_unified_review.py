"""Tests for unified-review. Run: python3 -m unittest discover tests"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
import urllib.parse
import zipfile
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parent.parent


def tree_metadata(root):
    """Metadata for the real state directories, used as a test guard."""
    root = Path(root)
    if not root.exists():
        return None
    paths = [root, *sorted(root.rglob("*"))]
    state = {}
    for path in paths:
        try:
            info = path.stat()
        except FileNotFoundError:
            continue
        state[str(path.relative_to(root))] = (info.st_size, info.st_mtime_ns)
    return state


def changed_paths(before, after):
    before, after = before or {}, after or {}
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


ORIGINAL_HOME = os.environ.get("HOME")
ORIGINAL_RUNS = os.environ.get("UNIFIED_REVIEW_RUNS")
ORIGINAL_MODEL_BINS = {name: os.environ.get(name) for name in ("CLAUDE_BIN", "CODEX_BIN", "CURSOR_BIN")}
REAL_HOME = Path(ORIGINAL_HOME) if ORIGINAL_HOME else Path.home()
REAL_RUNS_DIR = Path(ORIGINAL_RUNS) if ORIGINAL_RUNS else REAL_HOME / ".local/share/unified-review/runs"
REAL_STATE_DIR = REAL_HOME / ".local/state/unified-review"
REAL_RUNS_STATE = tree_metadata(REAL_RUNS_DIR)
REAL_STATE_STATE = tree_metadata(REAL_STATE_DIR)
TEST_STATE = tempfile.TemporaryDirectory()
MODEL_STUB = Path(TEST_STATE.name) / "model-stub"
MODEL_STUB.write_text("#!/bin/sh\nexit 1\n")
MODEL_STUB.chmod(0o700)
os.environ["HOME"] = TEST_STATE.name
os.environ["UNIFIED_REVIEW_RUNS"] = str(Path(TEST_STATE.name) / "runs")
for name in ORIGINAL_MODEL_BINS:
    os.environ[name] = str(MODEL_STUB)

ur = SourceFileLoader("unified_review", str(REPO / "bin" / "unified-review")).load_module()


def tearDownModule():
    try:
        runs_changed = changed_paths(REAL_RUNS_STATE, tree_metadata(REAL_RUNS_DIR))
        state_changed = changed_paths(REAL_STATE_STATE, tree_metadata(REAL_STATE_DIR))
        assert not runs_changed, "tests changed the real run directory: " + ", ".join(runs_changed)
        assert not state_changed, "tests changed the real state directory: " + ", ".join(state_changed)
    finally:
        if ORIGINAL_HOME is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = ORIGINAL_HOME
        if ORIGINAL_RUNS is None:
            os.environ.pop("UNIFIED_REVIEW_RUNS", None)
        else:
            os.environ["UNIFIED_REVIEW_RUNS"] = ORIGINAL_RUNS
        for name, value in ORIGINAL_MODEL_BINS.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        TEST_STATE.cleanup()

REVIEW = """Some preamble the parser should ignore.

=== FINDING
severity: Major
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
severity: Minor
title: Missing separator, so this one is skipped
"""

VOTES = """A1 | agree | Major | same:none | Wrong date.
**A2** | Partial | polish | same: none | Minor.
- B1 | disagree | Minor | same:A1 | Not wrong.
B2 | maybe | Polish | same:none | Not a valid vote word.
"""


def finding(fid, quote="", severity="Minor", pos=0):
    return {"id": fid, "quote": quote, "severity": severity, "title": fid, "body": fid, "pos": pos}


def vote(v, same="NONE", severity="Minor"):
    return {"vote": v, "severity": severity, "same": same, "reason": v}


class Parsing(unittest.TestCase):
    def test_request_bodies_have_route_specific_limits(self):
        self.assertEqual(ur.read_request_body({"Content-Length": "2"}, io.BytesIO(b"{}"), "POST", "/api/update"), b"{}")
        with self.assertRaisesRegex(ur.RequestBodyError, "Content-Length"):
            ur.read_request_body({}, io.BytesIO(), "POST", "/api/update")
        with self.assertRaisesRegex(ur.RequestBodyError, "invalid"):
            ur.read_request_body({"Content-Length": "-1"}, io.BytesIO(), "POST", "/api/update")
        with self.assertRaisesRegex(ur.RequestBodyError, "1 MiB"):
            ur.read_request_body({"Content-Length": str(ur.JSON_BODY_LIMIT + 1)}, io.BytesIO(), "POST", "/api/update")
        self.assertEqual(ur.read_request_body({"Content-Length": str(ur.JSON_BODY_LIMIT + 1)}, io.BytesIO(b"x"), "POST", "/api/upload/memo.md"), b"x")

    def test_runs_for_reuses_unchanged_results_metadata(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d)):
            ur.RUN_METADATA.clear()
            draft = Path(d) / "memo.md"
            result = ur.RUNS_DIR / "run" / "results.json"
            result.parent.mkdir()
            result.write_text(json.dumps({"files": [str(draft)]}))
            with mock.patch.object(ur.json, "loads", wraps=ur.json.loads) as loads:
                self.assertEqual(ur.runs_for(draft), [result.parent])
                self.assertEqual(ur.runs_for(draft), [result.parent])
                time.sleep(0.01)  # ensure a distinct mtime on filesystems with coarse clocks
                result.write_text(json.dumps({"files": [str(Path(d) / "other.md")]}))
                self.assertEqual(ur.runs_for(draft), [])
            self.assertEqual(loads.call_count, 2)

    def test_parse_findings(self):
        fs = ur.parse_findings(REVIEW)
        self.assertEqual([f["title"] for f in fs], ["Date is wrong", "Wordy opener"])
        self.assertEqual(fs[0]["severity"], "Major")
        self.assertEqual(fs[1]["severity"], "Nitpick")
        self.assertEqual(fs[0]["quote"], "Rome was founded in 1066.")
        self.assertEqual(fs[1]["quote"], "")
        self.assertIn("753 BC", fs[0]["body"])

    def test_parse_question_form(self):
        fs = ur.parse_findings("=== FINDING\nseverity: Minor\nkind: clarity\nform: question\n"
                               "title: Which gripper\nquote: a robot arm\n---\nTwo-finger or three-finger?\n")
        self.assertEqual(fs[0]["form"], "question")
        self.assertEqual(ur.parse_findings(REVIEW)[0]["form"], "edit")  # no form line means an edit

    def test_prompts_allow_questions(self):
        self.assertIn("form: edit | question", ur.review_prompt("draft", "", "rules"))
        self.assertIn("For a question finding", ur.VOTE)

    def test_parse_votes_is_tolerant_but_strict_on_vote_words(self):
        v = ur.parse_votes(VOTES)
        self.assertEqual(set(v), {"A1", "A2", "B1"})
        self.assertEqual(v["A2"]["vote"], "partial")
        self.assertEqual(v["A2"]["severity"], "Nitpick")
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
        g = ur.score_group([finding("A1")], {"claude": {"A1": vote("agree", severity="Major")},
                                             "gpt": {"A1": vote("disagree", severity="Polish")}, "gemini": {}},
                           voters, owner)
        self.assertTrue(g["rejected"])
        self.assertEqual(g["severity"], "Nitpick")
        self.assertNotIn("claude", g["votes"])  # a model's vote on its own finding is ignored
        self.assertEqual(ur.vote_tag(g), "No majority")

    def test_two_models_must_back_a_finding(self):
        owner = {"A": "claude", "B": "gpt", "C": "gemini"}
        voters = ["claude", "gpt", "gemini"]
        backed = ur.score_group([finding("A1")], {"gpt": {"A1": vote("partial")}, "gemini": {"A1": vote("disagree")}},
                                voters, owner)
        self.assertFalse(backed["rejected"])  # gpt's partial is a second backer, despite gemini
        alone = ur.score_group([finding("A1")], {"gpt": {"A1": vote("disagree")}, "gemini": {"A1": vote("disagree")}},
                               voters, owner)
        self.assertTrue(alone["rejected"])
        pair = ur.score_group([finding("A1"), finding("B1")], {"gemini": {"A1": vote("disagree"), "B1": vote("disagree")}},
                              voters, owner)
        self.assertFalse(pair["rejected"])  # two models raised the same point

    def test_score_group_takes_median_severity_and_raisers(self):
        owner = {"A": "claude", "B": "gpt"}
        g = ur.score_group([finding("A1"), finding("B1")],
                           {"claude": {"A1": vote("agree", severity="Major")},
                            "gpt": {"A1": vote("agree", severity="Polish")},
                            "gemini": {"A1": vote("agree", severity="Minor")}},
                           ["claude", "gpt", "gemini"], owner)
        self.assertEqual(g["severity"], "Minor")
        self.assertEqual(g["raised_by"], ["claude", "gpt"])

    def test_a_diff_that_rewrites_the_quote_beats_one_that_only_adds(self):
        owner = {"A": "claude", "B": "gpt", "C": "gemini"}
        voters = ["claude", "gpt", "gemini"]
        quote = "The marketplace gives contributors a local route to the cortex."
        adds = finding("B1", quote)
        adds["body"] = f"Local conflicts with cloud use.\n\n{quote} **🟢 Contributors authorize each transfer.**"
        rewrites = finding("C1", quote)
        rewrites["body"] = "Local conflicts with cloud use.\n\nThe marketplace gives contributors ~~a local~~ 🟢 **an authorized** route to the cortex."
        # GPT's insert-only diff has the better votes, but it keeps the sentence the finding says is wrong.
        votes = {"claude": {"B1": vote("agree"), "C1": vote("partial")},
                 "gemini": {"B1": vote("agree")}, "gpt": {"C1": vote("partial")}}
        g = ur.score_group([adds, rewrites], votes, voters, owner)
        self.assertEqual(g["rep"]["id"], "C1")
        # With no rewriting diff in the group, an insert-only diff still stands: it may fill an omission.
        alone = ur.score_group([dict(adds)], votes, voters, owner)
        self.assertEqual(alone["rep"]["id"], "B1")



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
        ur.LEFT_OFF.clear()
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
                mock.patch.dict(ur.runtime.CHILD_ENV, {"CODEX_API_KEY": "k", "CURSOR_API_KEY": "k"}):
            self.assertEqual(ur.preflight(["gpt", "gemini"]), ["gpt", "gemini"])
        self.assertEqual(ur.FAILURES, [])

    def choose(self, panel, missing=(), logged_out=()):
        checked = []

        def fake_preflight(ms):
            checked.extend(ms)
            for m in ms:
                if m in logged_out:
                    ur.fail("preflight", m, "not logged in")
            return [m for m in ms if m not in logged_out]
        ur.FAILURES.clear()
        ur.LEFT_OFF.clear()
        with mock.patch.object(ur, "available", lambda m: m not in missing), \
                mock.patch.object(ur, "preflight", fake_preflight), mock.patch.object(ur.runtime, "log", lambda *a: None):
            return ur.choose_panel(panel), checked

    def test_a_logged_out_panelist_is_not_tried_again_as_its_own_stand_in(self):
        panel, checked = self.choose(["gpt", "gemini", "argon"], logged_out=("gpt",))
        self.assertEqual(panel, ["gemini", "argon", "grok"])
        self.assertEqual(checked.count("gpt"), 1)
        self.assertEqual([f["model"] for f in ur.FAILURES], ["gpt"])

    def test_a_mediated_panel_leaves_off_the_mediators_lab(self):
        panel, checked = self.choose(["claude", "gpt", "gemini"])
        self.assertEqual(panel, ["gpt", "gemini"])  # Claude Opus mediates, so Claude Sonnet does not review
        self.assertNotIn("claude", checked)
        panel, _ = self.choose(["claude:opus", "gpt", "argon"])
        self.assertEqual(panel, ["gpt", "argon"])
        self.assertEqual([x["model"] for x in ur.LEFT_OFF], ["claude:opus"])  # recorded for the review

    def test_the_review_says_which_reviewers_were_left_off(self):
        ur.LEFT_OFF.clear()
        r = {"labels": {"claude": "Claude Sonnet"}, "left_off": [{"model": "claude", "mediator": "Claude Opus"}]}
        self.assertEqual(ur.left_off_line(r), "Left off as a reviewer: Claude Sonnet. Claude Opus mediates, "
                         "and a lab does not settle disputes over its own findings.")
        self.assertEqual(ur.left_off_line({"labels": {}}), "")

    def test_two_models_in_all_are_refused(self):
        with self.assertRaises(SystemExit):
            self.choose(["claude", "gpt"])  # Claude off, GPT alone, plus the mediator: two models
        self.assertEqual(self.choose(["claude"])[0], ["claude"])  # one model reviews alone

    def test_a_mediated_panel_skips_claude_as_a_stand_in(self):
        panel, checked = self.choose(["gpt", "argon"], logged_out=("gpt",))
        self.assertEqual(panel, ["argon", "grok"])
        self.assertNotIn("claude", checked)

    def test_a_stand_in_replaces_a_panelist_whose_cli_is_missing(self):
        panel, _ = self.choose(["gpt"], missing=("gpt",))
        self.assertEqual(panel, ["claude"])
        panel, _ = self.choose(["argon", "gpt", "gemini"], missing=("gpt",))
        self.assertEqual(panel, ["argon", "gemini", "grok"])

    def test_no_panel_when_nothing_is_available(self):
        with self.assertRaises(SystemExit):
            self.choose(["gpt"], missing=("gpt", "claude", "grok"))


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

    def group(self, title, quote, where, pos, contested=False, rejected=False, severity="Minor"):
        return {"rep": {"title": title, "quote": quote, "body": "Point."}, "where": where, "pos": pos,
                "severity": severity, "frac": 1, "score": 2, "n_votes": 2, "raised_by": ["claude"],
                "votes": {"claude": vote("agree"), "gpt": vote("disagree" if contested else "agree")},
                "contested": contested, "rejected": rejected}

    def test_question_finding_is_labeled(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        q = "Rome was founded in 1066."
        self.results([{**self.group("Which founding", q, "draft", ur.position(dn, q)), "form": "question"}])
        self.assertIn("### 1. Which founding (question)", ur.review_markdown(self.tmp))

    def test_summary_is_logic_first_then_theme_titles(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        g = lambda title, q, kind: {**self.group(title, q, "draft", ur.position(dn, q)), "kind": kind}
        self.results([g("Step fails", "First line.", "logic"), g("Vague term", "Rome was founded in 1066.", "clarity"),
                      g("Odd word", "More text here.", "style")])
        (self.tmp / "summary.json").write_text(json.dumps({"themes": [
            {"theme": "Wording", "gist": "Long gist sentence.", "findings": [1, 2, 3]}]}))
        block = ur.review_markdown(self.tmp).split("## Minor")[0]
        self.assertIn("## Summary (3 findings)\n\n- **Logical flaws (1 finding):**\n  - Step fails (1)\n- **Wording (2 findings):**\n  - Vague term (2)\n  - Odd word (3)\n", block)
        self.assertNotIn("Long gist", block)

    def test_summary_says_when_there_are_no_logic_flaws(self):
        self.results([{**self.group("Odd word", "More text here.", "draft", 0), "kind": "style"}])
        (self.tmp / "summary.json").write_text(json.dumps({"themes": []}))
        self.assertIn("- **Logical flaws:** none found.\n", ur.review_markdown(self.tmp))

    def test_logic_flaws_come_first(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        g = lambda title, q, kind, sev: {**self.group(title, q, "draft", ur.position(dn, q), severity=sev), "kind": kind}
        self.results([g("Major fact", "First line.", "evidence", "Major"),
                      g("Leap", "More text here.", "logic", "Minor"),
                      g("Broken step", "Rome was founded in 1066.", "logic", "Major")])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        order = [md.index(x) for x in ("## Logical flaws", "### 1. Broken step (Major)", "### 2. Leap (Minor)",
                                       "## Major", "### 3. Major fact (evidence)")]
        self.assertEqual(order, sorted(order))

    def test_votes_sit_beside_the_title(self):
        self.results([self.group("Date", "Rome was founded in 1066.", "draft", 0, contested=True)],
                     reviewers=("claude", "gemini"), voters=("claude", "gpt"))
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        self.assertIn("### 1. Date (contested) ✳ ✗֍\n", md)  # Claude flagged it, GPT disagreed
        self.assertNotIn("Votes:", md)

    def test_layout_severity_then_draft_order(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        at = lambda q: ur.position(dn, q)
        self.results([self.group("Late polish", "More text here.", "draft", at("More text here."), severity="Polish"),
                      self.group("Late substantive", "More text here.", "draft", at("More text here.")),
                      self.group("Overall", "", "overview", 0),
                      self.group("Date", "Rome was founded in 1066.", "draft", at("Rome was founded in 1066."),
                                 contested=True, severity="Major"),
                      self.group("Early substantive", "First line.", "draft", at("First line."))])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        order = [md.index(t) for t in ("## Major", "### 1. Date (contested)", "## Minor", "### 2. Overall",
                                       "### 3. Early substantive", "### 4. Late substantive", "## Nitpicks",
                                       "- **5.** Late polish")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("draft.md, line", md)  # no section, file, or line for a finding
        self.assertIn("*Whole draft*", md)
        self.assertNotIn("Warning", md)

    def test_changes_place_through_markup_and_reviewer_slips(self):
        def apply(text, body, quote=""):
            _, why, edits = ur.placed_diff(text, body, quote)
            if not edits:
                return why
            for a, b, r in sorted(edits, reverse=True):
                text = text[:a] + r + text[b:]
            return text
        # The reviewer quotes the text as it reads; the draft has bold, underline, and an escape.
        self.assertEqual(apply("staining depicted in **c**. FLAG", "Change c to f.\n\nstaining depicted in ~~c~~ **🟢 f**."),
                         "staining depicted in **f**. FLAG")
        self.assertEqual(apply("the use of a moderate<u>-low</u> affinity scFv",
                               "Reword.\n\nthe use of a ~~moderate-low affinity~~ **🟢 moderately low-affinity** scFv"),
                         "the use of a moderately low-affinity scFv")  # the cut underline goes, no tag left open
        self.assertEqual(apply("<u>He was **very** happy</u> today.", "Reword.\n\nHe was ~~very~~ **🟢 quite** happy today."),
                         "<u>He was **quite** happy</u> today.")
        self.assertEqual(apply("from DSMZ (ACC \\#777) RPMI", "Fix.\n\nfrom DSMZ (ACC ~~#777~~ **🟢 #778**) RPMI"),
                         "from DSMZ (ACC \\#778) RPMI")  # only the changed digit: the escape stays
        # 🟢 without bold: the addition ends where the draft's own text resumes, and is never added twice.
        t = "at a reduced efficiently, given a high enough affinity<sup>64</sup>. This suggested"
        self.assertEqual(apply(t, "Fix.\n\nat a reduced ~~efficiently~~🟢 efficiency, given a high enough affinity<sup>64</sup>."),
                         "at a reduced efficiency, given a high enough affinity<sup>64</sup>. This suggested")
        self.assertEqual(apply("depicted in **c**. FLAG", "Fix.\n\ndepicted in ~~c~~🟢 f."), "depicted in **f**. FLAG")
        # Striking all a superscript holds and adding after it leaves no empty <sup></sup>.
        _, _, e = ur.placed_diff("(BB7.2, 162 nM<sup>66</sup>) may", "Cite.\n\n(BB7.2, 162 nM<sup>~~66~~</sup>**🟢 {{citation: Author, year}}**",
                                 "", slots=True)
        a, b, r = e[0]
        self.assertEqual("(BB7.2, 162 nM<sup>66</sup>) may"[:a] + r + "(BB7.2, 162 nM<sup>66</sup>) may"[b:],
                         "(BB7.2, 162 nM{{citation: Author, year}}) may")
        self.assertEqual(apply("see ref<sup>12</sup> here", "Drop it.\n\nsee ref~~12~~ here"), "see ref here")
        # An addition that would repeat what follows with a word changed is refused, not guessed.
        self.assertEqual(apply("as the starting point and add potency as required. Next",
                               "Fix.\n\nas the starting point 🟢 to add potency as required."), ur.MALFORMED)

    def test_diff_in_the_first_paragraph_still_applies(self):
        text = "Intro.\n\nThe method is only one possible solution enhancing potency. Done.\n"
        body = "Add the missing word. The method is only one possible solution **🟢 for** enhancing potency."
        old, new, edits = ur.placed_diff(text, body, "only one possible solution enhancing")
        self.assertEqual((old, new), ("The method is only one possible solution enhancing potency.",
                                      "The method is only one possible solution for enhancing potency."))
        self.assertTrue(edits)
        self.assertIsNone(ur.placed_diff(text, "Which source says so?", "The method")[0])  # a body with no diff

    def test_a_question_with_a_revision_places_it(self):
        text = "Intro.\n\nThe method is fast. Done.\n"
        body = ("Fast compared with what? Readings: wall-clock or samples. I assumed wall-clock.\n\n"
                "The method is fast 🟢 **in wall-clock time**.")
        old, new, _ = ur.placed_diff(text, body, "The method is fast.")
        self.assertEqual((old, new), ("The method is fast.", "The method is fast in wall-clock time."))

    def test_nitpicks_typos_and_checks_are_one_list(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        q = "Rome was founded in 1066."
        nit = self.group("Missing word", q, "draft", ur.position(dn, q), severity="Nitpick")
        typo = self.group("Misspelling", q, "draft", ur.position(dn, q), severity="Nitpick")
        typo["rep"]["body"] = "Fix the spelling.\n\nRome was ~~fonded~~ **🟢 founded** in 1066."
        self.results([nit, typo])
        rj = json.loads((self.tmp / "results.json").read_text())
        rj["checks"] = [{"id": "M1", "line": 3, "pos": 0, "what": '"anti-tumor" (4×) and "antitumor" (2×) are both used.'}]
        (self.tmp / "results.json").write_text(json.dumps(rj))
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        self.assertNotIn("## Typos", md)
        self.assertNotIn("## Checks", md)
        nits = md[md.index("## Nitpicks"):]
        self.assertIn("Misspelling", nits)
        self.assertIn("(typo)", nits)
        self.assertIn('- **M1.** "anti-tumor" (4×) and "antitumor" (2×) are both used. (*line 3*), found by the script', nits)

    def test_nitpick_shows_where_and_the_change_without_votes(self):
        dn = ur.norm("===== draft.md =====\n" + self.doc.read_text())
        q = "Rome was founded in 1066."
        nit = self.group("Missing word", q, "draft", ur.position(dn, q), severity="Nitpick")
        nit["rep"]["body"] = "Add the year's era. Rome was founded in ~~1066~~ **🟢 753 BC**."  # the diff in the first paragraph
        ask = self.group("Why this date", q, "draft", ur.position(dn, q), severity="Nitpick")
        ask["rep"]["body"] = "Which source gives this date?"
        self.results([nit, ask])
        ur.render(self.tmp)
        md = (self.tmp / "unified.md").read_text()
        self.assertIn("- **1.** Missing word (*", md)
        self.assertIn("): Add the year's era. Rome was founded in ~~1066~~ **🟢 753 BC**.\n", md)
        self.assertIn("- **2.** Why this date (*", md)
        self.assertIn("): Which source gives this date?", md)
        nits = md[md.index("## Nitpicks"):]
        self.assertFalse(re.search("[✓✗✳֍✦]", nits))  # no votes on a nitpick

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
        with mock.patch.object(ur.sys, "platform", "darwin"), \
             mock.patch.dict(ur.os.environ, env, clear=True), \
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
            mod = SourceFileLoader("ur_env", str(REPO / "bin" / "unified_review_runtime.py")).load_module()
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
             "where": "draft", "pos": 0, "severity": "Major", "frac": 1, "rejected": False, "members": ["A1"]}
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

    def run_review(self, panel, fails=(), draft_text="The sky is green today. Grass grows slowly.", reply=None,
                   missing=(), failed_before=()):
        prompts = {}

        def fake_call(m, prompt, out, workdir, web=False, stage=""):
            prompts.setdefault(stage, {})[m] = prompt
            if m in fails or (stage, m) in fails:
                ur.fail(stage, m, "fake failure")
                return None
            if stage == "review" and reply is not None:
                return reply
            if stage == "review":
                return (f"=== FINDING\nseverity: Minor\ntitle: Sky color by {m}\n"
                        "quote: The sky is green today.\n---\nThe sky is blue.")
            ids = re.findall(r"^\[([A-H]\d+)\]", prompt, re.M)
            return "\n".join(f"{i} | agree | Minor | same:none | fine" for i in ids)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            f = d / "memo.md"
            f.write_text(draft_text)
            out = d / "run"
            out.mkdir()
            draft = f"===== memo.md =====\n{draft_text}"
            ur.FAILURES.clear()
            ur.LEFT_OFF.clear()
            for m in failed_before:
                ur.FAILURES.append({"stage": "preflight", "model": m, "reason": "not logged in"})
            with mock.patch.object(ur, "call", fake_call), mock.patch.object(ur, "RUNS_DIR", d), \
                 mock.patch.object(ur, "available", lambda m: m not in missing), \
                 mock.patch.object(ur, "LAST_RUN", d / "last-run"), \
                 mock.patch.object(ur, "open_file", lambda p: None), mock.patch.object(ur.runtime, "log", lambda *a: None):
                ur.foreground([f], draft, panel, "", "rules", out, d, False, [])
            return prompts, json.loads((out / "results.json").read_text()), (out / "unified.md").read_text()

    def test_voters_do_not_vote_on_their_own_findings(self):
        prompts, _, _ = self.run_review(["claude", "gpt", "gemini"])
        r = None
        for m, p in prompts["vote"].items():
            mine = [l for l in p.split("<your_own_findings>")[1].splitlines() if l.startswith("[")]
            voted = [l for l in p.split("<your_own_findings>")[0].split("<draft>")[0].splitlines() if l.startswith("[")]
            self.assertEqual(len(mine), 1, m)
            self.assertNotIn(mine[0].split("]")[0], " ".join(voted), m)

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

    def test_fact_check_keeps_three_checkers_for_a_solo_review(self):
        self.assertEqual(ur.factcheck_panel(["argon"]), ["claude", "gpt", "gemini"])
        self.assertEqual(ur.factcheck_panel(["claude", "gpt"]), ["claude", "gpt"])

    def test_solo_groups_are_marked_solo(self):
        _, r, _ = self.run_review(["argon"])
        self.assertTrue(all(g["solo"] for g in r["groups"]))
        _, r, _ = self.run_review(["claude", "gpt", "gemini"])
        self.assertFalse(any(g["solo"] for g in r["groups"]))

    def test_edit_review_with_one_reviewer_skips_the_vote(self):
        stages = []

        def fake_call(m, prompt, out, workdir, web=False, stage=""):
            stages.append(stage)
            return ("=== FINDING\nseverity: Minor\ntitle: Sky color\n"
                    "quote: The sky is green today.\n---\nThe sky is ~~green~~ 🟢 **blue** today.")

        real = ur.threading.Thread

        def Now(*a, **kw):  # run review_passage's daemon thread in place, others as usual
            if kw.get("daemon"):
                return types.SimpleNamespace(start=kw["target"])
            return real(*a, **kw)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            f = d / "memo.md"
            f.write_text("The sky is green today.\n")
            run = d / "run"
            run.mkdir()
            (run / "results.json").write_text(json.dumps({"groups": [], "labels": {}}))
            with mock.patch.object(ur, "call", fake_call), mock.patch.object(ur, "page_panel", lambda p: ["argon"]), \
                 mock.patch.object(ur, "load_rules", lambda r: ("rules", "x")), mock.patch.object(ur, "RUNS_DIR", d), \
                 mock.patch.object(ur.threading, "Thread", Now):
                ur.review_passage(str(f), run, "The sky is green today.")
            status = json.loads((run / "edit-review.json").read_text())
            self.assertEqual(status["status"], "done", status)
            self.assertEqual(status["added"], 1)
            self.assertNotIn("edit vote", stages)

    def test_stand_ins_are_claude_then_grok(self):
        self.assertEqual(ur.STANDINS, ["claude", "grok"])

    def test_claude_then_grok_stand_in_for_a_failed_solo_reviewer(self):
        _, r, md = self.run_review(["gpt"], fails=("gpt",))
        self.assertEqual(r["reviewers_ok"], ["claude"])
        self.assertIn("Failed: GPT-5.6 Luna", md)
        _, r, _ = self.run_review(["gpt"], fails=("gpt", "claude"))
        self.assertEqual(r["reviewers_ok"], ["grok"])

    def test_a_missing_or_already_failed_stand_in_is_skipped(self):
        prompts, r, _ = self.run_review(["gpt"], fails=("gpt",), missing=("claude",))
        self.assertEqual(r["reviewers_ok"], ["grok"])
        self.assertNotIn("claude", prompts["review"])
        prompts, r, md = self.run_review(["gpt", "gemini", "grok"], fails=("gpt",), failed_before=("claude",))
        self.assertNotIn("claude", prompts["review"])
        self.assertEqual(r["labels"]["claude"], ur.label("claude"))
        self.assertIn(f"Failed: {ur.label('claude')}", md)

    def test_grok_not_claude_stands_in_for_a_failed_voter(self):
        prompts, r, _ = self.run_review(["gpt", "gemini"], fails=(("vote", "gpt"),))
        self.assertEqual(sorted(r["voters"]), ["gemini", "grok"])  # Claude mediates, so it does not vote
        self.assertNotIn("claude", prompts.get("vote", {}))

    def test_one_reviewer_skips_the_vote_and_keeps_its_findings(self):
        prompts, r, md = self.run_review(["argon"])
        self.assertNotIn("vote", prompts)
        self.assertEqual(r["reviewers_ok"], ["argon"])
        self.assertEqual(len([g for g in r["groups"] if not g["rejected"]]), 1)
        self.assertIn("Reviewed by Gemini 4 Argon Medium alone, with no vote.", md)
        self.assertNotIn("Warning", md)

    def test_a_failed_solo_reviewer_still_warns(self):
        _, r, md = self.run_review(["argon"], fails=("argon",))
        self.assertEqual(r["reviewers_ok"], ["claude"])
        self.assertIn("Failed: Gemini 4 Argon Medium", md)

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
        self.assertEqual([sev for _, sev, _, _ in ur.ordered_findings(r)], ["Nitpick", "Typo"])


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

    def test_double_spaces_give_each_span_for_the_page_to_mark(self):
        text = "One sentence.  Two words  apart.\n\nKeep `x  y` in code."
        with mock.patch.object(ur, "BIB", Path("/nonexistent.bib")):
            out = ur.checks(text, Path("/tmp/memo.md"))
        self.assertEqual(out[0]["spans"], [[13, 15], [24, 26]])  # not the spaces inside code
        self.assertEqual([text[a:b] for a, b in out[0]["spans"]], ["  ", "  "])

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
        self.assertEqual(since, {"resolved": [{"n": None, "title": "Missing baseline"}], "dropped": []})

    def test_unchanged_passage_not_raised_again_is_dropped(self):
        prev = [{"key": "Kaaaaaa", "title": "Vague term", "quote": "many things happen here", "seen": 1}]
        rejected = self.group("Vague term", "many things happen here", rejected=True)
        since = ur.carry_over([rejected], prev, ur.norm("many things happen here."))
        self.assertEqual(since, {"resolved": [], "dropped": [{"n": None, "title": "Vague term"}]})

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

    def test_bib_key_reads_doi_from_bib(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "refs.bib").write_text("@article{Strick09,\n  doi = {10.1146/annurev.neuro.31.060407.125606},\n}\n")
            with mock.patch.object(ur, "BIB", Path(d) / "refs.bib"):
                self.assertEqual(ur.bib_key("10.1146/ANNUREV.NEURO.31.060407.125606"), ("Strick09", None))
                key, err = ur.bib_key("10.1038/nature12345")
        self.assertIsNone(key)
        self.assertIn("Add it in Paperpile", err)


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
        (run / "results.json").write_text(json.dumps({"files": [], "reviewers_ok": ["claude"]}))
        (run / "unified.md").write_text("## Major\n\n### 1. F1 is never defined\n")
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

    def test_key_claim_is_one_sentence_from_the_draft(self):
        run = Path(tempfile.mkdtemp())
        draft = run / "memo.md"
        draft.write_text("Sparse coding predicts V1 receptive fields.\n")
        (run / "results.json").write_text(json.dumps({"files": [str(draft)], "reviewers_ok": ["claude"]}))
        (run / "unified.md").write_text("## Major\n\n### 1. F1 is never defined\n")
        calls = []
        def call(name, prompt, out, workdir, stage=""):
            calls.append(prompt)
            return ('{"claim": "Sparse coding predicts V1 receptive fields. It also predicts V2.", '
                    '"themes": [{"theme": "Definitions", "gist": "F1 is undefined.", "findings": [1]}]}')
        with mock.patch.object(ur, "call", call), mock.patch.object(ur, "load_rules", lambda p: ("rules", "")):
            ur.summary_state(run)
            for _ in range(100):
                if (run / "summary.json").exists():
                    break
                time.sleep(0.01)
            st = ur.summary_state(run)
        self.assertEqual(st["claim"], "Sparse coding predicts V1 receptive fields.")
        self.assertIn("<draft>\nSparse coding predicts V1 receptive fields.", calls[0])
        shutil.rmtree(run)

    def test_no_recorded_reviewer_fails_without_a_call(self):
        run = Path(tempfile.mkdtemp())
        (run / "unified.md").write_text("## Major\n\n### 1. F1 is never defined\n")
        calls = []
        def call(name, prompt, out, workdir, stage=""):
            calls.append(name)
            return "{}"
        with mock.patch.object(ur, "call", call), mock.patch.object(ur, "load_rules", lambda p: ("rules", "")):
            self.assertEqual(ur.summary_state(run), {"status": "pending"})
            for _ in range(100):
                if (run / "summary.failed").exists():
                    break
                time.sleep(0.01)
            st = ur.summary_state(run)
        self.assertEqual(st["status"], "failed")
        self.assertIn("no reviewer", st["reason"])
        self.assertEqual(calls, [])
        shutil.rmtree(run)

    def test_summary_uses_the_runs_reviewer(self):
        run = Path(tempfile.mkdtemp())
        (run / "results.json").write_text(json.dumps({"reviewers_ok": ["argon"]}))
        self.assertEqual(ur.run_model(run), ur.panelist("argon"))
        shutil.rmtree(run)

    def test_one_sentence(self):
        self.assertEqual(ur.one_sentence("A holds. B holds."), "A holds.")
        # A label naming the kind of inference is dropped. Other parentheses stay.
        self.assertEqual(ur.one_sentence("X yields Y (a proposal's aim and hypothesis)."), "X yields Y.")
        self.assertEqual(ur.one_sentence("X is linked to Y (an association)"), "X is linked to Y")
        self.assertEqual(ur.one_sentence("X lowers ECE (from 9.1% to 2.3%)."), "X lowers ECE (from 9.1% to 2.3%).")
        self.assertEqual(ur.one_sentence("  A  holds  "), "A holds")
        self.assertEqual(ur.one_sentence(None), "")

    def test_old_summary_loses_its_label_when_read(self):
        run = Path(tempfile.mkdtemp())
        (run / "summary.json").write_text(json.dumps({"claim": "X yields Y (a proposal's aim).", "themes": []}))
        self.assertEqual(ur.summary_state(run)["claim"], "X yields Y.")
        shutil.rmtree(run)


class NotAssessed(unittest.TestCase):
    def test_lists_what_the_panel_could_not_check(self):
        with tempfile.TemporaryDirectory() as d:
            prose, nums, fig = Path(d) / "a.md", Path(d) / "b.md", Path(d) / "c.md"
            prose.write_text("We propose a four-day week for the team.\n")
            nums.write_text("Accuracy rose to 78.4% (n = 5 seeds).\n")
            fig.write_text("See ![fit](fig1.png).\n")
            # Prose with no numbers, code, or data: nothing to reproduce.
            self.assertEqual(ur.not_assessed({"files": [str(prose)], "verify": False}),
                             "Not assessed by the panel: whether cited sources say what the draft says they do "
                             "(check them with Also fact-check claims in the review page's Re-review ▾ menu, or `--verify`).")
            self.assertEqual(ur.not_assessed({"files": [str(prose)], "verify": False}, page=True),
                             "Not assessed by the panel: whether cited sources say what the draft says they do "
                             "(check them with Re-review ▾ › Also fact-check claims).")
            self.assertEqual(ur.not_assessed({"files": [str(prose)], "verify": True}), "")
            self.assertEqual(ur.not_assessed({"files": [str(nums)], "verify": True}),
                             "Not assessed by the panel: whether reported numbers reproduce from the data or code.")
            self.assertEqual(ur.not_assessed({"files": [str(fig)], "verify": True}),
                             "Not assessed by the panel: the images the draft links to.")
            self.assertIn(", whether reported numbers reproduce from the data or code, and the images",
                          ur.not_assessed({"files": [str(nums), str(fig)], "verify": False}))


class ClaimRules(unittest.TestCase):
    def test_claim_map_and_finding_rule_reach_the_panel(self):
        rules = ur.reviewer_rules()
        self.assertIn("identify up to three central claims", rules)
        self.assertIn("one sentence of at most 25 words", rules)
        self.assertIn("Keep Nitpicks terse", rules)
        # The prompt carries the rule itself, so custom --rules cannot drop it.
        prompt = ur.review_prompt("draft", "", "custom rules only")
        self.assertIn("up to three central claims", prompt)
        self.assertIn("problem: <one sentence, at most 25 words", prompt)
        self.assertIn("narrows the claim to\nwhat the evidence supports", prompt)


class SinceLast(unittest.TestCase):
    def results(self, since):
        g = lambda t, seen, pos: {"rep": {"title": t, "quote": "", "body": "Point."}, "severity": "Major",
                                  "rejected": False, "where": "draft", "pos": pos, "seen": seen}
        return {"groups": [g("Old point", 2, 0), g("New point", 1, 5)], "headings": [], "since_last": since}

    def test_counts_and_numbers(self):
        r = self.results({"resolved": [{"n": 4, "title": "Fixed thing"}],
                          "dropped": [{"n": 6, "title": "Quiet thing"}]})
        block = ur.since_block(r)
        self.assertIn("**Resolved (1)**: 4 (numbers from the last review)", block)
        self.assertIn("**Persisting (1)**: 1", block)
        self.assertIn("**New (1)**: 2", block)
        self.assertIn("Quiet thing", block)

    def test_first_review_has_no_block(self):
        self.assertEqual(ur.since_block(self.results(None)), "")

    def test_older_runs_kept_titles_only(self):
        self.assertIn("**Resolved (1)**\n", ur.since_block(self.results({"resolved": ["Fixed thing"], "dropped": []})))


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
        g["severity"] = "Minor"
        self.assertIsNone(ur.churn(g, text, history))
        steady = typo_group("Beta stays", "Beta remains")
        self.assertIsNone(ur.churn(steady, text, history))

    def test_churn_allows_only_critical_after_two_changes(self):
        text = "Alpha four words here."
        history = ["Alpha two words here.", "Alpha three words here."]
        g = typo_group("Alpha four words", "Alpha five words")
        g["severity"] = "Minor"
        self.assertIn("2 of the last 2", ur.churn(g, text, history))
        g["severity"] = "Major"
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
             mock.patch.object(ur.runtime, "log", lambda *a: None):
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


class Iterate(unittest.TestCase):
    def f(self, **kw):
        base = {"status": None, "form": "edit", "where": "draft", "tag": "Unanimous", "applicable": True,
                "slot": False, "severity": "Nitpick"}
        return {**base, **kw}

    def test_independent_raisers_count_as_agreement(self):
        g = {"votes": {}, "raised_by": ["claude", "gpt", "gemini"], "self_voter": "claude"}
        self.assertEqual(ur.vote_tag(g), "Unanimous")  # all three raised it, so none voted on it
        g = {"votes": {"gpt": {"vote": "disagree"}}, "raised_by": ["claude", "gemini"], "self_voter": "gemini"}
        self.assertEqual(ur.vote_tag(g), "No majority")
        g = {"votes": {"gpt": {"vote": "agree"}}, "raised_by": ["claude"], "self_voter": "claude"}
        self.assertEqual(ur.vote_tag(g), "Unanimous")

    def test_a_solo_finding_is_tagged_solo(self):
        g = {"votes": {}, "raised_by": ["argon"], "self_voter": "argon", "solo": True}
        self.assertEqual(ur.vote_tag(g), "Solo")

    def test_solo_major_and_minor_findings_auto_apply(self):
        self.assertTrue(ur.auto_applies(self.f(tag="Solo", severity="Minor")))
        self.assertFalse(ur.auto_applies(self.f(tag="Solo")))  # a nitpick needs every voter of a panel

    def test_auto_applies(self):
        self.assertTrue(ur.auto_applies(self.f()))
        self.assertTrue(ur.auto_applies(self.f(tag="Majority", severity="Minor")))
        self.assertFalse(ur.auto_applies(self.f(tag="Majority")))  # a nitpick needs every voter
        for kw in ({"tag": "Contested", "severity": "Major"}, {"where": "overview"}, {"form": "question"},
                   {"slot": True}, {"applicable": False}, {"status": "declined"}, {"tag": "No majority", "severity": "Major"}):
            self.assertFalse(ur.auto_applies(self.f(**kw)), kw)

    def test_loop_applies_agreed_findings_and_stops_when_nothing_applies(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            doc = Path(d).resolve() / "memo.md"
            doc.write_text("# Memo\n\nThe sky is green today.\n\nWater is dry.\n")
            g = lambda t, q, body, votes, contested=False: {
                "rep": {"title": t, "quote": q, "body": body}, "severity": "Major", "where": "draft", "pos": 0,
                "rejected": False, "contested": contested, "raised_by": ["claude"], "frac": 1.0,
                "votes": {m: {"vote": v} for m, v in votes.items()}}
            rounds = [[g("Sky", "The sky is green today.", "Wrong.\n\nThe sky ~~is green~~ 🟢 **is blue** today.",
                         {"gpt": "agree", "gemini": "agree"}),
                       g("Water", "Water is dry.", "Wrong.\n\nWater is ~~dry~~ 🟢 **wet**.",
                         {"gpt": "agree", "gemini": "disagree"}, contested=True)], []]
            def review(path, panel):
                i = len(list((Path(d) / "runs").glob("r*")))
                run = Path(d) / "runs" / f"r{i}"
                run.mkdir(parents=True)
                (run / "results.json").write_text(json.dumps({
                    "files": [str(path)], "labels": {}, "reviewers_ok": ["claude"], "voters": ["gpt", "gemini"],
                    "verify": False, "failures": [], "headings": [], "groups": rounds[i]}))
                time.sleep(0.01)  # runs are ordered by when their results were written
                return True
            with contextlib.redirect_stderr(io.StringIO()):
                done = ur.iterate(doc, 3, ["claude"], review=review)
            self.assertEqual([r["applied"] for r in done], [[[1, "Sky"]], []])
            self.assertEqual(done[0]["skipped"], 1)
            self.assertEqual(done[0]["attention"], [[2, "Water"]])
            self.assertIn("The sky is blue today.", doc.read_text())
            self.assertIn("Water is dry.", doc.read_text())
            decided = {x["title"]: (x["decision"], x["note"]) for x in ur.load_decisions()[str(doc)]}
            self.assertEqual(decided, {"Sky": ("applied", "auto-loop"), "Water": ("ignore", "auto-loop: skipped")})
            self.assertTrue((doc.parent / "memo-v1.md").exists())
            self.assertTrue((doc.parent / "memo-v1-to-v2.md").exists())


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
            g = lambda t, q, body: {"rep": {"title": t, "quote": q, "body": body}, "severity": "Minor",
                                    "where": "draft", "pos": 0, "rejected": False, "votes": {"claude": {"vote": "agree"}},
                                    "raised_by": ["claude"], "frac": 1.0}
            (run / "results.json").write_text(json.dumps({
                "files": [str(doc)], "labels": {"claude": "Claude Sonnet"}, "reviewers_ok": ["claude"],
                "voters": ["claude"], "verify": False, "failures": [],
                "headings": [], "groups": [
                    g("Sky", "The sky is green today.", "Wrong.\n\nThe sky ~~is green~~ 🟢 **is blue** today."),
                    g("Water", "Water is dry.", "Wrong.\n\nWater is ~~dry~~ 🟢 **wet**.")]}))
            (run / "summary.json").write_text('{"themes": []}')
            page = ur.PageServer(doc)
            code, _, out = page.handle("GET", "/api/state", {})
            st = json.loads(out)
            self.assertEqual([f["applicable"] for f in st["findings"]], [True, True])
            code, mime, md, headers = page.handle("GET", "/api/export/review.md", b"")
            self.assertEqual((code, headers["Content-Disposition"]), (200, 'attachment; filename="memo-review.md"'))
            self.assertIn("### 1. Sky", md)
            if shutil.which("pandoc"):
                code, mime, data, _ = page.handle("GET", "/api/export/review.docx", b"")
                self.assertEqual((code, mime, data[:2]), (200, ur.DOCX_MIME, b"PK"))
                back = subprocess.run(["pandoc", "-f", "docx", "-t", "plain"], input=data, capture_output=True).stdout.decode()
                self.assertIn("Sky", back)
            self.assertEqual(page.handle("GET", "/api/export/review.pdf", b"")[0], 400)
            self.assertEqual(page.handle("POST", "/api/accept", {"n": 1})[0], 200)
            self.assertIn("The sky is blue today.", doc.read_text())
            doc.write_text(doc.read_text().replace("Water is dry.", "Water is arid."))
            code, _, out = page.handle("POST", "/api/accept", {"n": 2})
            self.assertEqual(code, 409)
            self.assertIn("Water is arid.", doc.read_text())
            self.assertEqual(page.handle("POST", "/api/decline", {"n": 2, "note": "fine"})[0], 200)
            st = json.loads(page.handle("GET", "/api/state", {})[2])
            self.assertEqual([f["status"] for f in st["findings"]], ["accepted", "declined"])

    def test_rereview_options_start_over_and_fact_check(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            doc = Path(d).resolve() / "memo.md"
            doc.write_text("# Memo\n\nThe sky is green today.\n")
            run = Path(d) / "runs" / "r1"
            run.mkdir(parents=True)
            (run / "results.json").write_text(json.dumps({
                "files": [str(doc)], "labels": {}, "reviewers_ok": [], "voters": [], "verify": False,
                "failures": [], "headings": [], "groups": []}))
            # The page asking to start over is the file's own server: it must not stop itself.
            (Path(d) / "runs" / "pages.json").write_text(json.dumps({str(doc): {"port": 1, "pid": os.getpid()}}))
            started = []
            class Job:
                def __init__(self, cmd, **kw): started.append(cmd)
                def poll(self): return None
            page = ur.PageServer(doc)
            kills = []
            with mock.patch.object(ur.subprocess, "Popen", Job), mock.patch.object(ur.runtime, "log", lambda *a: None), \
                    mock.patch.object(ur.os, "kill", lambda pid, sig: kills.append(pid)):
                code, _, out = page.handle("POST", "/api/update", {"fresh": True, "verify": True})
            self.assertEqual(kills, [])
            self.assertEqual(code, 200)
            self.assertIn("--verify", started[0])
            self.assertEqual(ur.runs_for(doc), [])  # set aside, not deleted
            self.assertTrue(list((Path(d) / "runs" / "forgotten").glob("*/runs/r1/results.json")))
            st = json.loads(page.handle("GET", "/api/state", {})[2])
            self.assertEqual((st["starting_over"], st["job"]["running"]), (True, True))
            # A plain Re-review keeps the history and adds no fact-check.
            page.job = None
            run.parent.joinpath("r2").mkdir()
            (run.parent / "r2" / "results.json").write_text((Path(d) / "runs" / "forgotten").glob("*/runs/r1/results.json").__next__().read_text())
            with mock.patch.object(ur.subprocess, "Popen", Job):
                page.handle("POST", "/api/update", {})
            self.assertNotIn("--verify", started[1])
            self.assertEqual(len(ur.runs_for(doc)), 1)

    def test_each_page_logs_its_own_rereview_and_reports_its_progress(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            docs = [Path(d).resolve() / "a.md", Path(d).resolve() / "b.md"]
            class Job:
                def __init__(self, cmd, stdout=None, **kw): self.out = stdout
                def poll(self): return None
            pages = []
            for doc in docs:
                doc.write_text("# Memo\n\nText.\n")
                page = ur.PageServer(doc)
                with mock.patch.object(ur.subprocess, "Popen", Job), mock.patch.object(ur, "runs_for", lambda p: []):
                    page.handle("POST", "/api/update", {})
                pages.append(page)
            self.assertNotEqual(pages[0].job_log, pages[1].job_log)  # two pages never share a log
            pages[0].job.out.write("1/3 review (no web): claude, gpt\n  gpt: review done, 12 findings (31 s)\n")
            pages[0].job.out.flush()
            st = pages[0].job_state()
            self.assertEqual((st["running"], st["kind"]), (True, "review"))
            self.assertEqual([(s["label"], s["state"]) for s in st["stages"]], [("Review", "running")])
            self.assertEqual({m["name"]: m["state"] for m in st["stages"][0]["models"]}, {"claude": "running", "gpt": "done"})
            self.assertIn("  gpt: review done, 12 findings (31 s)", st["log"])
            self.assertGreaterEqual(st["elapsed"], 0)
            self.assertEqual(pages[1].job_state()["stages"], [])  # the other page's log is untouched
            for p in pages:
                p.job.out.close()

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
        # Older names map to the current ones in rank order.
        self.assertEqual(fs[0]["severity"], "Major")
        self.assertEqual((v["A1"]["severity"], v["A2"]["severity"]), ("Nitpick", "Major"))
        self.assertEqual([ur.canon_sev(s) for s in ("Critical", "Substantive", "Polish", "Minor")],
                         ["Major", "Minor", "Nitpick", "Minor"])
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
                with mock.patch.object(ur, "ordered_findings", lambda r: [(1, "Minor", "", g)]), \
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
                    if ur.load_comments(run)[0]["overall"]["status"] != "pending":
                        break
                    time.sleep(0.01)
            self.assertIn("<passage>\nThe sky is green.\n</passage>", prompts[0])
            self.assertEqual(ur.load_comments(run)[0]["passage"], "The sky is green.")

    def test_a_comment_gets_one_overall_recommendation_after_every_answer(self):
        prompts = []

        def call(m, prompt, *a, **k):
            prompts.append(prompt)
            if "one overall recommendation" in prompt:
                return "Accept GPT's edit.\n"
            if m == "gemini":
                return None
            return "Green is wrong.\nCHANGES:\nThe sky is ~~green~~ 🟢 **blue**." if m == "gpt" else "Fine.\nCHANGES: none"

        def wait(run):
            for _ in range(300):
                c = ur.load_comments(run)[-1]
                if c["overall"]["status"] != "pending":
                    return c
                time.sleep(0.01)
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run"
            run.mkdir()
            draft = Path(d) / "m.md"
            draft.write_text("The sky is green.\n")
            with mock.patch.object(ur, "call", call), mock.patch.object(ur, "page_panel", lambda p: ["claude", "gpt", "gemini"]), \
                 mock.patch.object(ur, "load_rules", lambda p: ("rules", "")), \
                 mock.patch.object(ur, "failure_reason", lambda run, stem: "no reply"):
                ur.comment_panel(draft, run, "Is this right?", False)
                c = wait(run)
                self.assertEqual(c["overall"], {"status": "done", "text": "Accept GPT's edit."})
                rec = prompts[-1]
                self.assertIn("one overall recommendation", rec)
                self.assertIn("Green is wrong.", rec)
                self.assertIn("Proposed edit: 'The sky is green.' -> 'The sky is blue.'", rec)
                self.assertNotIn("<answer reviewer=\"Gemini\"", rec)  # a failed answer is left out
                # No answer at all: no recommendation, and nothing left pending.
                with mock.patch.object(ur, "call", lambda *a, **k: None):
                    ur.comment_panel(draft, run, "And this?", False)
                    self.assertEqual(wait(run)["overall"], {"status": "none"})

    def test_a_review_of_an_edit_appends_its_findings_after_the_rest(self):
        review = ("=== FINDING\nseverity: Minor\nkind: logic\ntitle: Claim lacks support\n"
                  "quote: The sky is green.\n---\nThe claim needs a source.\n\n"
                  "~~The sky is green.~~ 🟢 **The sky is blue.**\n=== END FINDING\n")
        old = {"rep": {"title": "Old", "quote": "Grass grows.", "body": "Point."}, "votes": {}, "raised_by": [],
               "where": "draft", "pos": 30, "severity": "Polish", "kind": "style", "rejected": False}
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run"
            run.mkdir()
            draft = Path(d) / "m.md"
            draft.write_text("The sky is green.\n\nGrass grows.\n")
            (run / "results.json").write_text(json.dumps({"labels": {}, "groups": [old], "headings": []}))

            def call(m, prompt, *a, **k):
                return review if "Review the draft" in prompt else "A1 | agree | Minor | logic | same:none | Fair."
            with mock.patch.object(ur, "call", call), mock.patch.object(ur, "page_panel", lambda p: ["claude", "gpt"]), \
                 mock.patch.object(ur, "load_rules", lambda p: ("rules", "")), mock.patch.object(ur, "load_decisions", lambda: {}):
                ur.review_passage(draft, run, "The sky is green.")
                for _ in range(300):
                    if json.loads((run / "edit-review.json").read_text())["status"] != "pending":
                        break
                    time.sleep(0.01)
            st = json.loads((run / "edit-review.json").read_text())
            self.assertEqual(st["status"], "done", st)
            fs = ur.ordered_findings(json.loads((run / "results.json").read_text()))
            # The earlier Polish finding keeps number 1, and the new Minor ones follow it.
            self.assertEqual(fs[0][3]["rep"]["title"], "Old")
            self.assertTrue(all(g.get("added") == st["first"] for _, _, _, g in fs[1:]))
            self.assertIn("Claim lacks support", [g["rep"]["title"] for _, _, _, g in fs[1:]])

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
            code, _, _ = page.handle("POST", "/api/upload/notes.pptx", b"x")
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
            unified.write_text("# my paper.pdf\n\n<script>window.xss = true</script>\n")
            (folder / "stdout.log").write_text(f"{unified}\n")
            st = json.loads(page.handle("GET", "/api/job/" + uid, b"")[2])
            self.assertEqual(st["markdown"], unified.read_text())
            self.assertIsNone(st["html"])
            self.assertEqual(st["name"], "my paper.pdf")
            self.assertEqual(page.handle("GET", "/api/job/nope", b"")[0], 404)

    def test_repeated_uploads_get_distinct_job_ids(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d)), \
                mock.patch.object(ur.subprocess, "Popen"):
            first = ur.start_upload("memo.md", b"# Memo\n")
            second = ur.start_upload("memo.md", b"# Memo\n")
            self.assertNotEqual(first, second)
            self.assertTrue((Path(d) / "uploads" / first / "upload" / "memo.md").exists())
            self.assertTrue((Path(d) / "uploads" / second / "upload" / "memo.md").exists())

    def test_repeated_opens_get_distinct_job_ids(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"), \
                mock.patch.object(ur.subprocess, "Popen"):
            doc = Path(d) / "memo.md"
            doc.write_text("# Memo\n")
            first, second = ur.start_review(doc), ur.start_review(doc)
            self.assertNotEqual(first, second)
            self.assertEqual((Path(d) / "runs" / "opens" / second / "file.txt").read_text(), str(doc))

    @unittest.skipUnless(shutil.which("pandoc"), "needs pandoc")
    def test_upload_of_a_reviewed_word_file_offers_open_again_or_fresh(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            src = Path(d) / "memo.md"
            src.write_text("# Memo\n\nSome text.\n")
            docx = Path(d) / "memo.docx"
            subprocess.run(["pandoc", str(src), "-o", str(docx)], check=True)
            body, page = docx.read_bytes(), ur.UploadServer()
            check = lambda: json.loads(page.handle("POST", "/api/upload/check/memo.docx", body)[2])
            self.assertEqual(check(), {"seen": False, "reviews": 0, "last": None})
            with contextlib.redirect_stderr(io.StringIO()):
                md = ur.to_markdown(docx)
            run = ur.RUNS_DIR / "2026-10-09-1200-memo-v1"
            run.mkdir()
            md = md.resolve()  # as a review records it
            (run / "results.json").write_text(json.dumps({"files": [str(md)]}))
            self.assertEqual(check(), {"seen": True, "reviews": 1, "last": "2026-10-09"})
            self.assertEqual(json.loads(page.handle("POST", "/api/upload/check/notes.md", b"# x")[2])["seen"], False)
            with mock.patch.object(ur, "page_url", lambda p: "http://127.0.0.1:1/" if p == md else None):
                self.assertEqual(json.loads(page.handle("POST", "/api/upload/open/memo.docx", body)[2])["page"],
                                 "http://127.0.0.1:1/")
            with mock.patch.object(ur, "start_upload", lambda name, body: "job1"):
                self.assertEqual(json.loads(page.handle("POST", "/api/upload/memo.docx", body)[2]), {"id": "job1"})
                self.assertEqual(check()["seen"], True)  # review again keeps the history
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(json.loads(page.handle("POST", "/api/upload/fresh/memo.docx", body)[2]), {"id": "job1"})
            self.assertEqual(check()["seen"], False)  # start over forgot it
            self.assertTrue(md.exists())  # the edited copy stays

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
            with mock.patch.object(ur, "choose_file", lambda start: (str(Path(d) / "notes.pptx"), None)):
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

    @unittest.skipUnless(shutil.which("pandoc"), "needs pandoc")
    def test_word_file_is_edited_as_markdown_and_downloads_with_tracked_changes(self):
        def as_md(f, changes="accept"):
            return subprocess.run(["pandoc", str(f), "-t", ur.DOCX_MD, "--wrap=none", f"--track-changes={changes}"],
                                  capture_output=True, text=True, check=True).stdout
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            src = Path(d) / "memo.md"
            src.write_text(
                "# Memo\n\nThe cortex learns **slowly and steadily** from [work](https://x.org).[^1]\n\n"
                "The energy is $E = mc^2$ in this regime, which [Ann's note.]{.comment-start id=\"0\" author=\"Ann\" "
                "date=\"2026-01-01T00:00:00Z\"}matters[]{.comment-end id=\"0\"} here.\n\nThis one goes.\n\n"
                "| A | B |\n|---|---|\n| 1 | 2 |\n\n- first\n- second\n\nCited here^4^ and done.\n\nLast paragraph stays CITE.\n\n[^1]: A footnote.\n")
            docx = Path(d) / "memo.docx"
            subprocess.run(["pandoc", str(src), "-o", str(docx)], check=True)
            # Make it look like Word wrote it: a run split mid-word, and a citation field.
            with zipfile.ZipFile(docx) as z:
                parts = {i: z.read(i.filename) for i in z.infolist()}
            for i in parts:
                if i.filename == "word/document.xml":
                    parts[i] = parts[i].decode().replace(
                        '<w:t xml:space="preserve">Last paragraph stays CITE.</w:t></w:r>',
                        '<w:t xml:space="preserve">Last para</w:t></w:r><w:proofErr w:type="spellStart"/>'
                        '<w:r><w:t xml:space="preserve">graph stays </w:t></w:r>'
                        '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> ADDIN ZOTERO_ITEM </w:instrText></w:r>'
                        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>(Smith 2020)</w:t></w:r>'
                        '<w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:t>.</w:t></w:r>').encode()
            with zipfile.ZipFile(docx, "w") as z:
                for i, data in parts.items():
                    z.writestr(i, data)
            md = ur.to_markdown(docx)
            self.assertIn(ur.RUNS_DIR / "converted", md.parents)
            self.assertFalse(ur.read_only(md))
            self.assertEqual(ur.original_of(md), md.with_suffix(".docx"))
            before = md.read_text()
            self.assertIn("$E = mc^{2}$", before)
            self.assertIn("Last paragraph stays (Smith 2020).", before)
            after = (before.replace("**slowly and steadily**", "**slowly**")
                     .replace("in this regime", "at low speed").replace("This one goes.\n\n", "")
                     .replace("| 2 ", "| 3 ").replace("- second", "- second, revised")
                     .replace("Cited here<sup>4</sup> and done.", "Cited here<sup>4</sup> with care and done.")
                     .replace("Last paragraph stays (Smith 2020).", "Last paragraph now stays (Smith 2021).\n\nA new one.")
                     .replace("[^1]: A footnote.", "[^1]: A changed footnote."))
            md.write_text(after)
            self.assertEqual(ur.to_markdown(docx), md)  # the same file again keeps the edits
            self.assertEqual(md.read_text(), after)
            page = ur.PageServer(md)
            code, mime, data, headers = page.handle("GET", "/api/export/draft.docx", b"")
            self.assertEqual((code, mime), (200, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
            self.assertEqual(headers["Content-Disposition"], 'attachment; filename="memo-edited.docx"')
            missed = json.loads(urllib.parse.unquote(headers["X-Not-Placed"]))
            self.assertEqual([(m["why"], m["old"], m["new"]) for m in missed],
                             [("it changes an equation, citation or other field, footnote mark, or image",
                               "Last paragraph stays (Smith 202[0]).", "Last paragraph stays (Smith 202[1]).")])  # just the change, in brackets
            out = Path(d) / "out.docx"
            out.write_bytes(data)
            plain = lambda m: subprocess.run(["pandoc", "-f", ur.DOCX_MD, "-t", "plain", "--wrap=none"], input=m,
                                             capture_output=True, text=True).stdout
            # Accepting every change gives the edited draft, less the edit not placed. Rejecting gives the original.
            # "now" is placed; only the change inside the citation field is not.
            self.assertEqual(plain(as_md(out)), plain(after.replace("(Smith 2021)", "(Smith 2020)")))
            self.assertEqual(plain(as_md(out, "reject")), plain(before))
            self.assertRegex(as_md(out, "all"), r'"deletion"[^>]*>in this regime<.*"insertion"[^>]*>at low speed<')  # one change, not word by word
            with zipfile.ZipFile(out) as b:
                self.assertIn(b"ZOTERO_ITEM", b.read("word/document.xml"))
            # Words added after a superscript are not superscript; a changed superscript stays one.
            with zipfile.ZipFile(out) as z:
                x = z.read("word/document.xml").decode()
            self.assertNotRegex(x, r'<w:ins [^>]*><w:r><w:rPr>(?:(?!</w:rPr>).)*vertAlign')
            # Ann's comment stays, and the edit that could not be placed is a comment on its paragraph.
            comments = as_md(out, "all")
            self.assertIn('author="Ann"', comments)
            self.assertRegex(comments, r'author="Unified review"[^>]*>This edit is in the reviewed draft but could not be placed[^<]*'
                                       r'Was: Last paragraph stays \(Smith 202\\?\[0\\?\]\)\.')  # pandoc escapes brackets
            self.assertRegex(comments, r'comment-end[^>]*></span>Last paragraph|Last paragraph[^\n]*comment-end')
            # A blank left in the draft is a comment too.
            md.write_text(after.replace("A new one.", "A new one {{citation: Author, year}}."))
            _, _, data, _ = ur.export_draft(md, "docx")
            out.write_bytes(data)
            self.assertRegex(as_md(out, "all"), r'author="Unified review"[^>]*>Fill this in: \{\{citation: Author, year\}\}')

    def test_forget_sets_aside_reviews_decisions_and_versions(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            doc, other = Path(d).resolve() / "memo.md", Path(d).resolve() / "other.md"
            doc.write_text("# Memo\n")
            for name, f in (("r1", doc), ("r2", doc), ("r3", other)):
                (ur.RUNS_DIR / name).mkdir(parents=True)
                (ur.RUNS_DIR / name / "results.json").write_text(json.dumps({"files": [str(f)]}))
            (ur.RUNS_DIR / "decisions.json").write_text(json.dumps({str(doc): [{"id": "D1"}], str(other): [{"id": "D1"}]}))
            (ur.RUNS_DIR / "versions.json").write_text(json.dumps({str(doc): ["a", "b"], str(other): ["c"]}))
            with contextlib.redirect_stdout(io.StringIO()):
                out = ur.forget(doc)
            self.assertEqual(ur.runs_for(doc), [])
            self.assertEqual([r.name for r in ur.runs_for(other)], ["r3"])
            self.assertEqual(sorted(x.name for x in (out / "runs").iterdir()), ["r1", "r2"])
            self.assertNotIn(str(doc), json.loads((ur.RUNS_DIR / "decisions.json").read_text()))
            self.assertIn(str(other), json.loads((ur.RUNS_DIR / "decisions.json").read_text()))
            self.assertEqual(ur.version_number(doc, "b"), 1)  # the edited text is version 1
            kept = json.loads((out / "forgotten.json").read_text())
            self.assertEqual((kept["decisions"], kept["versions"]), ([{"id": "D1"}], ["a", "b"]))
            self.assertTrue(doc.exists())

    def test_servers_starting_together_keep_each_others_entries(self):
        with tempfile.TemporaryDirectory() as d:
            runs = Path(d) / "runs"
            files = [Path(d) / f"f{k}.md" for k in range(4)]
            for f in files:
                f.write_text("# x\n")
            env = {**os.environ, "UNIFIED_REVIEW_RUNS": str(runs)}
            logs = [open(Path(d) / f"serve{k}.err", "w") for k in range(len(files))]
            procs = [subprocess.Popen([sys.executable, str(REPO / "bin" / "unified-review"), "--serve", str(f)], env=env,
                                      stdout=subprocess.DEVNULL, stderr=log) for f, log in zip(files, logs)]
            try:
                for _ in range(300):  # cold starts on CI runners can take several seconds
                    pages = json.loads((runs / "pages.json").read_text()) if (runs / "pages.json").exists() else {}
                    if len(pages) == len(files):
                        break
                    time.sleep(0.1)
                errs = "\n".join(f"server {k} (exit {p.poll()}): {(Path(d) / f'serve{k}.err').read_text()[-1500:]}"
                                  for k, p in enumerate(procs))
                self.assertEqual(sorted(pages), sorted(str(f.resolve()) for f in files), errs)
                self.assertEqual(sorted(v["pid"] for v in pages.values()), sorted(p.pid for p in procs))
            finally:
                for p in procs:
                    p.terminate()
                    p.wait()
                for log in logs:
                    log.close()

    def test_draft_downloads_in_the_format_it_came_in(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ur, "RUNS_DIR", Path(d) / "runs"):
            draft = Path(d) / "draft.md"
            draft.write_text("# Draft\n")
            self.assertEqual(ur.export_draft(draft), ("draft-edited.md", ur.MD_MIME, b"# Draft\n", []))
            if shutil.which("pandoc"):  # a Markdown draft as Word, through pandoc
                name, mime, data, _ = ur.export_draft(draft, "docx")
                self.assertEqual((name, mime, data[:2]), ("draft-edited.docx", ur.DOCX_MIME, b"PK"))
            with self.assertRaises(ValueError):
                ur.export_draft(draft, "pdf")  # only a draft that came as a PDF
            md = ur.RUNS_DIR / "converted" / "paper-abc" / "paper.md"
            md.parent.mkdir(parents=True)
            md.write_text("# Paper\n")
            md.with_suffix(".pdf").write_bytes(b"%PDF")
            def make_pdf(cmd, **k):
                Path(cmd[cmd.index("-o") + 1]).write_bytes(b"%PDF-edited")
                return SimpleNamespace(returncode=0, stderr="")
            with mock.patch.object(ur.subprocess, "run", make_pdf) as run:
                self.assertEqual(ur.export_draft(md), ("paper-edited.pdf", "application/pdf", b"%PDF-edited", []))

    def test_job_progress_reads_each_model_from_the_log(self):
        lines = ["memo.pdf: converting to Markdown", "memo.pdf: Markdown copy at /x/memo.md",
                 "1/3 review (no web): claude, gpt, gemini", "  gpt: review done, 12 findings (31 s)",
                 "  gemini: review attempt 1 failed (timeout), retrying"]
        with mock.patch.object(ur, "SEEN", {}):
            st = ur.job_progress("j", lines, True)
            self.assertEqual([(s["label"], s["state"]) for s in st], [("Convert to Markdown", "done"), ("Review", "running")])
            self.assertEqual([(m["name"], m["state"], m["note"]) for m in st[1]["models"]],
                             [("claude", "running", ""), ("gpt", "done", "12 findings (31 s)"), ("gemini", "running", "retrying")])
            lines += ["  gemini: review failed (no reply)", "  claude: review done, 20 findings (200 s)",
                      "2/3 vote on 32 findings: claude, gpt", "3/3 render: 32 findings in 30 groups, 0 rejected by vote"]
            st = ur.job_progress("j", lines, False)
            self.assertEqual([s["state"] for s in st], ["done", "done", "done", "done"])
            self.assertEqual([m["state"] for m in st[1]["models"]], ["done", "done", "failed"])
            self.assertEqual([m["state"] for m in st[2]["models"]], ["done", "done"])  # finished, though not logged
            self.assertEqual(st[1]["secs"], 200)  # the slowest model's time
            two = ["1/4 review (no web): gpt, argon", "2/4 vote on 9 findings: gpt, argon",
                   "3/4 mediate 2 findings: Claude Opus", "4/4 render: 9 findings in 8 groups, 1 rejected by vote"]
            st = ur.job_progress("k", two, False)
            self.assertEqual([s["label"] for s in st], ["Review", "Vote on each other's findings", "Break ties", "Merge"])
            self.assertEqual([m["name"] for m in st[2]["models"]], ["Claude Opus"])

# ---------------------------------------------------------------- two-lab panel and notes file

DRAFT2 = "# Intro\n\nThe sky is green today.\n\nGrass grows slowly.\n\nWater is dry.\n"


def two_lab_review(d, replies, votes, mediation=None, draft_text=DRAFT2, fails=(), panel=("gpt", "argon"), missing=()):
    """Run foreground with two reviewers and a scripted mediator. replies: {model: review text}.
    votes: {model: {title: "problem | fix"}}. mediation: {title: block lines} or None.
    Returns (run folder, prompts)."""
    prompts = {}

    def fake_call(m, prompt, out, workdir, web=False, stage=""):
        prompts.setdefault(stage, {})[m] = prompt
        if m in fails or (stage, m) in fails:
            ur.fail(stage, m, "fake failure")
            return None
        if stage == "review":
            return replies[m]
        if stage == "vote":
            listed, _, own = prompt.partition("<your_own_findings>")
            rows = re.findall(r"^\[([A-H]\d+)\] \([^)]*\) (.+)$", listed, re.M)
            mine = dict((t, i) for i, t in re.findall(r"^\[([A-H]\d+)\] (.+)$", own.split("</your_own_findings>")[0], re.M))
            # Like a careful voter, name its own finding with the same title as the same point.
            return "\n".join(f"{i} | {votes[m].get(t, 'agree | agree')} | Minor | logic | same:{mine.get(t, 'none')} | why not"
                             for i, t in rows)
        if stage == "mediate":
            items = re.findall(r"^\[(M\d+)\] [^(]*\(\w+\) (.+)$", prompt, re.M)
            default = "ruling: uphold\nfix: a\nreason: fine\nproblem: same"
            # mediation may be a function of (model, title) that returns None to skip an item.
            pick = mediation if callable(mediation) else lambda m, t: (mediation or {}).get(t, default)
            return "\n\n".join(f"=== {i}\n" + b for i, t in items if (b := pick(m, t)) is not None)
        return ""
    f = d / "memo.md"
    if not f.exists():
        f.write_text(draft_text)
    # Unique run names: decisions are looked up by run name across every test's folders.
    out = d / f"run-{d.name}-{len(list(d.glob('run*')))}"
    out.mkdir()
    ur.FAILURES.clear()
    ur.LEFT_OFF.clear()
    with mock.patch.object(ur, "call", fake_call), mock.patch.object(ur, "available", lambda m: m not in missing), \
         mock.patch.object(ur, "LAST_RUN", d / "last-run"), mock.patch.object(ur.runtime, "log", lambda *a: None):
        ur.foreground([f], f"===== memo.md =====\n{f.read_text()}", list(panel), "", "rules", out, d, False, [])
    return out, prompts


def finding_text(title, quote, problem, fix, severity="Minor"):
    return (f"=== FINDING\nseverity: {severity}\nkind: logic\nform: edit\ntitle: {title}\nquote: {quote}\n---\n"
            f"problem: {problem}\n{fix}\n")


SKY = lambda fix="The sky is ~~green~~ 🟢 **blue** today.", who="": finding_text(
    "Sky color is wrong" + who, "The sky is green today.", "The sky is blue, so the claim fails.", fix)
WATER = finding_text("Water is not dry", "Water is dry.", "Water is wet.", "Water is ~~dry~~ 🟢 **wet**.")
GRASS = finding_text("Grass speed unsupported", "Grass grows slowly.", "No rate or baseline is given.",
                     "Grass grows ~~slowly~~ 🟢 **1 cm a week**.")


class ProblemAndFix(unittest.TestCase):
    def test_problem_line_splits_from_the_fix(self):
        f = ur.parse_findings(SKY())[0]
        self.assertEqual(f["problem"], "The sky is blue, so the claim fails.")
        self.assertEqual(f["fix"], "The sky is ~~green~~ 🟢 **blue** today.")
        self.assertEqual(ur.diff_parts(f["body"]), ("The sky is green today.", "The sky is blue today."))

    def test_older_replies_split_at_the_first_paragraph(self):
        self.assertEqual(ur.split_problem("Wrong date.\n\n~~1066~~ 🟢 **753 BC**"), ("Wrong date.", "~~1066~~ 🟢 **753 BC**"))
        self.assertEqual(ur.split_problem("problem: Runs\nonto two lines.\n\nfix: ~~a~~ 🟢 **b**"),
                         ("Runs onto two lines.", "~~a~~ 🟢 **b**"))

    def test_votes_carry_a_fix_vote_and_old_lines_still_parse(self):
        v = ur.parse_votes("A1 | agree | disagree | Major | logic | same:none | Fix misses it.\n"
                           "B1 | partial | Minor | same:none | Old format.")
        self.assertEqual((v["A1"]["vote"], v["A1"]["fix"]), ("agree", "disagree"))
        self.assertEqual((v["B1"]["vote"], v["B1"]["fix"]), ("partial", ""))

    def test_vote_prompt_asks_for_problem_and_fix_separately(self):
        self.assertIn("Judge the problem and the fix separately", ur.VOTE)
        self.assertIn("<problem> | <fix>", ur.VOTE)


class TwoLab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def groups(self, out):
        r = json.loads((out / "results.json").read_text())
        return r, {g["rep"]["title"]: g for g in r["groups"]}

    def test_default_is_three_models_two_reviewers_and_a_claude_mediator(self):
        self.assertEqual(ur.DEFAULT_PANEL, ["gpt", "argon"])
        self.assertTrue(ur.MEDIATOR.startswith("claude:"))

    def test_agreed_problem_goes_in_the_main_review_and_needs_no_mediator(self):
        out, prompts = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS},
                                      {"gpt": {}, "argon": {}})
        r, g = self.groups(out)
        self.assertFalse(any(x["disputed"] for x in g.values()))
        self.assertNotIn("mediate", prompts)
        self.assertNotIn("Disputed", (out / "unified.md").read_text())

    def test_partial_or_disagree_on_the_problem_is_disputed_and_the_mediator_rules(self):
        out, prompts = two_lab_review(
            self.d, {"gpt": SKY() + GRASS, "argon": WATER},
            {"argon": {"Sky color is wrong": "partial | agree", "Grass speed unsupported": "disagree | agree"}, "gpt": {}},
            {"Sky color is wrong": "ruling: uphold\nseverity: Major\nfix: a\nreason: The claim is false.\nproblem: same",
             "Grass speed unsupported": "ruling: drop\nseverity: Minor\nfix: a\nreason: Slowly is fine here.\nproblem: same"})
        r, g = self.groups(out)
        self.assertTrue(g["Sky color is wrong"]["disputed"])
        self.assertEqual(g["Sky color is wrong"]["severity"], "Major")
        self.assertTrue(g["Grass speed unsupported"]["rejected"])
        self.assertFalse(g["Water is not dry"]["disputed"])
        md = (out / "unified.md").read_text()
        # The main review first, then Disputed, numbered straight through, then what the mediator dropped.
        self.assertLess(md.index("Water is not dry"), md.index("## Disputed: Major"))
        self.assertIn("### 2. Sky color is wrong", md)
        self.assertIn("upholds it: The claim is false.", md)
        self.assertIn("## Dropped by", md)
        self.assertIn("Grass speed unsupported: Slowly is fine here.", md)
        self.assertEqual(r["mediator"], ur.MEDIATOR)
        self.assertIn("DISPUTED", prompts["mediate"][ur.MEDIATOR])
        self.assertNotIn("gpt", prompts["mediate"][ur.MEDIATOR].split("<items>")[1].lower())  # reviewers anonymized

    def test_both_raised_but_fixes_differ_the_mediator_keeps_one(self):
        out, prompts = two_lab_review(
            self.d, {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **gray** today.")},
            {"gpt": {}, "argon": {}},
            {"Sky color is wrong": "ruling: uphold\nfix: b,a\nreason: Gray fits the storm.\nproblem: same"})
        r, g = self.groups(out)
        sky = g["Sky color is wrong"]
        self.assertFalse(sky["disputed"])
        self.assertEqual(sky["fix_issue"], "differ")
        self.assertEqual([a["label"] for a in sky["alts"]], ["b"])  # one fix, even when the reply names two
        self.assertIn("the one fix to keep", prompts["mediate"][ur.MEDIATOR])
        was_b = re.search(r"^Fix b \(from [^)]*\):\n(.+)$", prompts["mediate"][ur.MEDIATOR], re.M).group(1)
        self.assertEqual(sky["alts"][0]["fix"], was_b)
        self.assertIn(was_b, sky["rep"]["body"])  # the pick is the one the page applies
        md = (out / "unified.md").read_text()
        self.assertNotIn("**Fix a**", md)
        self.assertIn("Gray fits the storm.", md)
        with mock.patch.object(ur, "summary_state", lambda run: None):  # no background summary call
            st = ur.page_state(self.d / "memo.md", out)["findings"][0]
        self.assertEqual(len(st["alts"]), 1)

    def test_the_fix_the_mediator_passes_over_goes_under_disputed(self):
        out, prompts = two_lab_review(
            self.d, {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **gray** today.")},
            {"gpt": {}, "argon": {}},
            {"Sky color is wrong": "ruling: uphold\nfix: b\nreason: Gray fits the storm.\nproblem: same"})
        r, g = self.groups(out)
        kept = g["Sky color is wrong"]["alts"][0]["fix"]
        other = next(v for k, v in g.items() if k.startswith("Other fix from ") and k.endswith(": Sky color is wrong"))
        self.assertTrue(other["disputed"])
        self.assertNotEqual(other["alts"][0]["fix"], kept)
        self.assertIn(other["alts"][0]["fix"], other["rep"]["body"])  # the page applies the other fix
        md = (out / "unified.md").read_text()
        main, _, disputed = md.partition("## Disputed")
        self.assertIn(kept, main)
        self.assertNotIn(other["alts"][0]["fix"], main)
        self.assertIn(other["rep"]["title"], disputed)
        self.assertIn("Another fix for “Sky color is wrong”. Claude Opus kept the other fix: Gray fits the storm.", disputed)
        with mock.patch.object(ur, "summary_state", lambda run: None):  # no background summary call
            st = {f["title"]: f for f in ur.page_state(self.d / "memo.md", out)["findings"]}
        self.assertEqual(st[other["rep"]["title"]]["tag"], "Disputed")  # iterate skips it
        with mock.patch.object(ur.runtime, "log", lambda *a: None):
            notes = ur.write_notes(self.d / "memo.md", out).read_text()
        self.assertIn(f"### X1. {other['rep']['title']}", notes)

    def test_each_passed_over_fix_gets_its_own_title(self):
        out, _ = two_lab_review(
            self.d, {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **gray** today."),
                     "grok": SKY("The sky is ~~green~~ 🟢 **white** today.")},
            {"gpt": {}, "argon": {}, "grok": {}},
            {"Sky color is wrong": "ruling: uphold\nfix: a\nreason: Blue is right.\nproblem: same"},
            panel=("gpt", "argon", "grok"))
        others = [k for k in self.groups(out)[1] if k.startswith("Other fix")]
        self.assertEqual(len(others), 2)
        self.assertEqual(len(set(others)), 2)  # a decision on one does not settle the other

    def test_two_settings_of_one_model_get_distinct_other_fix_titles(self):
        g = {"rep": {"title": "T", "quote": "q", "body": "p", "problem": "p"}, "others": [
            {"by": "cursor:foo", "fix": "~~a~~ 🟢 **b**"}, {"by": "cursor:foo@low", "fix": "~~a~~ 🟢 **c**"}]}
        with mock.patch.dict(ur.PANELISTS, {"cursor:foo": ("cursor", "foo", "Foo"), "cursor:foo@low": ("cursor", "foo", "Foo")}):
            titles = [x["rep"]["title"] for x in ur.other_fix_groups([g], {})]
        self.assertEqual(titles, ["Other fix from cursor:foo: T", "Other fix from cursor:foo@low: T"])

    def test_declining_an_other_fix_keeps_its_main_finding(self):
        # No mediator, and Argon's fix changes more words, so the same fix is passed over in both reviews.
        replies = {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **gray and heavy with rain** today.")}
        ruling = None
        out, _ = two_lab_review(self.d, replies, {"gpt": {}, "argon": {}}, ruling, fails=(ur.MEDIATOR,))
        r = json.loads((out / "results.json").read_text())
        n = next(n for n, _, _, g in ur.ordered_findings(r) if g["rep"]["title"].startswith("Other fix"))
        with contextlib.redirect_stdout(io.StringIO()):
            ur.record_decisions(str(n), "ignore", "not this one", out)
        out, prompts = two_lab_review(self.d, replies, {"gpt": {}, "argon": {}}, ruling, fails=(ur.MEDIATOR,))
        r, g = self.groups(out)
        self.assertNotIn("declined", g["Sky color is wrong"])  # the main finding stays
        self.assertTrue(next(v for k, v in g.items() if k.startswith("Other fix")).get("declined"))
        self.assertNotIn("Other fix", prompts["review"]["gpt"])  # not passed to the panel as a declined point

    def test_the_page_refuses_a_panel_the_review_would_refuse(self):
        self.assertIn("two reviewers from labs other than the mediator's", ur.too_few_reviewers(["claude", "gpt"]))
        self.assertEqual(ur.too_few_reviewers(["claude", "gpt", "gemini"]), "")
        self.assertEqual(ur.too_few_reviewers(["claude"]), "")

    def test_fixes_that_do_the_same_thing_add_no_disputed_entry(self):
        out, _ = two_lab_review(
            self.d, {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **blue** today!")}, {"gpt": {}, "argon": {}},
            {"Sky color is wrong": "ruling: uphold\nfix: a\nreason: same\nproblem: same"})
        self.assertFalse([k for k in self.groups(out)[1] if k.startswith("Other fix")])

    def test_with_no_mediator_the_longer_fix_goes_under_disputed(self):
        long_fix = finding_text("Sky color is wrong", "The sky is green today.", "Green skies are rare.",
                                "The sky is ~~green~~ 🟢 **gray and heavy with rain** today.")
        out, _ = two_lab_review(self.d, {"gpt": long_fix, "argon": SKY()}, {"gpt": {}, "argon": {}},
                                fails=(ur.MEDIATOR,))
        other = self.groups(out)[1]["Other fix from GPT: Sky color is wrong"]  # gpt's longer fix was passed over
        self.assertIn("heavy with rain", other["rep"]["body"])
        self.assertEqual(other["rep"]["problem"], "Green skies are rare.")  # gpt's problem, with gpt's fix
        self.assertIn("fewest changed words, since no mediator answered", (out / "unified.md").read_text())

    def test_with_no_mediator_the_fix_with_fewest_changed_words_is_kept_with_its_problem(self):
        long_fix = finding_text("Sky color is wrong", "The sky is green today.", "Green skies are rare.",
                                "The sky is ~~green~~ 🟢 **gray and heavy with rain** today.")
        out, _ = two_lab_review(self.d, {"gpt": long_fix, "argon": SKY()}, {"gpt": {}, "argon": {}},
                                fails=(ur.MEDIATOR,))
        sky = self.groups(out)[1]["Sky color is wrong"]
        self.assertEqual(len(sky["alts"]), 1)
        self.assertEqual(sky["alts"][0]["by"], "argon")
        self.assertEqual(sky["rep"]["problem"], "The sky is blue, so the claim fails.")  # argon's, with its fix
        self.assertIn("**blue**", sky["rep"]["body"])
        md = (out / "unified.md").read_text()
        self.assertNotIn("**Fix a**", md)
        self.assertIn("fewest changed words", md)
        self.assertEqual(ur.changed_words("The sky is ~~green~~ 🟢 **blue** today."), 2)

    def test_with_no_mediator_an_accepted_fix_beats_a_shorter_rejected_one(self):
        long_fix = finding_text("Sky color is wrong", "The sky is green today.", "Green skies are rare.",
                                "The sky is ~~green~~ 🟢 **gray and heavy with rain** today.")
        out, _ = two_lab_review(self.d, {"gpt": long_fix, "argon": SKY()},
                                {"gpt": {"Sky color is wrong": "agree | disagree"}, "argon": {}}, fails=(ur.MEDIATOR,))
        sky = self.groups(out)[1]["Sky color is wrong"]
        self.assertEqual(sky["alts"][0]["by"], "gpt")
        self.assertEqual(sky["rep"]["problem"], "Green skies are rare.")

    def test_fixes_with_the_same_effect_keep_one_and_say_nothing(self):
        out, _ = two_lab_review(
            self.d, {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **blue** today!")}, {"gpt": {}, "argon": {}},
            {"Sky color is wrong": "ruling: uphold\nfix: a\nreason: same\nproblem: same"})
        r, g = self.groups(out)
        self.assertEqual(len(g["Sky color is wrong"]["alts"]), 1)
        self.assertNotIn("The fixes differ", (out / "unified.md").read_text())

    def test_same_fix_from_both_is_one_fix(self):
        out, prompts = two_lab_review(self.d, {"gpt": SKY(), "argon": SKY()}, {"gpt": {}, "argon": {}})
        r, g = self.groups(out)
        self.assertEqual(len(g["Sky color is wrong"]["alts"]), 1)
        self.assertIsNone(g["Sky color is wrong"]["fix_issue"])
        self.assertNotIn("mediate", prompts)

    def test_a_rejected_fix_can_be_replaced_by_the_mediators_own(self):
        out, _ = two_lab_review(
            self.d, {"gpt": WATER, "argon": GRASS}, {"argon": {"Water is not dry": "agree | disagree"}, "gpt": {}},
            {"Water is not dry": "ruling: uphold\nfix: c\nreason: Wet is too loose.\nproblem: same\n---\n"
                                 "Water is ~~dry~~ 🟢 **liquid at room temperature**."})
        r, g = self.groups(out)
        w = g["Water is not dry"]
        self.assertFalse(w["disputed"])
        self.assertTrue(w["alts"][0]["unreviewed"])
        self.assertIn("not reviewed by the panel", (out / "unified.md").read_text())
        self.assertIn("liquid", w["rep"]["body"])

    def test_a_long_problem_is_shortened_and_the_diff_kept(self):
        long = " ".join(["word"] * 40) + "."
        out, prompts = two_lab_review(
            self.d, {"gpt": finding_text("Long one", "Water is dry.", long, "Water is ~~dry~~ 🟢 **wet**."), "argon": GRASS},
            {"gpt": {}, "argon": {}}, {"Long one": "ruling: uphold\nfix: a\nreason: ok\nproblem: Water is wet."})
        r, g = self.groups(out)
        self.assertIn("TOO LONG", prompts["mediate"][ur.MEDIATOR])
        self.assertEqual(g["Long one"]["rep"]["problem"], "Water is wet.")
        self.assertEqual(g["Long one"]["rep"]["fix"], "Water is ~~dry~~ 🟢 **wet**.")

    def test_a_failed_mediator_is_not_replaced_by_a_reviewer(self):
        out, prompts = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS},
                                      {"argon": {"Sky color is wrong": "disagree | agree"}, "gpt": {}}, fails=(ur.MEDIATOR,))
        r, g = self.groups(out)
        self.assertEqual(list(prompts["mediate"]), [ur.MEDIATOR])
        self.assertIsNone(r["mediator"])
        self.assertIsNone(g["Sky color is wrong"]["ruling"])
        self.assertTrue(any(f["stage"] == "mediate" and f["model"] == ur.MEDIATOR for f in r["failures"]))

    def test_when_no_mediator_answers_disputed_findings_have_no_ruling(self):
        out, _ = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS},
                                {"argon": {"Sky color is wrong": "disagree | agree"}, "gpt": {}},
                                fails=(ur.MEDIATOR, ("mediate", "gpt"), ("mediate", "argon")))
        r, g = self.groups(out)
        self.assertTrue(g["Sky color is wrong"]["disputed"])
        self.assertFalse(g["Sky color is wrong"]["rejected"])
        self.assertIn("No ruling: the mediator did not answer.", (out / "unified.md").read_text())
        self.assertTrue(any(f["stage"] == "mediate" for f in r["failures"]))
        self.assertIsNone(r["mediator"])  # it ruled on nothing, so the review does not name it

    def test_a_logged_out_mediator_gets_no_call_and_leaves_no_ruling(self):
        with mock.patch.object(ur, "preflight", lambda ms: [m for m in ms if m != ur.MEDIATOR]):
            out, prompts = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS},
                                          {"argon": {"Sky color is wrong": "disagree | agree"}, "gpt": {}})
        r, g = self.groups(out)
        self.assertNotIn("mediate", prompts)
        self.assertIsNone(r["mediator"])
        self.assertIn("No ruling: the mediator did not answer.", (out / "unified.md").read_text())

    def test_three_reviewers_need_a_majority_and_still_get_a_mediator(self):
        out, prompts = two_lab_review(
            self.d, {"gpt": SKY() + GRASS, "argon": WATER, "gemini": "NO FINDINGS"},
            {"argon": {"Sky color is wrong": "agree | agree", "Grass speed unsupported": "partial | agree"},
             "gemini": {"Sky color is wrong": "disagree | agree", "Grass speed unsupported": "agree | agree",
                        "Water is not dry": "partial | agree"},
             "gpt": {"Water is not dry": "disagree | agree"}}, panel=("gpt", "argon", "gemini"))
        r, g = self.groups(out)
        self.assertFalse(g["Sky color is wrong"]["disputed"])  # gpt raised, argon agreed: 2 of 3
        self.assertFalse(g["Grass speed unsupported"]["disputed"])  # gpt raised, gemini agreed: 2 of 3
        self.assertTrue(g["Water is not dry"]["disputed"])  # argon raised it, partial and disagree: 1 of 3
        self.assertIn("mediate", prompts)

    def test_the_mediator_login_is_not_checked_when_nothing_needs_it(self):
        checked = []
        with mock.patch.object(ur, "preflight", lambda ms: checked.extend(ms) or ms):
            out, _ = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS}, {"gpt": {}, "argon": {}})
        self.assertNotIn(ur.MEDIATOR, checked)
        self.assertFalse(json.loads((out / "results.json").read_text())["failures"])

    def test_a_login_error_on_stdout_reads_as_not_logged_in(self):
        self.assertTrue(ur.AUTH_ERROR.search("Failed to authenticate: OAuth session expired and could not be refreshed"))

    def test_three_fixes_keep_their_letters_and_own_is_the_mediators(self):
        replies = {"gpt": SKY(), "argon": SKY("The sky is ~~green~~ 🟢 **gray** today."),
                   "gemini": SKY("The sky is ~~green~~ 🟢 **azure** today.")}
        out, prompts = two_lab_review(self.d, replies, {"gpt": {}, "argon": {}, "gemini": {}},
                                      {"Sky color is wrong": "ruling: uphold\nfix: c,b\nreason: Both are plausible.\nproblem: same"},
                                      panel=("gpt", "argon", "gemini"))
        sky = self.groups(out)[1]["Sky color is wrong"]
        self.assertEqual([a["label"] for a in sky["alts"]], ["c"])
        self.assertFalse(any(a.get("unreviewed") for a in sky["alts"]))  # c is a reviewer's fix here
        self.assertIn("own is your own fix", prompts["mediate"][ur.MEDIATOR])
        d2 = self.d / "own"
        d2.mkdir()
        out, _ = two_lab_review(d2, replies, {"gpt": {}, "argon": {}, "gemini": {}},
                                {"Sky color is wrong": "ruling: uphold\nfix: own\nreason: All three miss it.\nproblem: same\n---\n"
                                                       "The sky is ~~green~~ 🟢 **blue at noon** today."},
                                panel=("gpt", "argon", "gemini"))
        sky = self.groups(out)[1]["Sky color is wrong"]
        self.assertTrue(sky["alts"][0]["unreviewed"])
        self.assertIn("blue at noon", sky["rep"]["body"])

    def test_items_the_mediator_skips_stay_unruled(self):
        def med(m, title):
            return "ruling: uphold\nfix: a\nreason: Real.\nproblem: same" if title == "Sky color is wrong" else None
        out, prompts = two_lab_review(self.d, {"gpt": SKY() + GRASS, "argon": WATER},
                                      {"argon": {"Sky color is wrong": "disagree | agree",
                                                 "Grass speed unsupported": "disagree | agree"}, "gpt": {}}, med)
        g = self.groups(out)[1]
        self.assertEqual(g["Sky color is wrong"]["ruling"]["by"], ur.MEDIATOR)
        self.assertIsNone(g["Grass speed unsupported"]["ruling"])
        self.assertFalse(g["Grass speed unsupported"]["rejected"])
        self.assertEqual(list(prompts["mediate"]), [ur.MEDIATOR])

    def test_a_problem_of_two_sentences_is_shortened(self):
        self.assertEqual(ur.sentences("No baseline is given, e.g. last year."), 1)
        self.assertEqual(ur.sentences("No baseline. The claim fails."), 2)
        out, prompts = two_lab_review(
            self.d, {"gpt": finding_text("Two sentences", "Water is dry.", "Water is wet. The claim fails.",
                                         "Water is ~~dry~~ 🟢 **wet**."), "argon": GRASS},
            {"gpt": {}, "argon": {}}, {"Two sentences": "ruling: uphold\nfix: a\nreason: ok\nproblem: Water is wet, so the claim fails."})
        self.assertIn("TOO LONG", prompts["mediate"][ur.MEDIATOR])
        self.assertEqual(self.groups(out)[1]["Two sentences"]["rep"]["problem"], "Water is wet, so the claim fails.")

    def test_a_deletion_only_fix_from_the_mediator_is_kept(self):
        out, _ = two_lab_review(
            self.d, {"gpt": WATER, "argon": GRASS}, {"argon": {"Water is not dry": "agree | disagree"}, "gpt": {}},
            {"Water is not dry": "ruling: uphold\nfix: own\nreason: Cut the claim.\nproblem: same\n---\n~~Water is dry.~~"})
        w = self.groups(out)[1]["Water is not dry"]
        self.assertTrue(w["alts"][0]["unreviewed"])
        self.assertEqual(w["alts"][0]["fix"], "~~Water is dry.~~")

    def test_a_missing_mediator_cli_leaves_no_ruling(self):
        out, prompts = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS},
                                      {"argon": {"Sky color is wrong": "disagree | agree"}, "gpt": {}}, missing=(ur.MEDIATOR,))
        r, g = self.groups(out)
        self.assertNotIn("mediate", prompts)
        self.assertIsNone(g["Sky color is wrong"]["ruling"])
        self.assertTrue(any(f["stage"] == "preflight" and f["model"] == ur.MEDIATOR for f in r["failures"]))

    def test_a_disputed_finding_says_when_its_fix_is_the_mediators_own(self):
        out, _ = two_lab_review(
            self.d, {"gpt": SKY(), "argon": GRASS}, {"argon": {"Sky color is wrong": "partial | disagree"}, "gpt": {}},
            {"Sky color is wrong": "ruling: uphold\nfix: own\nreason: Real.\nproblem: same\n---\n"
                                   "The sky is ~~green~~ 🟢 **gray** today."})
        self.assertIn("own, not reviewed by the panel", (out / "unified.md").read_text())

    def test_a_disputed_one_word_fix_is_not_a_typo(self):
        typo = finding_text("Typo", "Water is dry.", "Spelling.", "Water is ~~dry~~ 🟢 **dyr**.", "Nitpick")
        out, _ = two_lab_review(self.d, {"gpt": typo, "argon": GRASS}, {"argon": {"Typo": "partial | agree"}, "gpt": {}})
        g = self.groups(out)[1]["Typo"]
        self.assertTrue(g["disputed"])
        self.assertFalse(ur.is_typo(g))

    def test_three_reviewer_main_review_findings_are_tagged_majority(self):
        out, _ = two_lab_review(self.d, {"gpt": GRASS, "argon": WATER, "gemini": SKY()},
                                {"argon": {"Grass speed unsupported": "agree | agree"},
                                 "gemini": {"Grass speed unsupported": "partial | agree"}, "gpt": {}},
                                panel=("gpt", "argon", "gemini"))
        g = self.groups(out)[1]["Grass speed unsupported"]
        self.assertFalse(g["disputed"])
        self.assertEqual(ur.vote_tag(g), "Majority")

    def test_applied_and_ignore_take_a_fix_letter(self):
        out, _ = two_lab_review(self.d, {"gpt": SKY(), "argon": GRASS}, {"gpt": {}, "argon": {}})
        with contextlib.redirect_stdout(io.StringIO()) as s:
            ur.record_decisions("1b", "applied", "test", out)
        self.assertIn("recorded as applied", s.getvalue())

    def test_iterate_skips_disputed_findings_and_differing_fixes(self):
        base = {"status": None, "form": "edit", "where": "draft", "applicable": True, "slot": False, "severity": "Minor"}
        self.assertTrue(ur.auto_applies({**base, "tag": "Unanimous"}))
        self.assertFalse(ur.auto_applies({**base, "tag": "Disputed"}))
        self.assertFalse(ur.auto_applies({**base, "tag": "Fixes differ"}))


class NotesFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.notes = self.d / "notes" / "review.md"

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, replies, votes=None, mediation=None):
        out, _ = two_lab_review(self.d, replies, votes or {"gpt": {}, "argon": {}}, mediation)
        with mock.patch.object(ur.runtime, "log", lambda *a: None):
            return ur.write_notes(self.d / "memo.md", out), out

    def test_first_review_writes_sets_in_order_and_an_about_section(self):
        path, _ = self.review({"gpt": SKY() + GRASS, "argon": WATER},
                              {"argon": {"Grass speed unsupported": "partial | agree"}, "gpt": {}})
        self.assertEqual(path, self.notes)
        t = path.read_text()
        self.assertTrue(t.startswith("# Review of memo.md\n"))
        self.assertIn("### B1. Sky color is wrong", t)
        self.assertIn("### B2. Water is not dry", t)
        self.assertIn("### X1. Grass speed unsupported (Minor)", t)
        self.assertIn("*Intro · memo.md, line 3*", t)
        self.assertLess(t.index("## Minor"), t.index("## Disputed"))
        self.assertLess(t.index("## Disputed"), t.index("## About this review"))
        self.assertIn("- Open items: 2 Minor, 1 Disputed.", t)
        self.assertIn("ties broken by Claude Opus", t)  # the scripted mediator ruled on X1

    def test_an_open_item_the_mediator_drops_is_closed(self):
        self.review({"gpt": SKY(), "argon": WATER})
        path, _ = self.review({"gpt": SKY(), "argon": WATER}, {"argon": {"Sky color is wrong": "disagree | agree"}, "gpt": {}},
                              {"Sky color is wrong": "ruling: drop\nfix: a\nreason: Green is right here.\nproblem: same"})
        t = path.read_text()
        self.assertNotIn("### B1.", t)
        self.assertIn("B1 (dropped by the mediator)", t)

    def test_a_lost_id_map_does_not_duplicate_items(self):
        self.review({"gpt": SKY(), "argon": WATER})
        ur.notes_map_file().unlink()
        path, _ = self.review({"gpt": SKY(), "argon": WATER})
        t = path.read_text()
        self.assertEqual(t.count("Sky color is wrong"), 1)
        self.assertEqual(t.count("Water is not dry"), 1)
        self.assertNotIn("### B3.", t)

    def test_two_findings_with_one_title_keep_their_own_items(self):
        cite = lambda q: finding_text("Missing citation", q, "No source is given.", f"{q[:-1]} 🟢 **{{{{citation: Author, year}}}}**.")
        self.review({"gpt": cite("The sky is green today.") + cite("Water is dry."), "argon": GRASS})
        t = self.notes.read_text()
        sky_id = re.search(r"### (B\d)\. Missing citation.*\n\*Intro · memo.md, line 3\*", t).group(1)
        water_id = re.search(r"### (B\d)\. Missing citation.*\n\*Intro · memo.md, line 7\*", t).group(1)
        path, _ = self.review({"gpt": cite("Water is dry."), "argon": GRASS})
        t = path.read_text()
        self.assertIn(ur.NOT_RAISED, t.split(f"### {sky_id}.")[1].split("###")[0])
        self.assertNotIn(ur.NOT_RAISED, t.split(f"### {water_id}.")[1].split("###")[0])

    def test_a_lost_id_map_after_a_close_does_not_reuse_the_id(self):
        self.review({"gpt": SKY(), "argon": WATER})
        f = self.d / "memo.md"
        f.write_text(f.read_text().replace("The sky is green today.", "The sky is blue today."))
        self.review({"gpt": WATER, "argon": WATER})  # B1 closes as applied
        self.assertIn("<!-- next ids: A1, B3, C1, X1 -->", self.notes.read_text())
        ur.notes_map_file().unlink()
        path, _ = self.review({"gpt": WATER + GRASS, "argon": WATER})
        t = path.read_text()
        self.assertIn("### B3. Grass speed unsupported", t)
        self.assertNotIn("### B1.", t)

    def test_notes_for_a_converted_file_go_beside_the_file_the_user_named(self):
        _, out = self.review({"gpt": SKY(), "argon": WATER})
        src = self.d / "elsewhere" / "paper.docx"
        src.parent.mkdir()
        src.write_text("x")
        with mock.patch.object(ur.runtime, "log", lambda *a: None):
            path = ur.write_notes(self.d / "memo.md", out, src)
        self.assertEqual(path, src.parent / "notes" / "review.md")
        self.assertTrue(path.read_text().startswith("# Review of paper.docx\n"))

    def test_an_applied_item_does_not_take_a_finding_on_the_same_sentence(self):
        f = self.d / "memo.md"
        f.write_text("# Intro\n\nThe sky is green today, and the clouds over the hills are purple.\n\nGrass grows slowly.\n")
        s = "The sky is green today, and the clouds over the hills are purple."
        color = finding_text("Sky color is wrong", s, "The sky is blue.", s.replace("~~", "").replace("green", "~~green~~ 🟢 **blue**"))
        clouds = lambda q: finding_text("Clouds are not purple", q, "Clouds are white.", q.replace("purple", "~~purple~~ 🟢 **white**"))
        self.review({"gpt": color, "argon": clouds(s)})
        t = self.notes.read_text()
        clouds_id = re.search(r"### (B\d)\. Clouds", t).group(1)
        f.write_text(f.read_text().replace("green", "blue"))  # the author applies the color fix
        path, _ = self.review({"gpt": GRASS, "argon": clouds(s.replace("green", "blue"))})
        t = path.read_text()
        self.assertNotIn("Sky color is wrong", t.split("## About")[0])
        self.assertIn(f"### {clouds_id}. Clouds are not purple", t)
        self.assertNotIn(ur.NOT_RAISED, t.split(f"### {clouds_id}.")[1].split("###")[0])
        self.assertEqual(t.count("Clouds are not purple"), 1)

    def test_dropped_findings_stay_out_of_the_notes_file(self):
        path, _ = self.review({"gpt": SKY(), "argon": WATER}, {"argon": {"Sky color is wrong": "disagree | agree"}, "gpt": {}},
                              {"Sky color is wrong": "ruling: drop\nfix: a\nreason: The sky is green here.\nproblem: same"})
        t = path.read_text()
        self.assertNotIn("### B1. Sky", t)
        self.assertNotIn("Sky color is wrong", t)
        self.assertNotIn("Next free ids", t)

    def test_a_math_code_block_fix_shows_rendered(self):
        fix = "```markdown\n$$p = 1.$$\n$$p = 1. \\tag{1}$$\n```"
        out = ur.rendered_fix(fix)
        self.assertNotIn("```", out)
        self.assertIn("🔴 **Now**\n\n$$p = 1.$$\n\n🟢 **Proposed**\n\n$$p = 1. \\tag{1}$$", out)
        anchor = "```markdown\n[x](#a)\n[x](#b)\n```"
        self.assertEqual(ur.rendered_fix(anchor), anchor)

    def test_only_whole_line_equations_render(self):
        for src in ("For $x > 0$, it holds.\nFor $x \\ge 0$, it holds.",  # prose with inline math
                    "> $$p = 1.$$\n> $$p = 1. \\tag{1}$$",                # a quoted equation
                    "See \\autoref{a}.\nSee \\autoref{b}."):             # a macro, no math
            block = f"```markdown\n{src}\n```"
            self.assertEqual(ur.rendered_fix(block), block)
        self.assertIn("$$p = 1. \\tag{1}$$", ur.rendered_fix("```markdown\n$p = 1.$\n$p = 1. \\tag{1}$\n```"))

    def test_every_math_block_in_a_fix_renders(self):
        two = "```markdown\n$$a.$$\n$$a. \\tag{1}$$\n```\n\n```markdown\n$$b.$$\n$$b. \\tag{2}$$\n```"
        out = ur.rendered_fix(two)
        self.assertNotIn("```", out)
        self.assertEqual(out.count("🔴 **Now**"), 2)

    def test_a_rendered_pair_is_not_read_as_a_diff(self):
        body = "problem: Number it.\n\n🔴 **Now**\n\n$$p = 1.$$\n\n🟢 **Proposed**\n\n$$p = 1. \\tag{1}$$"
        old, why = ur.diff_parts(body)
        self.assertIsNone(old)
        self.assertIn("by hand", why)
        self.assertFalse(ur.note_resolved({"fix": body.partition("\n\n")[2]}, "The proposed rule."))

    def test_item_prints_the_stored_code_block_and_the_notes_show_it_rendered(self):
        g = {"rep": {"title": "T", "quote": "", "body": "", "problem": "Number it.",
                     "fix": "```markdown\n$$p.$$\n$$p. \\tag{1}$$\n```"}, "alts": [], "votes": {}}
        with mock.patch.object(ur, "problem_of", lambda r: r["problem"]), \
                mock.patch.object(ur, "fix_of", lambda r: r["fix"]):
            self.assertIn("```markdown", ur.finding_md(g, {}, ruling=False, render=False))
            self.assertNotIn("```", ur.finding_md(g, {}, ruling=False))

    DRAFT_TABLE = "Intro.\n\n| Name | Value |\n|---|---|\n| Alpha | One two three four. |\n| Beta | a \\| b |\n"

    def test_a_table_row_edit_shows_under_the_draft_header(self):
        fix = "```markdown\n| Alpha | One two three four. |\n| Alpha | One two {{slot}} four. |\n```"
        out = ur.rendered_fix(fix, self.DRAFT_TABLE)
        self.assertNotIn("```", out)
        self.assertEqual(out, "| Name | Value |\n|---|---|\n| Alpha | One two ~~three~~ 🟢 **{{slot}}** four. |")

    def test_a_table_row_not_in_the_draft_gets_a_blank_header(self):
        out = ur.rendered_fix("```markdown\n| A | x y z |\n| A | x y w |\n```")
        self.assertTrue(out.startswith("| | |\n|---|---|\n| A | x y ~~z~~ 🟢 **w** |"))

    def test_an_escaped_pipe_stays_in_its_cell(self):
        fix = "```markdown\n| Beta | a \\| b |\n| Beta | a \\| c |\n```"
        self.assertIn("| Beta | a \\| ~~b~~ 🟢 **c** |", ur.rendered_fix(fix, self.DRAFT_TABLE))

    def test_a_rewritten_cell_is_struck_whole(self):
        self.assertEqual(ur.cell_diff("one two three", "four five six"), "~~one two three~~ 🟢 **four five six**")

    def test_a_table_row_edit_in_a_nitpick_bullet_is_one_line(self):
        fix = "```markdown\n| Alpha | One two three four. |\n| Alpha | One two {{slot}} four. |\n```"
        out = ur.rendered_fix(fix, self.DRAFT_TABLE, inline=True)
        self.assertEqual(out, "*Value*: One two ~~three~~ 🟢 **{{slot}}** four.")

    def test_item_keeps_a_table_row_edit_as_stored(self):
        g = {"rep": {"title": "T", "quote": "", "body": "", "problem": "P.",
                     "fix": "```markdown\n| A | x |\n| A | y |\n```"}, "alts": [], "votes": {}}
        with mock.patch.object(ur, "problem_of", lambda r: r["problem"]), \
                mock.patch.object(ur, "fix_of", lambda r: r["fix"]):
            self.assertIn("```markdown\n| A | x |", ur.finding_md(g, {}, ruling=False, render=False))

    def test_new_ids_read_in_draft_order(self):
        path, _ = self.review({"gpt": WATER + GRASS, "argon": SKY()})
        t = path.read_text()
        self.assertLess(t.index("B1. Sky"), t.index("B2. Grass"))
        self.assertLess(t.index("B2. Grass"), t.index("B3. Water"))

    def test_rereview_keeps_annotations_refreshes_lines_and_closes_applied_items(self):
        self.review({"gpt": SKY(), "argon": WATER})
        t = self.notes.read_text()
        t = t.replace("Water is ~~dry~~ 🟢 **wet**.\n", "Water is ~~dry~~ 🟢 **wet**.\n\nAuthor: check the source first.\n")
        self.notes.write_text(t)
        f = self.d / "memo.md"
        # The author applies the sky fix and adds two lines at the top, so Water moves down.
        f.write_text("# Intro\n\nNew line.\n\nThe sky is blue today.\n\nGrass grows slowly.\n\nWater is dry.\n")
        path, _ = self.review({"gpt": WATER, "argon": GRASS})
        t = path.read_text()
        self.assertNotIn("Sky color is wrong", t.split("## About")[0])
        self.assertIn("Author: check the source first.", t)
        self.assertIn("### B2. Water is not dry", t)
        self.assertIn("memo.md, line 9*", t)
        self.assertIn("### B3. Grass speed unsupported", t)  # next free id, never B1 again
        self.assertLess(t.index("B3. Grass"), t.index("B2. Water"))  # draft order
        self.assertIn("Closed this round: B1 (applied)", t)
        self.assertTrue(any(d["decision"] == "applied" and d["title"] == "Sky color is wrong"
                            for d in ur.load_decisions().get(str(f), [])))

    def test_an_item_not_raised_again_stays_and_is_marked(self):
        self.review({"gpt": SKY(), "argon": WATER})
        path, _ = self.review({"gpt": WATER, "argon": GRASS})
        t = path.read_text()
        self.assertIn("### B1. Sky color is wrong", t)
        self.assertIn(ur.NOT_RAISED, t.split("### B1.")[1].split("###")[0])
        path, _ = self.review({"gpt": SKY(), "argon": WATER})  # raised again: the mark goes
        self.assertNotIn(ur.NOT_RAISED, path.read_text().split("### B1.")[1].split("###")[0])

    def test_an_old_ruling_line_goes_when_the_item_is_raised_again(self):
        self.review({"gpt": SKY(), "argon": WATER})
        old = "*Argon disagreed with the fix. Claude Opus keeps it: The sky is blue.*"
        mine = "*The fixes differ in wording, but keep the original.*"
        t = self.notes.read_text()
        head = t.index("### B1.")
        end = t.index("\n### ", head + 1)
        self.notes.write_text(t[:end] + f"\n\n{old}\n\n{mine}" + t[end:])
        path, _ = self.review({"gpt": SKY(), "argon": WATER})
        item = path.read_text().split("### B1.")[1].split("###")[0]
        self.assertNotIn(old, item)
        self.assertIn(mine, item)

    def test_an_old_ruling_line_goes_from_an_item_not_raised_again(self):
        self.review({"gpt": SKY(), "argon": WATER})
        old = "*The fixes differ. Claude Opus prefers Fix a: shorter.*"
        t = self.notes.read_text()
        end = t.index("\n### ", t.index("### B1.") + 1)
        self.notes.write_text(t[:end] + f"\n\n{old}" + t[end:])
        path, _ = self.review({"gpt": WATER, "argon": GRASS})
        item = path.read_text().split("### B1.")[1].split("###")[0]
        self.assertIn(ur.NOT_RAISED, item)
        self.assertNotIn(old, item)

    def test_a_problem_that_names_the_labels_still_applies(self):
        body = "problem: Use 🔴 **Now** and 🟢 **Proposed** labels.\n\nThe sky is ~~green~~ 🟢 **blue**."
        self.assertEqual(ur.diff_parts(body), ("The sky is green.", "The sky is blue."))

    def test_a_hand_edited_heading_is_left_as_written(self):
        self.review({"gpt": SKY(), "argon": WATER})
        t = self.notes.read_text().replace("### B2. Water is not dry", "### Water, my note")
        self.notes.write_text(t)
        path, _ = self.review({"gpt": SKY(), "argon": WATER})
        t = path.read_text()
        self.assertIn("### Water, my note", t)
        self.assertEqual(t.count("Water is not dry"), 0)  # not re-added under a new id either
        self.assertIn("heading not in the", t)

    def test_notes_for_a_second_draft_in_the_folder_get_their_own_file(self):
        self.review({"gpt": SKY(), "argon": WATER})
        other = self.d / "other.md"
        other.write_text("x")
        self.assertEqual(ur.notes_path(other), self.d / "notes" / "review-other.md")
        self.assertEqual(ur.notes_path(self.d / "memo.md"), self.notes)


if __name__ == "__main__":
    unittest.main()
