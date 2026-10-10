import json
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rb = SourceFileLoader("review_bench", str(ROOT / "bin" / "review-bench")).load_module()


class Bench(unittest.TestCase):
    TEXT = "# T\n\nThe first sentence holds. The planted claim overreaches badly. The last sentence holds.\n"
    PASSAGE = "The planted claim overreaches badly."

    def results(self, groups, findings):
        return {"groups": groups, "findings": findings}

    def group(self, quote, severity="Major", **kw):
        return {"rep": {"title": "T", "quote": quote, "body": "Point."}, "severity": severity, "members": [],
                "rejected": False, **kw}

    def test_every_case_places_once(self):
        cases = json.loads((ROOT / "bench" / "plants.json").read_text())["cases"]
        self.assertEqual(len({c["id"] for c in cases}), len(cases))
        for c in cases:
            text = (ROOT / "bench" / "drafts" / c["draft"]).read_text()
            self.assertIn(c["new"], rb.plant(text, c))
            self.assertIn(c["tier"], rb.TIERS)

    def test_plant_needs_one_match(self):
        with self.assertRaises(ValueError):
            rb.plant("a a", {"id": "x", "draft": "d", "old": "a", "new": "b"})

    def test_reported_with_tier(self):
        r = self.results([self.group("planted claim overreaches")], [{"id": "A1", "quote": "planted claim overreaches"}])
        self.assertEqual(rb.match(r, self.TEXT, self.PASSAGE),
                         {"raised": True, "reported": True, "tier": "Major", "finding": "T"})

    def test_raised_but_rejected_or_elsewhere(self):
        r = self.results([self.group("planted claim overreaches", rejected=True), self.group("The first sentence holds.")],
                         [{"id": "A1", "quote": "planted claim overreaches"}])
        self.assertEqual(rb.match(r, self.TEXT, self.PASSAGE)["raised"], True)
        self.assertEqual(rb.match(r, self.TEXT, self.PASSAGE)["reported"], False)
        r = self.results([self.group("")], [{"id": "A1", "quote": ""}])  # a whole-draft finding does not count
        self.assertEqual(rb.match(r, self.TEXT, self.PASSAGE)["raised"], False)

    def test_summary_and_report(self):
        rows = [{"id": "a", "planted_tier": "Major", "ok": True, "raised": True, "reported": True, "tier": "Major",
                 "control": False, "finding": "F"},
                {"id": "b", "planted_tier": "Major", "ok": True, "raised": True, "reported": False, "tier": None,
                 "control": False, "finding": None},
                {"id": "c", "planted_tier": "Nitpick", "ok": False}]
        s = rb.summarize(rows)
        self.assertEqual(s["Major"], {"n": 2, "raised": 2, "reported": 1, "tier_correct": 1, "lost_at_vote": 1, "control": 0})
        self.assertEqual(s["All"]["n"], 2)
        meta = {"date": "d", "commit": "abc", "dirty": False, "panel": ["claude"], "drafts": 1, "minutes": 3,
                "control": True, "failed": ["c"]}
        md = rb.report(meta, rows, s)
        self.assertIn("| Major | 2/2 | 1/2 | 1/1 | 1/2 | 0/2 |", md)
        self.assertIn("| c | Nitpick | review failed |", md)


if __name__ == "__main__":
    unittest.main()
