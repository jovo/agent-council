---
name: unified-review
description: Review a draft with two models from different labs (GPT and Gemini by default) that vote on each other's findings, with Claude Opus breaking ties, merged into one review in draft order and written to notes/review.md, with an optional web fact-check. One model or a three-lab panel also works. Use when the user asks for a unified, combined, panel, tri-model, or multi-model review or feedback on a file. Also use when the user asks to address, apply, fix, accept, or skip numbered items (such as 3, 7, or K5) from a unified review or fact-check. Also use when the user asks to iterate (review, apply the changes, and review again) for some number of rounds. Also use for any review of or feedback on a draft, even by one model, since its Reviewer rules set what to flag and the output format.
---

# Unified review

This skill lives in the agent-council repo (`skills/unified-review/SKILL.md`).
`install.sh` links it into `~/.claude/skills`, `~/.codex/skills`, and
`~/.cursor/skills`, so Claude Code, Codex, and Cursor share one copy. Edit it
in the repo.

For a review by you alone, without the script, follow the Reviewer rules at the end of this skill. The script gives the same rules to its models.

Run the script on the file(s) the user names:

```bash
unified-review [-n "extra focus"] [-p PANEL] [--context FILE]... [--verify] [-o OUTDIR] FILE [FILE...]
```

If the user attaches or names supporting material with the request (reviewer
comments, a call for proposals, a source paper, a style guide), pass it with
`--context FILE`, once per file. The panel reads it but does not review it.
Text files and PDFs work. An attachment that exists only in the chat must be
saved to a temporary file first. Images are not supported yet: say so.

The file to review can itself be a PDF. The script first converts it to
Markdown with Claude, keeping its links, under
`~/.local/share/unified-review/runs/converted/`, and reviews the Markdown, so
findings cite lines and the review page opens. It checks the conversion word by
word against the PDF's text and prints what is missing or added. Report that
line to the user. The same PDF reuses its Markdown, keeping the user's edits.
The Markdown is a copy: edits there do not reach the PDF's source document.
`--no-md` reviews the PDF as is: plain prose goes as text, and a PDF with
figures, tables, or equations is opened by each panelist directly. Findings
then cite pages, and accepted changes go in the source document.

The file can also be a Word file (.docx). pandoc converts it to Markdown in the
same folder, with tracked changes accepted, and the review page edits that
copy. Download on the page gives the review as Markdown, or the edited draft in
the format it came in. A Word file comes back as the original with each edit
written in as a tracked change, so its comments, citation fields, styles, and
layout are untouched. Edits it cannot place (inside an equation, citation, or
footnote mark, new formatting, new table cells) are listed for the user to make
by hand. A PDF comes back through make-pdf.

The default is two models from different labs, `gpt` (GPT-5.6 Luna, low
effort, via codex) and `argon` (Gemini 4 Argon Medium, via cursor-agent), with
Claude Opus as mediator. `-p` takes any one model or subset: short names
`argon`, `claude` (Sonnet), `gpt` (GPT-5.6 Luna, low effort), `gemini` (Gemini
3.8 Flash Low), `grok`, or `harness:model[@effort]`. `-p gpt` reviews with one
model alone. `-p claude,gpt,gemini` is a three-lab panel that votes by
majority, with no mediator. If a model fails, Claude Sonnet stands in
automatically, and Grok 4.7 Low Fast if Claude fails too. Pass `-p` only when the user names a model or a panel. Pass `--verify` only when the user asks for a
fact-check or claim verification.

How it works: each panelist reviews without web search. Each finding is a
problem (one sentence, at most 25 words) and a fix (the inline diff). With two
or more, every panelist then votes on the other models' findings, never its
own, with reviewers anonymized: once on the problem (agree, partial, disagree)
and once on the fix (agree, disagree). A single model skips the vote, and the
review says it reviewed alone.

With two reviewers (the default), a finding goes in the main review only when
both stand behind its problem: both raised it, or the other voted agree. A
partial or disagree vote makes it disputed. Claude Opus then mediates, and
raises no findings of its own:
- A disputed finding is upheld or dropped. Upheld ones follow the main review
  under Disputed, in the same severity groups and draft order, each with the
  dissenting vote and the ruling. Dropped ones are listed in one line each.
