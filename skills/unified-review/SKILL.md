---
name: unified-review
description: Get independent reviews of a draft from a panel of models from different labs (Claude, GPT, Gemini), have them vote on each other's findings, and merge them into one review in draft order, with an optional web fact-check. Use when the user asks for a unified, combined, panel, tri-model, or multi-model review or feedback on a file. Also use when the user asks to address, apply, fix, accept, or skip numbered items (such as 3, 7, or K5) from a unified review or fact-check.
---

# Unified review

This skill lives in the agent-council repo (`skills/unified-review/SKILL.md`).
`install.sh` links it into `~/.claude/skills`, `~/.codex/skills`, and
`~/.cursor/skills`, so Claude Code, Codex, and Cursor share one copy. Edit it
in the repo.

Run the script on the file(s) the user names:

```bash
unified-review [-n "extra focus"] [-p PANEL] [--context FILE]... [--verify] [-o OUTDIR] FILE [FILE...]
```

If the user attaches or names supporting material with the request (reviewer
comments, a call for proposals, a source paper, a style guide), pass it with
`--context FILE`, once per file. The panel reads it but does not review it.
Text files and PDFs work. An attachment that exists only in the chat must be
saved to a temporary file first. Images are not supported yet: say so.

The file to review can itself be a PDF. The script decides how the panel reads
it: plain prose goes as text, and a PDF with figures, tables, or equations is
opened by each panelist directly. Findings on a PDF cite pages, not lines. You
cannot edit a PDF, so apply accepted changes to its source document, or tell
the user where they go.

The default panel is `claude,gpt,gemini` (Claude Sonnet, GPT-5.6 Luna at low
effort, Gemini 3.8 Flash Low via cursor-agent). `grok` is also available. Pass
`-p` only when the user names a panel. Pass `--verify` only when the user asks for a
fact-check or claim verification.

How it works: each panelist reviews without web search, then every panelist
votes on every finding with reviewers anonymized. The script groups
duplicates, sets aside findings most voters reject, and writes `unified.md`:
findings grouped by severity (Critical, Substantive, Polish), each group in
draft order with its section, file, and line, then a short list of rejected
findings. There is no cap on findings.

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

The script opens `unified.md` where it was run from: in Cursor or VS Code it
opens in the editor, and from a terminal in the default Markdown app. Inside an
agent app that cannot open a file from outside (the Claude app, the Codex app),
it prints `OPEN IN APP: <path>` instead. When you see that line, show the file
in your own app: in the Claude app, open it in the file pane (if the run folder
is outside the session's folders, ask to add `~/.local/share/unified-review/runs`
first). Where you cannot show files, give the user the path as a link. The
fact-check prints the same line for `factcheck.md` when it finishes, in its
log (`factcheck.log` in the run folder).

When it finishes, show the user the contents of `unified.md` verbatim. Do not
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
   Every agent (Claude, Codex, Cursor) records to the same log, so decisions
   made in one are visible in the others. `unified-review --decisions` lists
   them for the current project, and `--item` shows whether an item was
   already ignored or applied. Check before acting on an item.
   The next review tells the panel about declined and applied points, and
   holds back findings that repeat a declined point while its text is unchanged.
8. Afterward, list what changed by item number, with the file and line. Do not
   commit.
