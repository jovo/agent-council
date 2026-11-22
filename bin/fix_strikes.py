#!/usr/bin/env python3
"""Find and repair ~~strikeout~~ spans that render as bare tildes.

GitHub-flavored Markdown opens a strikeout only on a left-flanking `~~` and
closes it only on a right-flanking one (CommonMark's delimiter rules). An
opener glued to a word and followed by punctuation, as in `company~~, so~~`,
is not left-flanking, so the reader sees the tildes. Neither is an opener
followed by a space, nor a closer that follows a space.

    fix-strikes FILE...         report bad spans, exit 1 if any
    fix-strikes --fix FILE...   repair what it can in place, report the rest

Repairs follow the unified-review rules. A deletion that opens on punctuation
glued to the word before it widens to take in that word, and the word goes
back in the 🟢 addition that follows (or a new one): `company~~, so what~~ 🟢
**. What**` becomes `~~company, so what~~ 🟢 **company. What**`. A space just
inside either `~~` moves outside it. Fenced code blocks and inline code are
skipped, since a diff of markup source is shown there on purpose.
"""
import re
import sys
import unicodedata

FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"(`+).+?\1", re.S)
ADDITION = re.compile(r"\A(\s*)🟢 \*\*(.*?)\*\*", re.S)


def _punct(c):
    return unicodedata.category(c)[0] in "PS"


def _space(c):
    return c == "" or c.isspace()


def _tildes(text):
    """Positions of each `~~` outside inline code, skipping runs of three or more."""
    code = [m.span() for m in CODE_SPAN.finditer(text)]
    out = []
    for m in re.finditer(r"~+", text):
        if len(m.group()) == 2 and not any(a <= m.start() < b for a, b in code):
            out.append(m.start())
    return out


def _problems(text):
    """(opener, closer, problem) for each bad span in one paragraph, closer None if unpaired."""
    pos = _tildes(text)
    out = []
    for i in range(0, len(pos) - 1, 2):
        s, e = pos[i], pos[i + 1]
        before = text[s - 1] if s else ""
        first, last = text[s + 2], text[e - 1]
        after = text[e + 2] if e + 2 < len(text) else ""
        if first.isspace():
            out.append((s, e, "space after opening ~~"))
        elif _punct(first) and not (_space(before) or _punct(before)):
            out.append((s, e, "opening ~~ is glued to a word and followed by punctuation"))
        elif last.isspace():
            out.append((s, e, "space before closing ~~"))
        elif _punct(last) and not (_space(after) or _punct(after)):
            out.append((s, e, "closing ~~ follows punctuation and is glued to a word"))
    if len(pos) % 2:
        out.append((pos[-1], None, "unpaired ~~"))
    return out


def _repair(text, s, e, problem):
    """Text with one bad span repaired, or None if this problem has no safe repair."""
    inner = text[s + 2:e]
    # A bolded deletion, **~~x~~**, moves the space outside the bold too.
    if problem == "space after opening ~~":
        k = len(inner) - len(inner.lstrip())
        a = s - 2 if text[s - 2:s] == "**" else s
        return text[:a] + inner[:k] + text[a:s] + "~~" + text[s + 2 + k:]
    if problem == "space before closing ~~":
        k = len(inner) - len(inner.rstrip())
        b = e + 4 if text[e + 2:e + 4] == "**" else e + 2
        return text[:e - k] + text[e:b] + inner[len(inner) - k:] + text[b:]
    if problem.startswith("opening"):
        w = s
        while w and not text[w - 1].isspace():
            w -= 1
        word = text[w:s]
        if "~~" in word or "**" in word or "🟢" in word:
            return None
        tail = text[e + 2:]
        m = ADDITION.match(tail)
        if m:
            add = m.group(2)
            joined = word + add if not add or _punct(add[0]) else word + " " + add
            tail = f"{m.group(1)}🟢 **{joined}**" + tail[m.end():]
        else:
            tail = f" 🟢 **{word}**" + tail
        return text[:w] + "~~" + word + inner + "~~" + tail
    return None


def _paragraphs(text):
    """(start, end) of each stretch of prose between blank lines and code fences."""
    spans, start, fenced, at = [], 0, False, 0
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            if not fenced and at > start:
                spans.append((start, at))
            fenced = not fenced
            start = at + len(line)
        elif not fenced and not line.strip():
            if at > start:
                spans.append((start, at))
            start = at + len(line)
        at += len(line)
    if not fenced and at > start:
        spans.append((start, at))
    return spans


def check(text):
    """[(line, problem, excerpt)] for each bad span in a Markdown text."""
    out = []
    for a, b in _paragraphs(text):
        para = text[a:b]
        for s, e, problem in _problems(para):
            line = text.count("\n", 0, a + s) + 1
            out.append((line, problem, para[max(0, s - 20):(e + 2 if e is not None else s + 2) + 20].replace("\n", " ")))
    return out


def fix(text):
    """Text with every repairable bad span repaired."""
    for a, b in reversed(_paragraphs(text)):
        para = text[a:b]
        for _ in range(50):  # each pass repairs one span, then rescans the paragraph
            for s, e, problem in _problems(para):
                new = _repair(para, s, e, problem) if e is not None else None
                if new is not None:
                    para = new
                    break
            else:
                break
        text = text[:a] + para + text[b:]
    return text


def main(argv):
    do_fix = "--fix" in argv
    files = [a for a in argv if a != "--fix"]
    if not files or any(a.startswith("-") for a in files):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    bad = 0
    for f in files:
        text = open(f, encoding="utf-8").read()
        if do_fix:
            new = fix(text)
            if new != text:
                open(f, "w", encoding="utf-8").write(new)
                print(f"{f}: repaired strikeouts")
            text = new
        for line, problem, excerpt in check(text):
            bad += 1
            print(f"{f}:{line}: {problem}: …{excerpt}…", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