- Where both accept a problem but the fixes differ, or one rejected the
  other's fix, the mediator keeps one fix, shows both (Fix a and Fix b, its pick
  first), or writes its own, marked as not reviewed by the panel.
- It shortens a problem over 25 words and leaves the diff as it is.
If the mediator fails, Disputed lists its findings without a ruling, and the
review says so. With three or more reviewers, the script reports a finding when
two models stand behind it (a second model raised it, or another voted agree or
partial), and there is no mediator.

The script groups duplicates and writes `unified.md` in the run folder and the
notes file (below) in the draft's folder:
findings grouped by severity (Major, Minor, Nitpick), each group in
draft order with its section, file, and line, then Disputed, then a short list
of findings not reported. There is no cap on findings. When the file was reviewed before,
`unified.md` opens with a "Since the last review" section: three counts and
their finding numbers, resolved (an earlier finding whose passage changed and
that no panelist raised again, numbered as in the last review), persisting,
and new. Report these counts to the user before the findings.

- The review takes about 1 to 3 minutes, then the notes file opens in the
  default app for .md files (set UNIFIED_REVIEW_OPEN_APP to change). With `--verify`, a web fact-check (stronger Claude and
  GPT models) runs in the background for about 2 more minutes, writes
  `factcheck.md` in draft order with each claim's verdict and sources, sends a
  macOS notification, and opens it. `unified.md` is not changed by the
  fact-check. Run the command with a timeout of at least 5 minutes. Do not wait
  for the fact-check before showing the review.
- One model can take minutes longer than the others. The script waits for it,
  and if a model fails it finishes with the rest and lists the failure in
  `unified.md`. So wait for `unified.md`. If your own command times out first,
  the run keeps going: wait until `unified.md` appears in the run folder. Never
  read the raw `review-*.md` files and merge or summarize them yourself, and
  never report a model as failed unless `unified.md` says so.
- It needs network access and writes outside the sandbox. In Codex or Cursor,
  request escalated / unsandboxed execution for this command.
- Output goes to a run folder under `~/.local/share/unified-review/runs/`, not
  the project (the last line of stdout is the path to `unified.md`). It holds:
  `unified.md`, `factcheck.md` (with `--verify`), each panelist's raw review
  (`review-gpt.md`, `review-argon.md`, and so on), votes, the mediator's reply
  (`mediation.txt`), `results.json` (findings, votes, groups, rulings,
  timings), and `*.err` logs. The line before the last is `Notes: <path>`, the
  notes file. The last line of stdout is the path to `unified.md`.
- The script checks logins first and retries a failed call once. If a panelist
  still fails, the run continues without it, and the header of `unified.md` says
  which one failed and why. Report that line to the user. Common
  cause: the CLI is not logged in (`claude` then `/login`, `cursor-agent login`,
  `codex login`).

The review opens as `unified.md` (below). The review page opens only when the
user asks for it: run `unified-review --page FILE` after the review. It prints
`Review page: http://127.0.0.1:<port>/`. The page shows the draft
with each finding in place, and the user accepts, edits, or declines findings
there, which writes to the file and records the decision. The page opens on
logic findings first, and lets the user ask the panel about a finding or the
whole draft. Each finding carries a kind (logic, evidence, clarity, style);
when acting on findings outside the page, take open logic findings first.
Give the user that
link and say how many findings there are by severity. The page's summary
opens with the draft's key claim: exactly one claim, in one sentence, that
is worded to show its kind of inference ("X is associated with Y",
"X causes Y", "we aim to show X"), with no label. It closes with what the panel could not
assess, such as whether cited sources say what the draft says they do, or,
for a draft with numbers, code, or data, whether its results reproduce. Pass that
line on when you report the review. Do not paste
`unified.md` unless asked.
Decisions made on the page are in the same log as `--applied` and `--ignore`,
so `--item` and later reviews see them.

