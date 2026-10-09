# agent-council

agent-council has models from different labs review the same document, vote on each other's findings, and merge the result into one review you read top to bottom. It drives the coding-agent CLIs you already use (Claude Code, Codex, and Cursor), so it needs no API keys beyond your existing logins.

The command is `unified-review`. A skill of the same name lets Claude Code, Codex, and Cursor run it and act on its findings by number ("address 3", "apply 2, 4, 7", "fix K5").

## Why a panel that votes

A single model reviewing a draft misses things another model catches. A single model merging several reviews favors its own findings. LLM evaluators recognize their own outputs and rate them higher (Panickssery et al. 2024, [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)). A panel of judges from different model families tracks human judgments more closely than one large judge and shows less intra-model bias (Verga et al. 2024, [arXiv:2404.18796](https://arxiv.org/abs/2404.18796)).

So agent-council does not let any one model decide. Each model reviews independently. Every model then votes on every finding, with reviewers anonymized. The script, not a model, groups duplicates and sets aside findings most voters reject. Andrej Karpathy's [llm-council](https://github.com/karpathy/llm-council) is a precursor to this.

## How it works

```
unified-review [-n FOCUS] [-p PANEL] [--context FILE]... [--verify] [--rules FILE] [-o OUTDIR] FILE [FILE...]
```

Before starting, the script checks that each CLI is installed and logged in, using its status command. A panelist whose CLI is missing or logged out is dropped and listed as failed in `unified.md`, so a model never drops out silently.

`--context FILE` adds supporting material that every panelist reads but does not review, such as reviewer comments, a call for proposals, or a source paper. Text files and PDFs work (PDFs through `pdftotext`). Very long material is trimmed to fit the prompt. Voters see it too, and a finding that quotes it is listed under the focus or supporting material.

A file to review can be a PDF. If it is plain prose, the panel gets its text (from `pdftotext`). If it has anything the text would lose, such as figures, images, ruled tables, or equations, each panelist opens the PDF itself. Findings on a PDF cite page numbers, and edits go in its source document. The check needs Ghostscript and poppler (`brew install ghostscript poppler`).

1. **Review.** Each panelist reviews the draft without web search. Findings come back in a fixed format: severity, kind, title, the exact text targeted, then the point and an inline diff. The kind is logic (a step that does not follow, or an inference the evidence does not support), evidence (an unsupported or wrong factual claim), clarity, or style. Voters vote on the kind too, and each finding takes the majority's.
2. **Vote.** Each panelist votes agree, partial, or disagree on every finding, sees reviewers only as A, B, C, and flags duplicates.
A model call that times out, errors, or returns nothing gets one retry, except after a login error. A login error is recognized only from the CLI's own messages at the end of its log ("not logged in", "401 Unauthorized", and the like), since CLIs copy the prompt into that log and a draft may say "authorized" or "log in" anywhere. A reply in the wrong format also gets one retry.

3. **Render.** The script groups duplicates (two voters calling them duplicates, or one voter plus overlapping quoted text), keeps the best-voted version of each, sets aside findings a majority rejects, and writes `unified.md`. For one Markdown file, the [review page](#the-review-page) opens in your browser. Otherwise `unified.md` opens where you ran the command: in Cursor or VS Code if you ran it there, in your default Markdown app from a terminal. Inside the Claude or Codex app, the script prints `OPEN IN APP: <path>` and the skill has the agent show the file. Set `UNIFIED_REVIEW_OPEN_APP` to always use one app.
4. **Fact-check (optional, `--verify`).** A detached background process lists the draft's checkable claims, has each panelist check them with web search, keeps the most cautious verdict per claim, writes `factcheck.md`, and opens it. A claim that the last fact-check of the same file confirmed, with its sentence unchanged, keeps that verdict and is marked as carried over instead of being checked again. Everything else is checked from scratch.

The default panel is one model per lab, chosen for speed: Claude Sonnet (via `claude`), GPT-5.6 Luna at low effort (via `codex`), and Gemini 3.8 Flash Low (via `cursor-agent`). If a panelist is unavailable or fails to review or vote, Grok 4.7 Low Fast (via `cursor-agent`) stands in, so three models still vote and ties can be broken. Grok cannot stand in for Gemini when `cursor-agent` itself is down, since both run through it. The fact-check uses stronger Claude and GPT models, since it runs in the background. Edit `PANELISTS` and `FACTCHECK_PANELISTS` at the top of `bin/unified-review` to change them.

The panel runs on the CLIs' subscriptions, so a review adds no per-call cost. An October 2026 test compared cheaper pay-per-token models with this panel on the same memo. None replaced it. On Together AI, DeepSeek V4 Flash and gpt-oss-120b cost about $0.004 per model per round and answered in 20 to 65 seconds, but returned 3 and 6 findings where the panel's models returned 5 to 21, and 2 of gpt-oss-120b's 6 quotes did not match the draft. Open-weight models served through `cursor-agent` (GLM 5.2, Kimi K3) took 60 to 270 seconds per review, against 13 to 22 seconds for Gemini and GPT.

On one 1,300-word memo, a review took 40 to 120 seconds and the fact-check about 2 more minutes. Times depend on the models, the draft, and the providers' load.

## Output

Each run writes a folder under `~/.local/share/unified-review/runs/`, outside every project, named `<date>-<time>-<project>-<file>-v<N>`, such as `2026-10-08-1342-myproject-memo-v7`, so the folders sort by when each run was made, with `-run2` for a second run in the same minute, so nothing is added to the project you review. Set `UNIFIED_REVIEW_RUNS` to put runs elsewhere. Each run folder holds:

- `unified.md`: the review. See [Reading unified.md](#reading-unifiedmd).
- `factcheck.md` (with `--verify`): each claim in draft order, with its sentence, each checker's verdict, notes, and sources.
- `reviewed/`: an exact copy of the text reviewed. The title of `unified.md` gives its version number, and `results.json` its fingerprint and git commit.
- `results.json`, `factcheck.json`: findings, votes, groups, verdicts, and per-stage timings.
- `review-<model>.md`, `votes-<model>.txt`, `*.err`: raw panel output and logs.

## The review page

For one Markdown file, `unified-review` opens a local page in your browser (`http://127.0.0.1:<port>/`). It shows the current draft, set in New Computer Modern like the PDFs and decks, with front matter and HTML-only lines hidden and tables drawn as tables. Each finding is highlighted in place by severity, on the words its change replaces or deletes, or on the word before an insertion. A card shows the selected finding: its type, point, diff, and votes. Clicking a card scrolls the draft to its passage.

- **Logic first.** When a review has open logic findings, the page opens showing only those, Critical first, since a passage whose argument fails may be rewritten anyway. Once none are open, it shows everything, ordered by severity. A banner says so, with a link to show everything at once. A review made before findings had types says it has none.
- **Accept** writes the change into the file and records it as applied. **Edit** lets you change the proposed text first. **Decline** records the decision with an optional note. These are the same records `--applied` and `--ignore` write. Before writing, Accept re-reads the file and finds the passage the change targets, allowing for small misquotes by the reviewers. If you have since changed that passage, it refuses and leaves the file alone.
- A diff that skips text with "…" applies part by part: the text on each side of the ellipsis is found in order and changed, and the skipped text is kept. If any part is missing, Accept refuses.
- A finding with no exact diff, such as one about the whole draft or one whose new text has a blank to fill in, cannot be accepted on the page. Its card says why and copies a request you can paste to an agent.
- **Ask** on a card sends a question about that finding to every panelist in parallel, with the draft, the finding, its votes, and earlier questions. Answers appear as each model finishes, marked with the model that raised the finding. An answer that revises the change gets its own **Accept this version**.
- **Ask** beside **Accept all shown** opens a box at the top of the right column for a question, comment, or request about the whole draft ("tighten the wedge section"). Each panelist answers, and any edits it proposes appear as changes with their own Accept. Tick "Use as focus for the next Update" to pass the comment to the next review as its focus (`-n`). Questions and comments are saved in the run folder, and a failed answer gives the reason.
- Dropdowns select findings by type (logic, evidence, clarity, style), severity, agreement (unanimous, majority, contested), and status. **Accept all shown** applies every open finding they select.
- Double-click any paragraph, heading, or table to edit its Markdown in place. Save writes it back, unless it changed in the file since the page loaded.
- **Panel** in the header chooses the models for Update and Ask, saved per file. Its Add menu cascades by lab, model family, and variant: the models Claude Code and Codex run directly, and every model `cursor-agent models` lists (Gemini, Grok, Kimi, GLM, and others). Reset to default restores Claude Sonnet, GPT-5.6 Luna, and Gemini 3.8 Flash Low. On the command line the same choices are `-p claude:opus,codex:gpt-5.6-luna@medium,cursor:kimi-k3-low`, alongside the short names.
- **Update** runs a new review of the current text and loads it into the page. The header gives when the review ran and says "edited since" once the file differs.
- Keys: `j` and `k` move between findings, `a` accepts, `e` edits, `d` declines, `q` asks, and ⌘Enter saves an edit or sends a question.

The page is served by a small server inside `unified-review`, using only Python's standard library. It listens only on your machine, serves one file, and exits after 8 hours without use. `unified-review --page FILE` reopens it.

## Reading unified.md

- The title is the reviewed file, its version number, and the date and time the run started. Versions count up like SVN revisions: version 1 is the first text of that file reviewed, version 2 the next different text, and unchanged text keeps its number. `versions.json` in that runs folder maps each version to a fingerprint of the exact text. `reviewed/` in the run folder holds a copy of that text, and `results.json` records the fingerprint, git commit, and whether there were uncommitted edits.
- Findings are grouped by severity: Critical, then Substantive, then Polish. Within each group, findings about the whole draft come first, then findings in the order of the draft, then findings about any focus material (`-n`). Each finding shows its draft section, file, and line. Findings most voters rejected come last, with their reasons.
- Each finding is the best-voted version among duplicates. It shows the file and line, the quoted text, the point, an inline diff (~~deleted~~ and 🟢 **added**), and a line of votes such as `Claude ✓ · **GPT** ✓ · Gemini ~`: ✓ agree, ~ partial, ✗ disagree, bold for the model that raised the point.
- A model's vote on a finding its own review raised is shown but not counted: it does not decide whether the finding is kept, its severity, or its label, since models favor their own text.
- **Contested** means at least one model other than the one that raised it agreed and at least one disagreed.
- **Agreement** is ordinal Krippendorff's alpha over the votes (agree > partial > disagree), with a bootstrap 95% confidence interval over findings. Each model's votes on its own findings are left out. 1 is full agreement, 0 is chance level. Most votes are "agree", and that imbalance pulls alpha down even when raw agreement is high.
- A "Failed" line or a warning appears only when a panelist failed or fewer than two models took part.

## Acting on findings

```
unified-review --item 3,7,K2 [--run DIR]
```

This prints the items from the newest run that reviewed a file in the current folder (else the last run made): the reviewed file's full path, whether it has changed since the review, each item's current line, the quoted text, the votes, the diff, and the whole current file with line numbers. The skill tells agents to run it before giving an opinion on an item or editing, so they work from the current text.

To iterate, ask an agent to "iterate on FILE" (3 rounds by default) or "iterate 5 rounds". Each round it reviews, applies findings every voter agreed with plus Critical and Substantive findings a majority agreed with, records the rest as declined, and reviews again. It stops early when nothing qualifies, then lists the contested and whole-draft findings it skipped for you to decide. Each version is saved beside the file as `memo-v7.md`, `memo-v8.md`, and so on, with a pattern added to the repository's `.gitignore`. At the end, `memo-v7-to-v10.md` opens with every change since the start, ~~deleted~~ and 🟢 **added**, under its section heading. The two commands the loop uses also work alone:

```
unified-review --snapshot FILE
unified-review --changes N FILE
```


## Skills

`install.sh` links every folder in `skills/` into Claude Code, Codex, and Cursor, which load a skill when a task matches its description:

- `unified-review`: run the panel review and act on its findings by number.
- `logic`: check the logic of an argument from the document's arc down to a single sentence: missing premises, non sequiturs, unaddressed alternatives, over- and underclaims. Reviews also check it.
- `statistics`: experimental design and inference from data, as two halves of what a study can conclude: controls, units of replication, fair method comparisons, and the inference errors that follow from design. Reviews also check it.
- `figures`: rules for making, styling, captioning, and sourcing figures. Reviews also check them.
- `documents`: equations, citations, and tables in Markdown documents. Reviews also check them.
- `papers-and-proposals`: structuring papers, grants, summaries, and rebuttals, from Mensh and Kording (2017) and the bitsandbrains.io posts.
- `pdf`: build PDFs with `make-pdf` in the house style.
- `slides`: all deck rules, for Marp decks that use the shared theme in `slides/` (New Computer Modern, the same family as the PDFs). A decks repository links `theme/` to `slides/theme`.

## Remembering your decisions

```
unified-review --ignore 5,7 --note "intentional"
unified-review --applied 3
unified-review --unignore D2
```

Each decision goes into `decisions.json` in the runs folder, per reviewed file. The next review tells the panel which points you declined and which changes you already applied. A new finding that a voter matches to a declined point, or that quotes the same text, is held back and listed under "Previously declined" instead. A decline lasts while its quoted text is still in the file. Rewrite the sentence and the point can come back. Recording takes a fraction of a second and adds no model calls.

## PDFs

`make-pdf FILE.md` builds a PDF in a consistent style: New Computer Modern (Sans Bold headings, Book body, Book math), 1 in margins, 11 pt, justified, two-tone links, a rule under each table row, and references on a new page (set `references-page-break: false` in the front matter to keep them inline). It passes pandoc only the cited bibliography entries, and builds anyway, without a reference list, when the bibliography cannot be read. SVG figures are converted on the fly. `install.sh` installs the fonts. The style lives in `typeset/pdf-preamble.tex` and `typeset/pdf-filters.lua`, which a project with its own build can include.

## Install

You need Python 3.9 or later, macOS or Linux, and these CLIs, logged in:

- [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`)
- [Codex CLI](https://github.com/openai/codex) (`codex`, or the copy inside the ChatGPT app, which the script finds on its own)
- [Cursor CLI](https://cursor.com/cli) (`cursor-agent`)

Then:

```
git clone https://github.com/jovo/agent-council
cd agent-council
./install.sh
```

`install.sh` links `unified-review` and `make-pdf` into `~/.local/bin`, links every skill into `~/.claude/skills`, `~/.codex/skills`, and `~/.cursor/skills`, and installs the fonts into `~/Library/Fonts` (`~/.local/share/fonts` on Linux). It does not overwrite real files. If a CLI lives somewhere unusual, set `CLAUDE_BIN`, `CODEX_BIN`, or `CURSOR_BIN` to its path.

### In a GitHub Codespace

This setup has not been tried in a live codespace yet. To run the tool in the cloud instead of on your Mac, name this repository as your dotfiles repository in your [GitHub Codespaces settings](https://github.com/settings/codespaces). Every codespace you create then runs `install.sh`, which also runs `codespaces/setup.sh`. That script installs the three CLIs, poppler, and Ghostscript, and sets `UNIFIED_REVIEW_PORT` to 8737 so the review page keeps one address. Log in to each CLI once per codespace. Or store a `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` and a `CURSOR_API_KEY` as Codespaces secrets. Codex has no such token for a subscription, so run `codex login`.

In a codespace, `unified-review --page FILE` prints the page's forwarded address (`https://<codespace>-8737.app.github.dev/`), which only your GitHub account can open, and opens it in your browser. `unified.md` opens in the codespace's editor. Edits go to the checkout in the codespace, so commit and push them from there. The model calls use your subscriptions, as on a Mac. The codespace itself uses your monthly Codespaces allowance and stops after its idle timeout, which you can raise in the same settings.

## Review rules

Reviewers follow a set of review rules. The first one found wins: `--rules FILE`, then `$UNIFIED_REVIEW_RULES`, then the `# Writing and review guidelines` section of your `~/.claude/CLAUDE.md`, then the same section of this repo's [`CLAUDE.md`](CLAUDE.md). The script reads `~/.claude/CLAUDE.md` as plain text and does not follow its `@` imports, so a `~/.claude/CLAUDE.md` that only imports other files falls through to this repo's copy. The script tells reviewers to ignore any cap on findings or ordering rule in those rules, because it orders findings itself.

## CLAUDE.md

`CLAUDE.md` is the author's general instructions for coding agents: communication, sourcing, engineering, writing, and review. It is here as an example, not something the tool needs.

## Limits

- Grouping duplicates depends on voters flagging them. Two findings that make the same point about different sentences can both survive.
- Anonymizing reviewers reduces self-preference but does not remove it, since models can recognize their own text. Voting by all panelists limits how much any one model's bias moves the result.
- Reviews run without web search. Factual claims are tagged unverified unless you run `--verify`.
- A carried-over confirmation is not rechecked, so a source that later moves or changes goes unnoticed until the sentence changes.
- The fact-check marks a claim with the most cautious verdict across checkers. A checker that fails to find a source pulls a claim down to "plausible" even when another confirmed it.

## Tests

```
python3 -m unittest discover tests
```

The tests use made-up fixtures and fake CLI calls, so they run offline and make no model calls.

## License

MIT. See [LICENSE](LICENSE).
