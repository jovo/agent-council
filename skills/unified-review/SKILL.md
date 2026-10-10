---
name: unified-review
description: Get independent reviews of a draft from a panel of models from different labs (Claude, GPT, Gemini), have them vote on each other's findings, and merge them into one review in draft order, with an optional web fact-check. Use when the user asks for a unified, combined, panel, tri-model, or multi-model review or feedback on a file. Also use when the user asks to address, apply, fix, accept, or skip numbered items (such as 3, 7, or K5) from a unified review or fact-check. Also use when the user asks to iterate (review, apply the changes, and review again) for some number of rounds. Also use for any review of or feedback on a draft, even by one model, since its Reviewer rules set what to flag and the output format.
---

# Unified review

This skill lives in the agent-council repo (`skills/unified-review/SKILL.md`).
`install.sh` links it into `~/.claude/skills`, `~/.codex/skills`, and
`~/.cursor/skills`, so Claude Code, Codex, and Cursor share one copy. Edit it
in the repo.

For a review by you alone, without the panel, follow the Reviewer rules at the end of this skill. The script gives the same rules to the panel.

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

The default panel is `claude,gpt,gemini` (Claude Sonnet, GPT-5.6 Luna at low
effort, Gemini 3.8 Flash Low via cursor-agent). If one fails, Grok 4.7 Low Fast stands in automatically, so three models
still vote. Pass
`-p` only when the user names a panel. Pass `--verify` only when the user asks for a
fact-check or claim verification.

How it works: each panelist reviews without web search, then every panelist
votes on the other models' findings, never its own, with reviewers anonymized.
The script groups duplicates, reports a finding only when two models stand
behind it (a second model raised it, or another voted agree or partial), and
writes `unified.md`:
findings grouped by severity (Major, Minor, Nitpick), each group in
draft order with its section, file, and line, then a short list of findings not
reported. There is no cap on findings. When the file was reviewed before,
`unified.md` opens with a "Since the last review" section: three counts and
their finding numbers, resolved (an earlier finding whose passage changed and
that no panelist raised again, numbered as in the last review), persisting,
and new. Report these counts to the user before the findings.

- The review takes about 40 seconds to 2 minutes, then `unified.md` opens in the
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
  (`review-claude.md`, `review-gpt.md`, `review-gemini.md`), votes, `results.json` (findings, votes, groups,
  timings), and `*.err` logs. The last line of stdout is the path to `unified.md`.
- The script checks logins first and retries a failed call once. If a panelist
  still fails, the run continues without it, and the header of `unified.md` says
  which one failed and why. Report that line to the user. Common
  cause: the CLI is not logged in (`claude` then `/login`, `cursor-agent login`,
  `codex login`).