The script opens the notes file where it was run from: in Cursor or VS Code it
opens in the editor, and from a terminal in the default Markdown app. Inside an
agent app that cannot open a file from outside (the Claude app, the Codex app),
it prints `OPEN IN APP: <path>` instead. When you see that line, show the file
in your own app: in the Claude app, open it in the file pane (if the run folder
is outside the session's folders, ask to add `~/.local/share/unified-review/runs`
first). Where you cannot show files, give the user the path as a link. The
fact-check prints the same line for `factcheck.md` when it finishes, in its
log (`factcheck.log` in the run folder).

The script writes the notes file itself. Do not copy, re-summarize, or
re-order its findings. Reply with the one line the notes-file section
describes, with the counts by severity from its closing section. With
`--verify`, say whether the fact-check has finished or is still running.

## The notes file

After a script review of one file, the script writes and updates the notes
file. On a re-review it edits the file in place and never rewrites it:
- A finding raised again keeps its id and its body, so notes added under it
  survive. Its line number is refreshed.
- An item whose struck text is gone from the draft, or whose added text is in
  it, is removed and recorded with `--applied`. A declined item is removed.
- An item not raised again, with its passage unchanged, stays, marked "Not
  raised this round."
- A new finding takes the next free id in its set and goes in by severity,
  then draft order. An item the user deleted is not added back.
- Only `## About this review` is rewritten. An item whose heading no longer
  has the `### A1. Title` form is left as written, and the closing section
  names it.

Between reviews, and for a review by you alone, keep the file yourself by the
rules below. Once a review has more than one item, keep the
open items in a notes file in a `notes/` folder inside the draft's own folder:
`notes/review.md`, or `notes/review-<file>.md` when that folder holds more than
one draft (`<file>` is the draft's file name without its extension). Use the
notes file the user names instead, if they name one. A notes file keeps its
name once it exists, even if a second draft later joins the folder. Each item gives its section, its current line
in the draft, the point, and at least one inline revision, even while a source
is still being checked (then the revision is provisional, and the item says so).
In a review of a slide deck, every line number also names its slide number,
counted as the rendered deck counts them, with the cover as slide 1: in the
item's heading ("B5. Slides 10 and 11 (lines 142–163)") and in each
cross-reference ("the theorem (slide 16, line 237)"). Every turn, re-read the draft,
fix line and slide numbers that moved, and delete each item the user applied or rejected,
so the user never has to tidy the file. Delete an item you apply in the same
turn you apply it. Detect the user's own edits: an item whose struck text is
gone from the draft, or whose added text is in it, is applied. When the draft
changed the passage some other way, re-check the point and revise or delete
the item.

The file opens with its title and goes straight to the items. Everything else
goes in one section at the end, `## About this review`: the counts by
severity, the date the line numbers refer to, the review run, how ids work,
which items are closed and why, and what the review could not assess.
Give each set of recommendations a letter: A for Major, B for Minor, C for
Nitpick, X for Disputed. An item's id is its letter and its number within that
set (A2, B7), and the notes file lists the sets in that order. Where an item
shows Fix a and Fix b, they are alternatives: A2a and A2b name them. Ids stay fixed and are never
reused, leaving gaps, so an id the user said earlier still names the same item.
A new item takes the next free number in its set. An item whose severity
changes keeps its id.
For a script review, record each one with `--applied N` or `--ignore N`, so the
next review neither raises it again nor forgets it.

Write each item from scratch, as if the reader has seen no conversation. Open
with why the change is proposed: what is wrong or missing in the current text
and what that costs the argument or the reader. Never write "you're right",
"as you said", "partly right", or anything else that answers the chat.

The notes file is the only report. Everything relevant goes there: the point,
the evidence and sources, the revision, open questions, and answers to the
user's questions about an item. In the chat, write one line: the file's path and
which items were added, changed, applied, or removed. Do not repeat findings,
revisions, or reasoning in the chat.

## Addressing items

Findings are numbered in `unified.md` (1, 2, 3, ...), straight through the main
review and Disputed. A finding with alternative fixes names each by letter: 3a,
3b. `--item 3b` prints that fix as the one to apply. Fact-check claims are
numbered in `factcheck.md` (K1, K2, ...). This applies whenever the user refers to
items by number: to address, apply, fix, skip, or just to ask whether one is
worth doing, for example "address 3", "apply 2, 4, 7", "fix K5", or "is 6
right?".

The notes file uses its own ids (A2, B7), not the numbers in `unified.md`.
When the user names a notes id, act on that item in the notes file, and find
its number in `unified.md` by its quoted text before running `--item`,
`--applied` or `--ignore`.

1. Always start by running `unified-review --item <numbers>`, even if you saw
   the review earlier. Add `--run DIR` only if the user names an older run. It
   works from any folder: it uses the newest run that reviewed a file in the
   current folder, else the last run made. It is local, takes about a second, and needs no
   network or sandbox escalation. Read its whole output. It prints:
   - the full path of each reviewed file (the file to edit) and the run folder;
   - the version reviewed (an SVN-style number, 1, 2, 3, ...), whether the
     file has changed since, and a saved copy of the reviewed text;
   - for each item, its current line in that file, the quoted text, the votes,
     and the finding with its diff;
   - the full current text of each reviewed file, line-numbered.
2. Base every opinion and edit on that current text, not on the review's
   snapshot. the user edits files directly, so the text may have changed since the
   review ran. If a finding no longer applies, say so.
3. To apply a finding, edit the reviewed file at its current line: replace the
   ~~struck~~ text with the 🟢 text. Keep the edit minimal. If the proposed text
   breaks the user's writing rules (their CLAUDE.md, AGENTS.md, or review rules
   file), fix that in the applied text and say so.
