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
unified-review [-n "extra focus"] [-p PANEL] [--verify] [-o OUTDIR] FILE [FILE...]
```

The default panel is `claude,gpt,gemini` (Claude Sonnet, GPT-5.6 Luna at low
effort, Gemini 3.8 Flash Low via cursor-agent). `grok` is also available. Pass
`-p` only when the user names a panel. Pass `--verify` only when the user asks for a
fact-check or claim verification.

How it works: each panelist reviews without web search, then every panelist
votes on every finding with reviewers anonymized. The script groups
duplicates, sets aside findings most voters reject, and writes `unified.md`:
an overview first, then findings in the order of the draft under its section
headings, each with its votes, then findings about the focus material, then a
short list of rejected findings. There is no cap on findings.

- The review takes about 40 seconds to 2 minutes, then `unified.md` opens in the
  default app for .md files (set UNIFIED_REVIEW_OPEN_APP to change). With `--verify`, a web fact-check (stronger Claude and
  GPT models) runs in the background for about 2 more minutes, writes
  `factcheck.md` in draft order with each claim's verdict and sources, sends a
  macOS notification, and opens it. `unified.md` is not changed by the
  fact-check. Run the command with a timeout of at least 5 minutes. Do not wait
  for the fact-check before showing the review.
- It needs network access and writes outside the sandbox. In Codex or Cursor,
  request escalated / unsandboxed execution for this command.
- Output goes to `feedback/<file>-<timestamp>/` in the current directory:
  `unified.md`, `factcheck.md` (with `--verify`), each panelist's raw review
  (`review-claude.md`, `review-gpt.md`, `review-gemini.md`), votes, `results.json` (findings, votes, groups,
  timings), and `*.err` logs. The last line of stdout is the path to `unified.md`.
- If a panelist fails, the script continues with the rest, which
  vote without it. Report which one failed and the first line of its `.err` file. Common
  cause: the CLI is not logged in (`claude` then `/login`, `cursor-agent login`,
  `codex login`).

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
   works from any folder: it uses the newest run under `./feedback`, else the
   last run made anywhere. It is local, takes about a second, and needs no
   network or sandbox escalation. Read its whole output. It prints:
   - the full path of each reviewed file (the file to edit) and the run folder;
   - the version reviewed (content fingerprint and git commit), whether the
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
5. For overview findings, which have no single location, propose the change
   and ask before making it.
6. For a K item marked contradicted or unverifiable, propose a fix: reword,
   hedge, or a better source. Follow the sourcing and citation rules. If the
   project has a bibliography, look up citation keys there; never invent one.
7. Afterward, list what changed by item number, with the file and line. Do not
   commit.
