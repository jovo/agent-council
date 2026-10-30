#!/usr/bin/env python3
"""Flag the words in a draft that are not on a list of common English words.

    plain_words.py check FILE [--allow WORDS]   flag words by line (FILE may be - for stdin)
    plain_words.py fetch                        download the Oxford and xkcd lists

The list is the union of:
  - NGSL 1.2 and its supplement (Browne, Culligan, and Phillips, CC BY-SA 4.0), in lists/.
  - The American Oxford 3000 (Oxford University Press), downloaded by `fetch`.
  - The xkcd Simple Writer list (Randall Munroe), downloaded by `fetch`, minus lists/blocked.txt.

Words in a file named plain-words-allow.txt next to the draft, and in --allow, also pass.
Exit status: 0 when every word passes, 1 when some do not, 2 on a usage error.
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


def fetch():
    DATA.mkdir(parents=True, exist_ok=True)
    for name, url in DOWNLOADS.items():
        with urllib.request.urlopen(url, timeout=30) as r:
            (DATA / name).write_bytes(r.read())
        print(f"fetched {DATA / name}")


def blocked():
    return [w for w in (LISTS / "blocked.txt").read_text().split() if not w.startswith("#")]


def load_words():
    """Return (words, missing): every allowed word form, and the downloaded lists not found."""
    words = set()
    for name in ("ngsl-1.2.csv", "ngsl-supplement.csv"):
        for line in (LISTS / name).read_text().splitlines():
            if line and not line.startswith("#"):
                words.update(w.strip().lower() for w in line.split(",") if w.strip())
    missing = []
    oxford = DATA / "oxford-3000-us.txt"
    if oxford.exists():
        words.update(w.strip().lower() for w in oxford.read_text().splitlines() if w.strip())
    else:
        missing.append(oxford.name)
    xkcd = DATA / "xkcd-simplewriter.js"
    if xkcd.exists():
        m = re.search(r'"([^"]*)"', xkcd.read_text())
        bad = tuple(blocked())
        words.update(w.replace("’", "'") for w in m.group(1).split("|") if not w.startswith(bad))
    else:
        missing.append(xkcd.name)
    return words, missing


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
            out.append(stem)
            if not repl and len(stem) > 2 and stem[-1] == stem[-2]:  # stopped, bigger
                out.append(stem[:-1])
    return out


def allowed(word, words):
    if word in words:
        return True
    if word in CONTRACTIONS:
        return CONTRACTIONS[word] in words
    for clitic in CLITICS:
        if word.endswith(clitic) and len(word) > len(clitic):
            return allowed(word[: -len(clitic)], words)
    if "-" in word:
        return all(allowed(part, words) for part in word.split("-") if part)
    return any(s in words for s in stems(word))


# Spans that are not prose: masked with spaces so line numbers stay put.
SKIP = [
    re.compile(r"\A---\n.*?\n---\n", re.S),          # YAML front matter
    re.compile(r"^(```|~~~).*?^\1", re.S | re.M),     # fenced code
    re.compile(r"\$\$.*?\$\$", re.S),                 # display math
    re.compile(r"(?<![\\$])\$[^$\n]+\$"),             # inline math
    re.compile(r"`[^`\n]+`"),                         # inline code
    re.compile(r"<!--.*?-->", re.S),                  # HTML comments
    re.compile(r"<[^>\n]+>"),                         # HTML tags
    re.compile(r"\]\([^)\n]*\)"),                     # link targets
    re.compile(r"\]\[[^\]\n]*\]"),                     # reference link labels
    re.compile(r"^ {0,3}\[[^\]\n]+\]:.*$", re.M),         # reference link definitions
    re.compile(r"https?://\S+"),                      # bare URLs
    re.compile(r"\[\^[^\]\n]+\]"),                    # footnote marks
    re.compile(r"-?@[\w:.#$%&+?<>~/-]+"),             # citation keys
    re.compile(r"\{[#.][^}\n]*\}"),                   # Pandoc attributes
]
TOKEN = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


def mask(text):
    for pattern in SKIP:
        text = pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return text


def check(text, words):
    """Return {word: [line numbers]} for each word not allowed, and the set of words seen only capitalized."""
    flagged, lower_seen = {}, set()
    for n, line in enumerate(mask(text).splitlines(), 1):
        for m in TOKEN.finditer(line):
            tok = m.group(0).replace("’", "'")
            word = tok.lower()
            if len(word) == 1:  # variables and list letters
                continue
            if tok[0].islower():
                lower_seen.add(word)
            if not allowed(word, words):
                lines = flagged.setdefault(word, [])
                if n not in lines:
                    lines.append(n)
    names = {w for w in flagged if w not in lower_seen}
    return flagged, names


def read_allow(path):
    return {w.lower() for w in re.findall(r"[A-Za-z'-]+", Path(path).read_text())} if path else set()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--allow", help="file of extra words to pass")
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        fetch()
        return 0
    words, missing = load_words()
    if missing:
        print(f"warning: missing {', '.join(missing)}: run `plain-words fetch`. Checking without them.",
              file=sys.stderr)
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
    words |= read_allow(args.allow)
    if args.file != "-":
        local = Path(args.file).resolve().parent / ALLOW_FILE
        if local.exists():
            words |= read_allow(local)
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
