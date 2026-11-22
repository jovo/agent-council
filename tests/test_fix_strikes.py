"""Tests for fix-strikes. Run: python3 -m unittest discover tests"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "fix_strikes.py"
spec = importlib.util.spec_from_file_location("fix_strikes", SCRIPT)
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


class Check(unittest.TestCase):
    def problems(self, text):
        return [p for _, p, _ in fs.check(text)]

    def test_good_spans_pass(self):
        for text in [
            "the tokens it covers ~~and the rest~~.",
            "~~(v2)~~ is gone",
            "a ~~b~~ 🟢 **c**.",
            "~~company, so what~~ 🟢 **company. What**",
            "said “x”~~, and y~~ here",  # punctuation before the opener
            "no strikes at all",
        ]:
            self.assertEqual(self.problems(text), [], text)

    def test_glued_punctuation_opener(self):
        self.assertEqual(self.problems("the company~~, so what~~ 🟢 **. What**"),
                         ["opening ~~ is glued to a word and followed by punctuation"])

    def test_inner_spaces(self):
        self.assertEqual(self.problems("a~~ b~~ c"), ["space after opening ~~"])
        self.assertEqual(self.problems("a ~~b ~~c"), ["space before closing ~~"])

    def test_unpaired(self):
        self.assertEqual(self.problems("a ~~b c"), ["unpaired ~~"])

    def test_code_is_skipped(self):
        self.assertEqual(self.problems("`x~~, y~~`\n\n```\nfoo~~, bar~~\n```\n"), [])

    def test_valid_nested_span_is_kept(self):
        # GFM matches the inner pair, so only the outer opener is bad.
        self.assertEqual(self.problems("~~a ~~b~~"), ["unpaired ~~"])
        self.assertEqual(fs.fix("~~a ~~b~~"), "~~a ~~b~~")

    def test_links_and_urls_are_skipped(self):
        for text in ["[x](foo~~,bar~~)", "<https://a.b/c~~,d~~>", "see https://a.b/c~~,d~~ now"]:
            self.assertEqual(fs.fix(text), text)
        # A word that is part of a link is not widened, only reported.
        text = "[company~~, so what~~](u)"
        self.assertEqual(fs.fix(text), text)
        self.assertEqual(len(fs.check(text)), 1)

    def test_fence_closes_only_on_its_own_marker(self):
        text = "~~~\ncode\n``` not closing\nmore~~, old~~\n~~~\n"
        self.assertEqual(self.problems(text), [])
        self.assertEqual(self.problems("````\nx\n```\nmore~~, old~~\n````\n"), [])

    def test_indented_code_is_skipped(self):
        self.assertEqual(self.problems("    foo~~, bar~~\n"), [])
        # A list continuation line is prose.
        self.assertEqual(len(fs.check("- item\n    foo~~, bar~~")), 1)

    def test_line_numbers(self):
        self.assertEqual(fs.check("ok\n\nthe end~~, and x~~.")[0][0], 3)


class Fix(unittest.TestCase):
    def test_widens_into_following_addition(self):
        self.assertEqual(
            fs.fix("across the company~~, so what~~ 🟢 **. What** your people know"),
            "across the ~~company, so what~~ 🟢 **company. What** your people know")

    def test_addition_starting_with_a_word(self):
        self.assertEqual(fs.fix("invite your team~~, with no~~ 🟢 **plus** AI"),
                         "invite your ~~team, with no~~ 🟢 **team plus** AI")

    def test_widens_without_addition(self):
        self.assertEqual(fs.fix("the end~~, and x~~."), "the ~~end, and x~~ 🟢 **end**.")

    def test_moves_inner_spaces_out(self):
        self.assertEqual(fs.fix("the tokens it covers~~ and the rest~~."),
                         "the tokens it covers ~~and the rest~~.")
        self.assertEqual(fs.fix("a ~~b ~~c"), "a ~~b~~ c")
        self.assertEqual(fs.fix("eyes.**~~ .~~**"), "eyes. **~~.~~**")
        self.assertEqual(fs.fix("a **~~b ~~**c"), "a **~~b~~** c")

    def test_several_in_one_paragraph(self):
        text = "one~~, two~~ 🟢 **. Two** and three~~, four~~ 🟢 **. Four**"
        self.assertEqual(fs.check(fs.fix(text)), [])

    def test_leaves_good_text_and_unpaired_alone(self):
        for text in ["a ~~b~~ 🟢 **c**.", "a ~~b c", "```\nx~~, y~~\n```\n"]:
            self.assertEqual(fs.fix(text), text)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "n.md"
            f.write_text("the end~~, and x~~.\n")
            r = subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("n.md:1:", r.stderr)
            r = subprocess.run([sys.executable, str(SCRIPT), "--fix", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(f.read_text(), "the ~~end, and x~~ 🟢 **end**.\n")


class ReviewScript(unittest.TestCase):
    def test_parsed_findings_get_repaired(self):
        from importlib.machinery import SourceFileLoader
        ur = SourceFileLoader("ur_strikes", str(SCRIPT.parent / "unified-review")).load_module()
        body = "problem: The sentence is long.\n\nthe company~~, so what~~ 🟢 **. What** people know"
        self.assertIn("the ~~company, so what~~ 🟢 **company. What**", ur.strip_end(body))


if __name__ == "__main__":
    unittest.main()
