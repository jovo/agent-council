#!/usr/bin/env python3
"""Flag the words in a draft that are not on a list of common English words.

    plain_words.py check FILE [--allow WORDS]   flag words by line (FILE may be - for stdin)
                                                --allow takes a file or comma-separated words
    plain_words.py sentences FILE [--max N] [--mean N]
                                                give the mean sentence length and list each
                                                sentence over --max words (defaults 25 and 15)
    plain_words.py fetch                        download the Oxford and xkcd lists

The list is the union of:
  - NGSL 1.2 and its supplement (Browne, Culligan, and Phillips, CC BY-SA 4.0), in lists/.
  - The American Oxford 3000 (Oxford University Press), downloaded by `fetch`.
  - The xkcd Simple Writer list (Randall Munroe), downloaded by `fetch`, minus lists/blocked.txt.

Words in a file named plain-words-allow.txt next to the draft (in the current folder for
stdin), and in --allow, also pass, with their inflections.
Exit status: 0 when every word passes, 1 when some do not, 2 on a usage error.

`sentences` counts the words in each sentence of running prose: paragraphs and list items,
not headings, tables, or block quotes. Inline code and math count as one word each. Code
blocks, display math, links, and citations do not count.
Its exit status is 0 when no sentence is over --max and the mean is at most --mean, else 1.
"""
import argparse
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LISTS = HERE / "lists"
DATA = Path(os.environ.get("PLAIN_WORDS_DATA")
            or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "plain-words")
DOWNLOADS = {
    "oxford-3000-us.txt": "https://raw.githubusercontent.com/ittuann/The-Oxford-5000-Word-Lists/"
                          "main/American%20Oxford%203000.txt",
    "xkcd-simplewriter.js": "https://xkcd.com/simplewriter/words.js",
}
ALLOW_FILE = "plain-words-allow.txt"

# Contractions whose stem is not itself a word.
CONTRACTIONS = {"won't": "will", "can't": "can", "shan't": "shall", "ain't": "be"}
CLITICS = ("n't", "'s", "'re", "'ve", "'ll", "'d", "'m")
# Pieces of split contractions that NGSL lists as forms (isn from isn't). They are not words.
FRAGMENTS = {"ain", "aren", "couldn", "didn", "doesn", "don", "hadn", "hasn", "haven", "isn",
             "mightn", "mustn", "needn", "shan", "shouldn", "wasn", "weren", "wouldn", "wo", "ca",
             "d", "ll", "m", "re", "s", "t", "ve"}


def norm(word):
    return word.strip().lower().replace("’", "'")


def fetch():
    DATA.mkdir(parents=True, exist_ok=True)
    for name, url in DOWNLOADS.items():
        with urllib.request.urlopen(url, timeout=30) as r:
            (DATA / name).write_bytes(r.read())
        print(f"fetched {DATA / name}")