4. If "Location now" says the text is not in the current file, it was likely
   already edited. Say so and ask before changing anything.
5. For whole-draft findings, which have no single location, propose the change
   and ask before making it.
6. For a K item marked contradicted or unverifiable, propose a fix: reword,
   hedge, or a better source. Follow the sourcing and citation rules. If the
   project has a bibliography, look up citation keys there; never invent one.
7. Record each decision so the next review respects it (about a tenth of a
   second, no model calls):
   - After applying findings: `unified-review --applied 3,4`.
   - When the user declines findings ("ignore 5", "skip 7", "won't do 9"):
     `unified-review --ignore 5,7 --note "<their reason, if given>"`.
   - When the user wants a declined point back: `unified-review --unignore D2`
     (D ids are listed under "Previously declined" in `unified.md`).
   - When the user wants a file's history forgotten (start over, nothing held
     back to stop churn): `unified-review --forget FILE`. It sets aside the
     file's earlier reviews, decisions, and versions under `runs/forgotten/`.
     A Word or PDF file's edited Markdown copy stays, so the next review sees
     the edited text as version 1.
   Every agent (Claude, Codex, Cursor) records to the same log, so decisions
   made in one are visible in the others. `unified-review --decisions` lists
   them for the current project, and `--item` shows whether an item was
   already ignored or applied. Check before acting on an item.
   The next review tells the panel about declined and applied points, and
   holds back findings that repeat a declined point while its text is unchanged.
8. Afterward, list what changed by item number, with the file and line. Do not
   commit.

## Iterating

Use this when the user asks to review, apply the changes, and repeat ("iterate
on memo.md", "iterate 5 rounds", "keep going until it's clean"). Run it without
stopping to ask between rounds.

The same loop also runs in the script: `unified-review --iterate N FILE`, or
the review page's **Iterate** button. The script applies each agreed diff as
written. The steps below have you fix each edit to the user's writing rules,
so follow them when the user asks you to iterate.

1. Rounds: 3 unless the user gives a number. Before the first round, run
   `unified-review --snapshot FILE`. It saves the starting text beside the file
   as `<name>-v<N>` (for example `memo-v7.md`) and adds a pattern for these
   copies to the repository's `.gitignore`. Note N: it is the starting version.
2. Each round, run `unified-review FILE` (no `--verify` unless asked) and wait
   for `unified.md`. Then run `unified-review --item` with every finding number,
   and work from its current text, as in "Addressing items".
3. Apply a finding only if it is in the review's main list (not Disputed,
   not rejected) and either:
   - every voter agreed on its problem and its fix, or
   - with three or more reviewers, it is Major or Minor and a majority of
     voters agreed (more ✓ than half the votes, ~ counting as not agreeing).
   Skip everything else, and always skip disputed findings, findings whose
   fixes differ (even when the mediator picked one), contested findings,
   whole-draft findings, question findings, and findings whose quoted text is
   no longer in the file. Do not
   ask about skipped findings during the loop.
