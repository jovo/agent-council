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
            'window.__WORDS = "shrug|shrugged|fuck|fucking|don’t|thereabouts|isthmus";')
        self.pw = load(self.data)
        self.words, self.missing = self.pw.load_words()

    def tearDown(self):
        self.tmp.cleanup()

    def flagged(self, text):
        return self.pw.check(text, self.words)[0]

    def main(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.pw.main(argv)

    def test_lists_combine_and_blocked_words_drop(self):
        self.assertEqual(self.missing, [])
        for w in ("abandoned", "monday", "apple", "long-term", "shrugged", "don't"):
            self.assertIn(w, self.words)
        self.assertNotIn("fuck", self.words)
        self.assertNotIn("fucking", self.words)
        # The comment in blocked.txt blocks nothing: these start with "the" and "is".
        self.assertIn("thereabouts", self.words)
        self.assertIn("isthmus", self.words)

    def test_contraction_pieces_are_not_words(self):
        self.assertNotIn("isn", self.words)
        self.assertEqual(self.flagged("on a reed"), {"reed": [1]})

    def test_inflections_contractions_and_hyphens_pass(self):
        text = "The apples, two birthdays. They shrug. It won't, it can't, it's the dog's. Well-known."
        self.assertEqual(self.flagged(text), {})

    def test_unlisted_words_flag_with_line_numbers(self):
        self.assertEqual(self.flagged("We obfuscate.\n\nThey obfuscate twice."), {"obfuscate": [1, 3]})

    def test_derived_agent_nouns_flag(self):
        self.assertEqual(self.flagged("The reviewer and the marketer."), {"reviewer": [1], "marketer": [1]})
        self.assertEqual(self.flagged("Bigger cities, the biggest."), {})

    def test_es_and_doubling_only_where_english_uses_them(self):
        self.assertEqual(self.flagged("two robes and canes, two putts"),
                         {"robes": [1], "canes": [1], "putts": [1]})
        self.assertEqual(self.flagged("boxes, wishes, stopped, running"), {})

    def test_single_letters_and_their_compounds_pass(self):
        self.assertEqual(self.flagged("Compare x's value with the x-value and a t-shirt."), {})
        self.assertEqual(self.flagged("the x-axis"), {"x-axis": [1]})

    def test_markup_is_skipped(self):
        text = ("---\ntitle: Zyzzyva\n---\n"
                "Text $\\zeta_{qq}$ and `qqfoo` [link](https://qqbar.example) [@Qqkey20] {#sec:qq}.\n"
                "```\nqqcode\n```\n$$\nqqmath\n$$\n<!-- qqnote -->\n"
                "See [the list][qq-ref].\n\n[qq-ref]: https://qqbar.example \"Qq title\"\n"
                "Use `` `qqtick` `` here.\n"
                "- item\n\n  ````md\n  ```\n  qqnested\n  ```\n  ````\n")
        self.assertEqual(self.flagged(text), {})

    def test_prose_that_looks_like_markup_is_checked(self):
        self.assertEqual(self.flagged("Claim.[^1]\n\n[^1]: We obfuscate this.\n"), {"obfuscate": [3]})
        self.assertEqual(self.flagged("It costs $10 to obfuscate and $20 more."), {"obfuscate": [1]})

    def test_words_seen_only_capitalized_are_names(self):
        flagged, names = self.pw.check("Zorblat met us. The zibber ran. Zibber again.", self.words)
        self.assertEqual(names, {"zorblat"})
        self.assertIn("zibber", flagged)
        _, names = self.pw.check("We obfuscate.\nObfuscated text. Zorblat's cat.", self.words)
        self.assertEqual(names, {"zorblat's"})

    def test_allow_file_next_to_draft(self):
        draft = Path(self.tmp.name) / "draft.md"
        draft.write_text("The neurons fire. The co-authors agree.\n")
        self.assertEqual(self.main(["check", str(draft)]), 1)
        (Path(self.tmp.name) / "plain-words-allow.txt").write_text("# terms\nneuron\nco-author\n")
        self.assertEqual(self.main(["check", str(draft)]), 0)

    def test_allow_words_on_the_command_line_and_stdin(self):
        draft = Path(self.tmp.name) / "draft.md"
        draft.write_text("The neuron and the glia.\n")
        self.assertEqual(self.main(["check", str(draft), "--allow", "neuron,glia"]), 0)
        with self.assertRaises(SystemExit):
            self.main(["check", str(draft), "--allow", "missing.txt"])
        (Path(self.tmp.name) / "plain-words-allow.txt").write_text("neuron\n")
        with mock.patch("sys.stdin", io.StringIO("The neuron.")), \
                mock.patch.object(self.pw.Path, "cwd", return_value=Path(self.tmp.name)):
            self.assertEqual(self.main(["check", "-"]), 0)

    def test_empty_xkcd_file_does_not_crash(self):
        (self.data / "xkcd-simplewriter.js").write_text("")
        words, missing = self.pw.load_words()
        self.assertEqual(missing, [])
        self.assertIn("abandon", words)

    def test_missing_downloads_warn_and_still_check(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        pw = load(empty)
        words, missing = pw.load_words()
        self.assertEqual(missing, ["oxford-3000-us.txt", "xkcd-simplewriter.js"])
        self.assertIn("abandon", words)

    def counts(self, text):
        return [(n, c) for n, c, _ in self.pw.sentences(text)]

    def test_sentences_split_and_count_words(self):
        text = "One two three. Four five!\nSix seven, eight? \"Nine ten,\" she said."
        self.assertEqual(self.counts(text), [(1, 3), (1, 2), (2, 3), (2, 4)])

    def test_abbreviations_and_initials_do_not_end_sentences(self):
        text = "See e.g. the fit in Fig. 2 by Dr. Smith. R. Jacob wrote it, et al. agree."
        self.assertEqual(self.counts(text), [(1, 10), (1, 7)])

    def test_sentence_wrapped_over_lines_keeps_its_first_line(self):
        text = "Intro.\n\nThis sentence starts here\nand ends on the next line. Short one."
        self.assertEqual(self.counts(text), [(1, 1), (3, 10), (4, 2)])

    def test_headings_labels_tables_quotes_and_markup_do_not_count(self):
        text = ("# A long heading that is not a sentence at all\n\n**2. Subheading**\n\n"
                "| a | table | row |\n\n> A quoted source sentence here.\n\n"
                "Math $a + b = c$ and `code here` stay out [@Cohen80].\n")
        self.assertEqual(self.counts(text), [(9, 6)])  # code and math are one word each

    def test_sentence_that_starts_with_code_is_its_own_sentence(self):
        text = "The repo has it. `install.sh`\nlinks it here."
        self.assertEqual([s for _, _, s in self.pw.sentences(text)],
                         ["The repo has it.", "`install.sh` links it here."])

    def test_list_items_are_separate_and_bold_lead_ins_split(self):
        text = "- **Lead in.** Then the rest\n  wraps here.\n- Next item with no period\n"
        self.assertEqual(self.counts(text), [(1, 2), (1, 5), (3, 5)])

    def test_sentences_command_reports_long_sentences_and_mean(self):
        draft = Path(self.tmp.name) / "draft.md"
        draft.write_text("Short one here. Word " + " ".join(["word"] * 29) + ".\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.pw.main(["sentences", str(draft)]), 1)
        self.assertIn("2 sentences, mean 16.5 words (target 15 or fewer). 1 over 25 words.",
                      out.getvalue())
        self.assertIn("L1 (30 words): Word word", out.getvalue())
        self.assertEqual(self.main(["sentences", str(draft), "--max", "30", "--mean", "17"]), 0)
        self.assertEqual(self.main(["sentences", str(draft), "--max", "30"]), 1)  # mean too high


if __name__ == "__main__":
    unittest.main()
