---
name: plain-words
description: Rewrite a draft so it uses only common English words. A checker flags every word outside a list of about 3,250 common headwords (NGSL 1.2 plus the American Oxford 3000 and a few everyday words), and you propose numbered replacement edits in the unified-review diff format. Use when the user asks to make a document plainer, simpler, or readable to a general or non-native audience, to use only common or the most frequent English words, to check a text against NGSL or the Oxford 3000, or to apply numbered plain-words edits.
---

# Plain words

This skill lives in the agent-council repo (`skills/plain-words/`). `install.sh`
links it into Claude Code, Codex, and Cursor, puts the checker on the PATH as
`plain-words`, and downloads the two lists that cannot be committed here.

## The word list

A word passes when it, or its regular inflection (plural, past, -ing),
is on one of these lists:

- **NGSL 1.2** and its 52-word supplement (days, months, number words), the
  ~2,800 most frequent lemmas in a 273M-word corpus of modern English, with every
  inflected form. Browne, Culligan, and Phillips, CC BY-SA 4.0,
  [newgeneralservicelist.com](https://www.newgeneralservicelist.com/). Committed
  in `lists/`.
- **The American Oxford 3000**, which adds everyday concrete words that corpus
  counts underweight (apple, airport, birthday, laptop). Oxford University Press
  owns it, so `plain-words fetch` downloads it to `~/.local/share/plain-words/`.
- **The xkcd Simple Writer list** (Munroe), which adds a few dozen words NGSL
  lacks (shrug, nod, frown, hug), minus the words in `lists/blocked.txt`. Also
  downloaded.

Contractions, possessives, and hyphenated compounds of allowed words pass. A
derived word does not pass because its root does: "reviewer" fails though
"review" passes, and "unchanged" fails though "change" passes. Comparatives
pass only when the list has them: NGSL lists them for its adjectives, the Oxford
list does not. The checker skips
front matter, code, math, URLs, link targets and reference link labels, HTML, citation keys, footnote
marks, Pandoc attributes, and single letters.

Words the draft needs and defines (a technical term, a product name) go in
`plain-words-allow.txt` next to the draft, one per line. The checker reads that
file on every run.

## Proposing edits

1. Run `plain-words check FILE`. If it warns that a downloaded list is missing,
   run `plain-words fetch` first. The output lists each line with its words that
   are not on the list, then the words seen only capitalized (names, acronyms,
   and words that only start sentences).
2. Read the whole draft before proposing anything, so each replacement fits its
   context and the draft's terms stay consistent: replace a repeated term the
   same way everywhere.
3. For each flagged word, choose one:
   - **Replace** it with a listed word that keeps the meaning ("productivity" →
     "output").
   - **Rewrite** the phrase when no single word fits ("catering" → "food for
     meetings"). Keep the sentence's claim and its strength.
   - **Keep** it when the draft is about that thing and no plain wording names
     it (a disease, a method, a person). Propose adding it to the allow file,
     and propose a short definition at first use when the draft lacks one.
   - **Fix** it when it is a typo ("recieve").
   Names and acronyms are kept unless the user asks otherwise.
4. Check every replacement before proposing it: pipe the new sentence to
   `plain-words check -`. A replacement must pass, and it must follow the user's
   writing rules (their CLAUDE.md: no em dashes, no semicolons, no hedges).
5. Write the edits to `<name>.plain-words.md` next to the draft, then show it to
   the user (in the Claude app, open it in the file pane). Do not edit the draft
   yet.

## Output format

Follow unified-review's diff format, without severity groups:

```markdown
# Plain words: draft.md

List: NGSL 1.2 + Oxford 3000 (US) + xkcd. 4 words flagged on 3 lines, 3 edits, 1 kept.

## Edits

1. **Why, L7.** Our own survey found that 90% of the team want the change, which shows it will raise ~~productivity~~ 🟢 **output**.
2. ...

## Kept

- **neuron** (L3, L12): the subject of the draft, defined at L3. Add to `plain-words-allow.txt`.
```

- Number the edits sequentially in draft order, so the user can say "apply 2, 5".
  Put several flagged words in one sentence into one edit.
- Each edit names its section and line, then shows the sentence as an inline
  revision: ~~struck~~ old words, 🟢 **bold** new words, everything else plain.
  Quote only the sentence that changes, not the whole paragraph.
- Add a few words after the diff only when the meaning shifts ("narrower:
  'output' drops the per-hour sense"). Say nothing when it does not.
- Under **Kept**, list each kept word with its lines and the reason.

## Applying edits

When the user says "apply 1, 3" (or "apply all"):

1. Re-read the draft. The user edits files directly, so the text may have moved.
   If an edit's struck text is no longer there, say so and skip it.
2. Make each edit at its current line. Add kept words the user approved to
   `plain-words-allow.txt`.
3. Run `plain-words check FILE` again and report what still fails.
4. Do not commit.