4. Apply edits as in "Addressing items" (minimal, at the current line, fixed
   to the user's writing rules). Then record every decision:
   `unified-review --applied <numbers>` and
   `unified-review --ignore <numbers> --note "auto-loop: skipped"`. This keeps
   later rounds from raising them again. The user can bring one back with
   `--unignore`. Then run `unified-review --snapshot FILE` to save the new
   version beside the file.
5. Stop early when a round has nothing to apply. Stop if a round's applied
   change would undo an earlier round's change: skip that finding and say so.
6. Do not commit.
7. When the loop ends, run `unified-review --changes N FILE` with the starting
   version N. It writes `<name>-v<N>-to-v<M>` beside the file: every changed
   passage under its section heading, ~~deleted~~ and 🟢 **added**, and opens
   it (or prints `OPEN IN APP:`, which you handle as for `unified.md`).
8. Then give one summary: for each round, the version reviewed, the
   finding numbers applied (with a few words each), and how many were skipped.
   Then list the skipped findings worth the user's attention: Major or
   Minor findings that were disputed, contested, had differing fixes, or were
   whole-draft, with the run folder
   so the user can address them by number (`--run DIR`).

## Reviewer rules

Reviewer instructions for feedback on drafts. This covers verification and how findings get reported.

### Review method

- Before writing findings, identify up to three central claims or decision-critical commitments. For each, identify the text, analysis, evidence, citation, or stated premise that supports it. Judge whether that support establishes the claim, supports a narrower claim, or leaves the claim unsupported. Do not report the map unless it produces a finding.
- Apply that map when the draft makes an argument or asks its reader to make a decision. Do not force it onto a simple message, reference list, or other document with no such claim or commitment.

### What to flag

- Logical gaps, overstated claims, unaddressed counterarguments, internal redundancy.
- House-style violations: citation key format, equation tagging, cross-reference syntax, table size.
- Places where the intended reader has to guess: a term or acronym used before it is defined, two words that may name the same thing, a sentence with two readings, steps that may be one test or several, what the draft asks its reader to decide or provide, who decides, and what has to happen first (approval, purchases). Say what you guessed. When a later passage resolves the guess, flag that the information arrives after the first place it was needed.
- Categories the draft names but does not apply. When it sets up a split, check that each method or condition it mentions falls in exactly one category and that each category is defined well enough to place them. Ask where each one falls when the draft does not say.
- Mechanisms that cannot produce the stated effect given how the system was built or trained, such as a policy expected to adapt to an input it was never trained on.
- For each experiment the draft proposes, check that a reader could set it up from the text: the hardware, the task as given to the system (its instruction or goal), what varies and what stays fixed, and for a simulation, what is modeled and what is idealized. Ask about each missing piece.
- A new term or method introduced without saying why an existing one does not serve.
- What an expert in the draft's field expects and does not find: standard benchmarks (including well-known ones missing from a list the draft gives), accepted definitions or standards for key terms. Ask, since the omission may be deliberate.

### What not to touch

- Argument structure and section order, unless actually broken (a claim doesn't follow, or a section contradicts another one elsewhere). Don't restructure a passage that already works. A broken story arc counts as broken: no explicit question, objectives stated in place of a question, a conclusion that answers a different question than the one posed, or an opening whose scope does not match the conclusion's (see OCAR in the `logic` and `papers-and-proposals` skills). These are Major when they leave the central claim unsupported.
- Equations and notation. Flag an equation or symbol that is wrong, unused, or redundant, but do not remove one only to make the prose read faster.

### Output format

- Group findings by severity, judged by one test: do the draft's claims still stand if this goes unfixed? **Major**: no, a claim fails or is unsupported until this is fixed. **Minor**: yes, but the fix makes the draft clearer, more complete, or easier to reproduce. **Nitpick**: style, phrasing, typos, with a few words of point at most and a diff of only the words that change. Within each group, put findings about the whole draft or its structure first, then work through the draft from top to bottom, giving findings in the order of the text they target and naming the section each is in. Enumerate every finding with a sequential integer that runs through the whole response, Major first, so a finding can be cited by number alone. For each finding, state the problem, then immediately show its fix, before moving to the next finding. Do not collect all diffs into a separate list at the end.
- Each finding has two parts. The problem is one sentence of at most 25 words: the claim or decision affected and what the defect costs it. The fix is the diff, with no restatement of the problem. For a Major finding about a claim, the fix adds the missing support or narrows the claim to what the evidence supports. Keep Nitpicks terse: a few words and the diff.
- Every finding proposes at least one revision, a question finding included. For a question, state it in one or two sentences, list the readings or options you see, say which one you assumed, and give the revision for that reading. Use a question only when the answer is the author's to give. When the draft already implies the answer, make it an edit.
- Show every diff as an **inline revision of the original text**, not as a `Replace:` / `With:` pair. Strike deletions with `~~tildes~~`, and make every struck span render as strikeout, never as literal tildes. The opening `~~` touches the first struck character and the closing `~~` touches the last, so a space next to a span sits outside it: `the tokens it covers ~~and the rest~~.`, not `the tokens it covers~~ and the rest~~.`. A span may open on punctuation, as in `~~(v2)~~`, only when a space or the start of a line comes before it. When a deletion starts with punctuation attached to the word before it, as in `choice, because`, widen it to take in that word and restore the word in the 🟢 text: `~~choice, because x~~ 🟢 **choice**`, not `choice~~, because x~~`. Bold each addition and prefix it with `🟢 `. When an addition runs several sentences or lines in a row, one `🟢 ` before the first is enough: bold the whole run once, not each sentence. Tildes mark deletions only, never additions. Leave genuinely unchanged sentences plain, and for a mostly-rewritten paragraph strike the whole old block and follow it with the whole new one rather than a word-level diff. When the finding says the quoted text is wrong, the diff strikes or rewrites that text. A diff that only adds text is for an omission, never for a fix to text the draft already has. The added text does not repeat what neighboring sentences already say.

### Math and markup inside a diff

The inline form needs the surrounding Markdown to render, so anything in the quoted text that is itself Markdown or LaTeX has to be handled deliberately.

- **Math carried along as unchanged context**: leave it in whatever form the source uses. Inline math stays `$...$`, display equations stay `$$...$$` on their own lines with blank lines around them, which is what GFM needs to render them at all.
- **When the edit targets an equation**: show the old and new equations rendered, never as LaTeX source in a code block and never with `~~` or 🟢 inside or around math. Write a 🔴 **Now** line, then the old equation as display math (`$$...$$` on its own line, blank lines around it), then a 🟢 **Proposed** line, then the new equation. Colour the parts that change: red in the old equation and green in the new, with a scoped group, `{\color{red} ...}` and `{\color{green} ...}`, never the bare `\color{red}{...}` switch. Do not insert placeholder symbols to mark something missing. When a change only adds a term, colour the new term green and say what is missing in the 🔴 line, for example "🔴 **Now** (no expectation):". Display form here is a way to show the equations and does not change the source: the item still says where the math sits (inline or display) when that matters.
- **When a prose edit contains inline math**: never wrap math in `~~` or `**`, and never start a bolded addition with a list marker (write `- 🟢 **text**`, not `🟢 **- text**`). Strikethrough and bold do not render over math delimiters, so show any edit that deletes, replaces, or adds inline math as a 🔴 **Now** and 🟢 **Proposed** pair, as for an equation edit. When an edit changes only the prose around math that stays, leave the math outside the `~~` and `🟢 **` spans as unchanged context, and start every added span with its own `🟢 `.
- **When the edit targets other markup source** (a `\tag{}`, an anchor, table pipes, a citation key): put that diff in a fenced code block, with the old and new lines one above the other. Rendering it would hide the exact characters being changed, which are the point.
- When applying an equation change, keep the source's form: never rewrite `$...$` into `$$...$$` in the draft. That changes inline math into a display equation and silently edits the source.