def blocked():
    return [norm(line) for line in (LISTS / "blocked.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def load_words():
    """Return (words, missing): every allowed word form, and the downloaded lists not found."""
    words = set()
    for name in ("ngsl-1.2.csv", "ngsl-supplement.csv"):
        for line in (LISTS / name).read_text().splitlines():
            if line and not line.startswith("#"):
                words.update(norm(w) for w in line.split(","))
    missing = []
    oxford = DATA / "oxford-3000-us.txt"
    if oxford.exists():
        words.update(norm(w) for w in oxford.read_text().splitlines())
    else:
        missing.append(oxford.name)
    xkcd = DATA / "xkcd-simplewriter.js"
    if xkcd.exists():
        m = re.search(r'"([^"]*)"', xkcd.read_text())
        bad = tuple(blocked())
        words.update(w for w in map(norm, m.group(1).split("|") if m else []) if not w.startswith(bad))
    else:
        missing.append(xkcd.name)
    words.discard("")
    return words - FRAGMENTS, missing


def stems(word):
    """Possible headwords for a regular inflection: plural, past, or -ing.

    No -er or -est: they would also pass agent nouns (reviewer from review). NGSL already
    lists the comparatives and superlatives of its adjectives.
    """
    out = []
    for suffix, repl in (("ies", "y"), ("ied", "y"), ("es", ""), ("s", ""),
                         ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e")):
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            stem = word[: -len(suffix)] + repl
            if suffix == "es" and not stem.endswith(("s", "z", "x", "sh", "ch", "o")):
                continue  # robes is robe + s, not rob + es
            out.append(stem)
            if suffix in ("ed", "ing") and not repl and len(stem) > 2 and stem[-1] == stem[-2]:
                out.append(stem[:-1])  # stopped, running
    return out


def allowed(word, words):
    if len(word) == 1 or word in words:  # single letters are variables and list labels
        return True
    if word in CONTRACTIONS:
        return CONTRACTIONS[word] in words
    for clitic in CLITICS:
        if word.endswith(clitic) and len(word) > len(clitic):
            return allowed(word[: -len(clitic)], words)
    if any(s in words for s in stems(word)):
        return True
    return "-" in word and all(allowed(part, words) for part in word.split("-") if part)


# Spans that are not prose: masked with spaces so line numbers stay put.
SKIP = [
    re.compile(r"\A---\n.*?\n---\n", re.S),                       # YAML front matter
    re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1", re.S | re.M),  # fenced code
    re.compile(r"\$\$.*?\$\$", re.S),                              # display math
    re.compile(r"(?<![\\$])\$(?!\s)(?:[^$\\\n]|\\.)*(?<![\\$\s])\$(?!\d)"),  # inline math, not $10 to $20
    re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)"),                # inline code
    re.compile(r"<!--.*?-->", re.S),                               # HTML comments
    re.compile(r"<[^>\n]+>"),                                      # HTML tags
    re.compile(r"\]\([^)\n]*\)"),                                  # link targets
    re.compile(r"\]\[[^\]\n]*\]"),                                 # reference link labels
    re.compile(r"^ {0,3}\[(?!\^)[^\]\n]+\]:.*$", re.M),            # reference link definitions
    re.compile(r"https?://\S+"),                                   # bare URLs
    re.compile(r"\[\^[^\]\n]+\]"),                                 # footnote marks
    re.compile(r"-?@[\w:.#$%&+?<>~/-]+"),                          # citation keys
    re.compile(r"\{[#.][^}\n]*\}"),                                # Pandoc attributes
]
TOKEN = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


def mask(text):
    for pattern in SKIP:
        text = pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return text


def roots(word):
    """The word without a clitic, and its possible stems, so obfuscated meets obfuscate."""
    for clitic in CLITICS:
        if word.endswith(clitic) and len(word) > len(clitic):
            word = word[: -len(clitic)]
            break
    return {word, *stems(word)}


def check(text, words):
    """Return {word: [line numbers]} for each word not allowed, and the set of words seen only capitalized."""
    flagged, lower_seen = {}, set()
    for n, line in enumerate(mask(text).splitlines(), 1):
        for m in TOKEN.finditer(line):
            tok = m.group(0)
            word = norm(tok)
            if tok[0].islower():
                lower_seen.update(roots(word))
            if not allowed(word, words):
                lines = flagged.setdefault(word, [])
                if n not in lines:
                    lines.append(n)
    names = {w for w in flagged if not roots(w) & lower_seen}
    return flagged, names


# Words that end in a period without ending the sentence. Single letters (initials) too.
ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "cf", "al", "fig", "figs", "eq", "eqs", "no", "dr",
                 "mr", "mrs", "ms", "prof", "st", "jr", "sr", "inc", "ltd", "co", "approx", "ref"}
SENTENCE_END = re.compile(r"""[.!?]["'”’)\]*_]*(?=\s+["'“‘(\[*_]*[A-Z0-9])""")
COUNTED = re.compile(r"[A-Za-z0-9]+(?:['’.,-][A-Za-z0-9]+)*")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


INLINE = SKIP[3:5]  # inline math and inline code: each reads as one word


def as_word(m):
    """Mask a span as the one-word placeholder X, keeping its length."""
    return "X" + re.sub(r"[^\n]", " ", m.group(0)[1:])


def blocks(text):
    """Running prose as a list of blocks, each a list of (line number, text, original text):
    paragraphs and list items. Inline code and math become X. Headings (and lines that are
    all bold), tables, block quotes, rules, and the other spans in SKIP are left out."""
    view = text
    for pattern in INLINE:
        view = pattern.sub(as_word, view)
    out, cur = [], []
    for n, (line, orig) in enumerate(zip(mask(view).splitlines(), text.splitlines()), 1):
        s = line.strip()
        label = re.fullmatch(r"(\*\*|__)[^*_]+\1:?", s)  # a bold line used as a heading
        if not s or label or s.startswith(("#", "|", ">")) or re.fullmatch(r"[-*_=\s]{3,}", s):
            if cur:
                out.append(cur)
            cur = []
            continue
        if LIST_ITEM.match(line) and cur:
            out.append(cur)
            cur = []
        m = LIST_ITEM.match(line)
        a = m.end() if m else 0
        a += len(line[a:]) - len(line[a:].lstrip())
        b = len(orig.rstrip())  # the masked line can end in spaces where the original has code
        cur.append((n, line[a:b], orig[a:b]))
    if cur:
        out.append(cur)
    return out


def sentences(text):
    """Return (line number, word count, sentence) for each sentence of running prose."""
    out = []
    for block in blocks(text):
        joined, original, starts = "", "", []
        for n, s, orig in block:
            starts.append((len(joined), n))
            joined += s + " "
            original += orig + " "
        spans, start = [], 0
        for m in SENTENCE_END.finditer(joined):
            if m.group(0)[0] == ".":
                last = re.search(r"([A-Za-z][A-Za-z.]*)$", joined[start:m.start()])
                if last and (len(last.group(1)) == 1 or last.group(1).lower() in ABBREVIATIONS):
                    continue
            spans.append((start, m.end()))
            start = m.end()
        spans.append((start, len(joined)))
        for a, b in spans:
            seg = joined[a:b]
            count = len(COUNTED.findall(seg))
            if count:
                first = a + len(seg) - len(seg.lstrip())
                line = max(n for at, n in starts if at <= first)
                out.append((line, count, " ".join(original[a:b].split())))
    return out


def report_sentences(text, longest, mean_target):
    """Print the mean length and each sentence over `longest` words. Return the exit status."""
    found = sentences(text)
    if not found:
        print("no sentences found.")
        return 0
    mean = sum(c for _, c, _ in found) / len(found)
    long = [s for s in found if s[1] > longest]
    print(f"{len(found)} sentences, mean {mean:.1f} words (target {mean_target:g} or fewer). "
          f"{len(long)} over {longest} words.")
    for n, count, s in long:
        print(f"L{n} ({count} words): {s}")
    return 1 if long or mean > mean_target else 0


def read_allow(source):
    """Words from an allow file (# starts a comment), or from a comma-separated string."""
    if not source:
        return set()
    path = Path(source)
    if path.is_file():
        text = re.sub(r"#.*", "", path.read_text())
    elif path.suffix or os.sep in str(source):
        raise SystemExit(f"plain-words: no allow file {source}")
    else:
        text = str(source)
    return {norm(w) for w in re.findall(r"[A-Za-z'’-]+", text)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--allow", help="file of extra words to pass, or comma-separated words")
    s = sub.add_parser("sentences")
    s.add_argument("file")
    s.add_argument("--max", type=int, default=25, help="longest sentence, in words (default 25)")
    s.add_argument("--mean", type=float, default=15, help="target mean, in words (default 15)")
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        fetch()
        return 0
    if args.cmd == "sentences":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
        return report_sentences(text, args.max, args.mean)
    words, missing = load_words()
    if missing:
        print(f"warning: missing {', '.join(missing)}: run `plain-words fetch`. Checking without them.",
              file=sys.stderr)
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
    words |= read_allow(args.allow)
    folder = Path.cwd() if args.file == "-" else Path(args.file).resolve().parent
    if (folder / ALLOW_FILE).is_file():
        words |= read_allow(folder / ALLOW_FILE)
    flagged, names = check(text, words)
    if not flagged:
        print("all words pass.")
        return 0
    by_line = {}
    for word, lines in flagged.items():
        if word not in names:
            for n in lines:
                by_line.setdefault(n, []).append(word)
    source = text.splitlines()
    print(f"{len(flagged) - len(names)} words not on the list, on {len(by_line)} lines. "
          f"{len(names)} more appear only capitalized.")
    for n in sorted(by_line):
        print(f"L{n}: {', '.join(by_line[n])}\n    {source[n - 1].strip()}")
    if names:
        print("\nSeen only capitalized (names, acronyms, or sentence-initial words):")
        for word in sorted(names):
            print(f"  {word}: L{', L'.join(map(str, flagged[word]))}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