For one Markdown file, the script opens the review page in the user's browser
and prints `Review page: http://127.0.0.1:<port>/`. The page shows the draft
with each finding in place, and the user accepts, edits, or declines findings
there, which writes to the file and records the decision. The page opens on
logic findings first, and lets the user ask the panel about a finding or the
whole draft. Each finding carries a kind (logic, evidence, clarity, style);
when acting on findings outside the page, take open logic findings first.
Give the user that
link and say how many findings there are by severity. The page's summary
opens with the draft's key claim: exactly one claim, in one sentence, that
makes clear its kind of inference (association, causal effect, benchmark
result, theorem, or a proposal's aim). It closes with what the panel could not
assess, such as whether cited sources say what the draft says they do. Pass that
line on when you report the review. Do not paste
`unified.md` unless asked. Run `unified-review --page FILE` to reopen the page.
Decisions made on the page are in the same log as `--applied` and `--ignore`,
so `--item` and later reviews see them.

For a PDF reviewed with `--no-md` or several files, the script opens `unified.md` where it was run from: in Cursor or VS Code it
opens in the editor, and from a terminal in the default Markdown app. Inside an
agent app that cannot open a file from outside (the Claude app, the Codex app),
it prints `OPEN IN APP: <path>` instead. When you see that line, show the file
in your own app: in the Claude app, open it in the file pane (if the run folder
is outside the session's folders, ask to add `~/.local/share/unified-review/runs`
first). Where you cannot show files, give the user the path as a link. The
fact-check prints the same line for `factcheck.md` when it finishes, in its
log (`factcheck.log` in the run folder).

When no review page opened, show the user the contents of `unified.md` verbatim. Do not
re-summarize or re-order the findings. With `--verify`, say whether the
fact-check has finished or is still running.

## Addressing items

Findings are numbered in `unified.md` (1, 2, 3, ...). Fact-check claims are
numbered in `factcheck.md` (K1, K2, ...). This applies whenever the user refers to
items by number: to address, apply, fix, skip, or just to ask whether one is
worth doing, for example "address 3", "apply 2, 4, 7", "fix K5", or "is 6
right?".

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

1. Rounds: 3 unless the user gives a number. Before the first round, run
   `unified-review --snapshot FILE`. It saves the starting text beside the file
   as `<name>-v<N>` (for example `memo-v7.md`) and adds a pattern for these
   copies to the repository's `.gitignore`. Note N: it is the starting version.
2. Each round, run `unified-review FILE` (no `--verify` unless asked) and wait
   for `unified.md`. Then run `unified-review --item` with every finding number,
   and work from its current text, as in "Addressing items".
3. Apply a finding only if it is in the review's main list (not rejected) and
   either:
   - every voter agreed (every vote is ✓), or
   - it is Major or Minor and a majority of voters agreed (more ✓
     than half the votes; ~ counts as not agreeing).
   Skip everything else, and always skip contested findings, whole-draft
   findings, question findings, and findings whose quoted text is no longer
   in the file. Do not
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
   Minor findings that were contested or whole-draft, with the run folder
   so the user can address them by number (`--run DIR`).

## Reviewer rules

Reviewer instructions for feedback on drafts. This covers verification and how findings get reported.

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

- Argument structure and section order, unless actually broken (a claim doesn't follow, or a section contradicts another one elsewhere). Don't restructure a passage that already works.
- Equations and notation. Flag an equation or symbol that is wrong, unused, or redundant, but do not remove one only to make the prose read faster.

### Output format

- Group findings by severity, judged by one test: do the draft's claims still stand if this goes unfixed? **Major**: no, a claim fails or is unsupported until this is fixed. **Minor**: yes, but the fix makes the draft clearer, more complete, or easier to reproduce. **Nitpick**: style, phrasing, typos, with a few words of point at most and a diff of only the words that change. Within each group, put findings about the whole draft or its structure first, then work through the draft from top to bottom, giving findings in the order of the text they target and naming the section each is in. Enumerate every finding with a sequential integer that runs through the whole response, Major first, so a finding can be cited by number alone. For each finding, state the point, then immediately show its diff, before moving to the next finding. Do not collect all diffs into a separate list at the end.
- For a Major finding, name the claim it leaves unsupported (the key claim, or the passage that states another claim) and what follows if it stays unfixed. Then give the smallest change that fixes it: the missing support, or the weaker claim the evidence does support.
- A question finding has no diff. State the question in one or two sentences, list the readings or options you see, and say which one you assumed. Use it only when the answer is the author's to give. When the draft already implies the answer, propose the edit.
- Show every diff as an **inline revision of the original text**, not as a `Replace:` / `With:` pair. Strike deletions with `~~tildes~~`. Bold each addition and prefix it with `🟢 `. Tildes mark deletions only, never additions. Leave genuinely unchanged sentences plain, and for a mostly-rewritten paragraph strike the whole old block and follow it with the whole new one rather than a word-level diff.

### Math and markup inside a diff

The inline form needs the surrounding Markdown to render, so anything in the quoted text that is itself Markdown or LaTeX has to be handled deliberately.

- **Math carried along as unchanged context**: leave it in whatever form the source uses. Inline math stays `$...$`, display equations stay `$$...$$` on their own lines with blank lines around them, which is what GFM needs to render them at all.
- **When the edit itself targets math or markup source** (an equation's internals, a `\tag{}`, an anchor, table pipes, a citation key): put that diff in a fenced code block instead, with the old and new lines one above the other. Rendering it would hide the exact characters being changed, which are the point.
- Never rewrite `$...$` into `$$...$$` just to make a diff render. That changes inline math into a display equation and silently edits the source.
