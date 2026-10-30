"""Tests for the plain-words checker. Run: python3 -m unittest discover tests"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills/plain-words/plain_words.py"


def load(data_dir):
    with mock.patch.dict(os.environ, {"PLAIN_WORDS_DATA": str(data_dir)}):
        spec = importlib.util.spec_from_file_location("plain_words", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class PlainWordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir()
        (self.data / "oxford-3000-us.txt").write_text("apple\nbirthday\nlong-term\n")
        (self.data / "xkcd-simplewriter.js").write_text(
            'window.__WORDS = "shrug|shrugged|fuck|fucking|don’t";')
        self.pw = load(self.data)
        self.words, self.missing = self.pw.load_words()

    def tearDown(self):
        self.tmp.cleanup()

    def flagged(self, text):
        return self.pw.check(text, self.words)[0]

    def test_lists_combine_and_blocked_words_drop(self):
        self.assertEqual(self.missing, [])
        for w in ("abandoned", "monday", "apple", "long-term", "shrugged", "don't"):
            self.assertIn(w, self.words)
        self.assertNotIn("fuck", self.words)
        self.assertNotIn("fucking", self.words)

    def test_inflections_contractions_and_hyphens_pass(self):
        text = "The apples, two birthdays. They shrug. It won't, it can't, it's the dog's. Well-known."
        self.assertEqual(self.flagged(text), {})

    def test_unlisted_words_flag_with_line_numbers(self):
        self.assertEqual(self.flagged("We obfuscate.\n\nThey obfuscate twice."), {"obfuscate": [1, 3]})

    def test_markup_is_skipped(self):
        text = ("---\ntitle: Zyzzyva\n---\n"
                "Text $\\zeta_{qq}$ and `qqfoo` [link](https://qqbar.example) [@Qqkey20] {#sec:qq}.\n"
                "```\nqqcode\n```\n$$\nqqmath\n$$\n<!-- qqnote -->\n")
        self.assertEqual(self.flagged(text), {})

    def test_words_seen_only_capitalized_are_names(self):
        flagged, names = self.pw.check("Zorblat met us. The zibber ran. Zibber again.", self.words)
        self.assertEqual(names, {"zorblat"})
        self.assertIn("zibber", flagged)

    def test_allow_file_next_to_draft(self):
        draft = Path(self.tmp.name) / "draft.md"
        draft.write_text("The neuron fires.\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.pw.main(["check", str(draft)]), 1)
        (Path(self.tmp.name) / "plain-words-allow.txt").write_text("neuron\nfire\n")
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.pw.main(["check", str(draft)]), 0)

    def test_missing_downloads_warn_and_still_check(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        pw = load(empty)
        words, missing = pw.load_words()
        self.assertEqual(missing, ["oxford-3000-us.txt", "xkcd-simplewriter.js"])
        self.assertIn("abandon", words)


if __name__ == "__main__":
    unittest.main()
