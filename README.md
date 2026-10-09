# agent-council

[![License: MIT](https://img.shields.io/github/license/jovo/agent-council)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/jovo/agent-council)](https://github.com/jovo/agent-council/commits/main)

agent-council has models from three labs review the same draft, vote on each other's findings, and merge them into one review. You work through the review in a local web page that shows your draft with each finding highlighted in place. **Accept** writes the change into your file.

It drives the coding-agent CLIs you already use (Claude Code, Codex, and Cursor), so it runs on your existing subscriptions and needs no API keys, except in the cloud. The command is `unified-review`. The repo also holds the writing skills its reviewers apply, and the house style for PDFs and slide decks.

## Quick start

Pick one of three ways in:

1. [In the cloud](#in-the-cloud): click a button, paste three API keys, and drop a file on a web page. No install.
2. [With Claude](#with-claude): ask the Claude desktop app for a review, and it installs everything and runs the commands for you.
3. [In a terminal](#in-a-terminal): clone, install, and run it yourself.

### In the cloud

*Untested.* [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/jovo/agent-council)

The button opens GitHub's create page, which asks for three API keys: `ANTHROPIC_API_KEY` from the [Claude Console](https://console.anthropic.com/settings/keys), `CODEX_API_KEY` from [OpenAI](https://platform.openai.com/api-keys), and `CURSOR_API_KEY` from the [Cursor dashboard](https://cursor.com/dashboard). GitHub saves them as your Codespaces secrets, so you enter them once. The codespace installs everything on first start, which takes a few minutes, then opens the upload page in a new tab. Only your GitHub account can open it. Reviews bill to those API keys rather than to your Claude, ChatGPT, or Cursor subscriptions, and the codespace uses your monthly Codespaces allowance. To come back later, open [your codespaces](https://github.com/codespaces) and pick this one.

### With Claude

In the Claude desktop app, open the Code tab, choose the folder that holds your draft, and ask:

> Install https://github.com/jovo/agent-council and give me a unified review of my-draft.md.

Claude reads this README, runs the install, and asks before each command. If a model CLI is missing or logged out, it says which one and opens the sign-in in your browser. The review page then opens, and **Accept** writes into your draft. After the first time, ask for "a unified review of my-draft.md."

### In a terminal

```
git clone https://github.com/jovo/agent-council
cd agent-council
./install.sh
unified-review example.md
```

[`example.md`](example.md) is a short proposal with planted flaws: overclaims, a conclusion that does not follow from its evidence, and two typos. Its review takes about 30 seconds, and a 1,300-word memo takes 40 to 120. For a Markdown file, the review page then opens in your browser. Click a highlighted passage to see its finding, then Accept, Edit, or Decline it. Click **Re-review** to review the revised text. Accept writes into `example.md`, and `git checkout example.md` restores it. [Install](#install) lists what you need first.

To review a PDF, or a file you want left unchanged, run `unified-review --upload`. A page opens where you drop or choose a PDF, Markdown, text, or TeX file. The panel reviews a copy, and the page shows the unified review when it finishes, with a button to download it as Markdown. Nothing is written back to your file.

## Why a panel that votes

A single model reviewing a draft misses things another model catches. A single model merging several reviews favors its own findings: LLM evaluators recognize their own outputs and rate them higher (Panickssery et al. 2024, [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)). A panel of judges from different model families tracks human judgments more closely than one large judge and shows less intra-model bias (Verga et al. 2024, [arXiv:2404.18796](https://arxiv.org/abs/2404.18796)).

So no single model decides. Each model reviews independently. Every model then votes on the other models' findings, never its own, with reviewers anonymized. The script, not a model, groups duplicates and reports a finding only when two models stand behind it. Andrej Karpathy's [llm-council](https://github.com/karpathy/llm-council) is a precursor.

That design follows the evidence above, but it has not been tested on its own output yet. No benchmark shows how many real errors the panel catches, or whether majority rejection sets aside real ones.

## The review page

The page shows the current draft, set in New Computer Modern like the PDFs and decks. Front matter and HTML-only lines are hidden, and tables are drawn as tables. Bold, italics, links, and lists render as in the PDFs: cross-references and URLs in blue, citations in green, and nested bullets as filled disc, open circle, and filled square. Citations show as numbers linked to a References list below the draft, formatted by pandoc in the PLOS style the book uses (`typeset/plos.csl`), with DOIs linked. Each finding is highlighted by severity on the words its change touches. The card for the selected finding shows its type, point, diff, and votes. Clicking the card scrolls the draft to its passage.

**Acting on a finding**

- **Accept** writes the change into the file and records it as applied. It re-reads the file first and finds the passage, allowing for small misquotes by the reviewers. If you have since changed that passage, it refuses and leaves the file alone. A diff that skips text with "…" applies part by part and keeps the skipped text.
- **Edit** lets you change the proposed text before writing it. **Decline** records the decision with an optional note, and later reviews do not raise that point again while its text stands.
- **Mark done** appears when the passage changed after the review, for a finding you already fixed by hand. It records the finding as applied without writing anything.
- **Ask** sends a question about the finding to every panelist in parallel. Answers appear as each model finishes. An answer that revises the change gets its own **Accept this version**.
- A finding with no exact diff, such as one about the whole draft, cannot be accepted. Its card says why and copies a request you can paste to an agent.

**Typos and checks**

- **Typos** are fixes that change one word by a letter or two, or remove a doubled word, that no voter other than the one that raised them disputed. They are listed together in their own card, all checked, with one Accept, and are not highlighted in the draft.
- **Checks** lists problems the script finds without a model: equation tags out of order or duplicated, references to missing equations or figures, uncited figures, links to missing anchors, citation keys not in the bibliography, terms written both hyphenated and closed, and double spaces. Double spaces have a **Fix** button. Checks are recomputed from the current text each time the page loads.

**Choosing what to see**

- When a review has open logic findings, the page shows only those at first, since a passage whose argument fails may be rewritten anyway. A banner says so and links to everything.
- Dropdowns filter by type (logic, evidence, clarity, style), severity, agreement (unanimous, majority, contested), and status. **Accept all shown** applies every open finding the filters select.
- A finding the panel has raised before shows "in N reviews".

**Working on the whole draft**

- **Summary**, shown by default at the top right, summarizes the reviews. Claude Sonnet groups the findings into themes and writes a sentence or two on where the panel agreed and split. Each theme is a bullet with a one-sentence gist, and its findings are listed beneath it by title, linked to the finding. Until the themes arrive, the card lists the Critical and Substantive findings. The summary is written the first time the page opens a review and kept as `summary.json` in the run folder. The **Summary** button shows or hides it.
- **Open…** opens a new tab where you drop a draft from Finder, or click **Choose in Finder…** (macOS). A draft dropped anywhere on the review page works the same way. Obsidian gives a dragged note to no other app, so drag it from Finder (Reveal in Finder in Obsidian). A browser does not tell a page where a dropped file lives, so the server finds the original with Spotlight: the one file with the same name and the same bytes. If it finds none (an unindexed folder) or several identical copies, it says so and reviews nothing. It never reviews a copy. The chosen file is reviewed in place, as `unified-review FILE` would, and the tab becomes its review page, so several reviews can be open at once. A file reviewed before opens straight to its page, where **Re-review** runs a new review.
- **Download** saves the review as Markdown: the theme summary, then every finding with its proposed change and votes. It is the run's `unified.md`, so it takes no model calls.
- **Ask** beside **Accept all shown** sends a question, comment, or request about the whole draft ("tighten the wedge section") to every panelist. Edits they propose appear with their own Accept. Tick "Use as focus for the next Re-review" to pass the comment to the next review.
- Double-click any paragraph, heading, or table to edit its Markdown in place. Save writes it back, unless it changed in the file since the page loaded.
- **Panel** chooses the models for Re-review and Ask, saved per file. Its menu lists models by lab, model, version, and setting: those Claude Code and Codex run directly, and every model `cursor-agent models` lists.
- **Re-review** runs a new review of the current text and loads it. The header gives when the review ran and says "edited since" once the file differs.
- Keys: `j` and `k` move between findings, `a` accepts, `e` edits, `d` declines, `q` asks, and ⌘Enter saves an edit or sends a question.

The page is served by a small server inside `unified-review`, using only Python's standard library. It listens only on your machine, serves one file, and exits after 8 hours without use. `unified-review --page FILE` reopens it.

## How a review runs

```
unified-review [-n FOCUS] [-p PANEL] [--context FILE]... [--verify] [--rules FILE] [-o OUTDIR] FILE [FILE...]
```

1. **Preflight.** The script checks that each CLI is installed and logged in. A panelist that is missing or logged out is dropped and listed as failed, never silently.
2. **Review.** Each panelist reviews the draft without web search and returns findings in a fixed format: severity (Critical, Substantive, Polish), kind (logic, evidence, clarity, style), title, the exact text targeted, the point, and an inline diff. A reviewer that finds nothing worth changing says so. Each review also receives the last review's open findings, so a point that still applies comes back in the same words, and the points you declined or applied.
3. **Vote.** Each panelist votes agree, partial, or disagree on every other model's finding, sees reviewers only as A, B, and C, flags duplicates, and votes on severity and kind. It does not vote on its own findings, which it sees only to name duplicates.
4. **Merge.** The script groups duplicates (two voters calling them duplicates, or one voter plus overlapping quoted text) and keeps the best-voted version of each. It reports a finding only when two models stand behind it: a second model raised the same point, or another model voted agree or partial. It takes the median severity and majority kind of the other models' votes. It holds back findings that would restore earlier wording, or change a passage that keeps changing: after one change, only Critical and Substantive findings on that passage show, and after two changes in the last three versions, only Critical ones. It then runs the checks and writes `unified.md`.
5. **Fact-check (optional, `--verify`).** A background process lists the draft's checkable claims, has each panelist check them with web search, keeps the most cautious verdict per claim, and writes `factcheck.md`. A claim the last fact-check confirmed keeps that verdict while its sentence is unchanged.

A model call that times out, errors, or returns nothing gets one retry, except after a login error, and so does a reply in the wrong format.

The default panel is one model per lab, chosen for speed: Claude Sonnet (via `claude`), GPT-5.6 Luna at low effort (via `codex`), and Gemini 3.8 Flash Low (via `cursor-agent`). If a panelist fails, Grok 4.7 Low Fast (via `cursor-agent`) stands in, so three models still vote. Grok cannot stand in for Gemini when `cursor-agent` itself is down. The fact-check uses stronger Claude and GPT models, since it runs in the background. Choose other models with `-p`, for example `-p claude:opus,codex:gpt-5.6-luna@medium,cursor:kimi-k3-low`, or with **Panel** on the page.

A review adds no per-call cost, since the CLIs run on their subscriptions. An October 2026 test of cheaper pay-per-token models on the same memo found none that replaced the panel. DeepSeek V4 Flash and gpt-oss-120b on Together AI cost about $0.004 per model per round. They returned 3 and 6 findings, where the panel's models returned 5 to 21, and 2 of gpt-oss-120b's 6 quotes did not match the draft. Open-weight models through `cursor-agent` (GLM 5.2, Kimi K3) took 60 to 270 seconds per review, against 13 to 22 for Gemini and GPT.

## What you can review

- **Markdown** gets the full treatment: the page, checks, carry-over, and churn guards. Several files can be reviewed together, and the review then goes to `unified.md` only.
- **Slide decks.** A Markdown file whose front matter says `marp: true` is reviewed as a talk (`--slides` forces it). Reviewers and voters also get the `slides` skill's deck rules and are told not to flag what those rules call for, such as fragments without full stops. Findings are labeled by slide ("Slide 4: Results hold across scales"), the page draws a break between slides, and Checks adds deck rules a script can test: a plain list of more than three items, more than one takeaway on a slide, HTML the rules forbid (`style=`, `<br>`, `<p>`, `<strong>`, `<em>`, `<mark>`), and three content slides in a row without a figure. Reference and reading slides, and slides after an Appendix divider, are exempt from the last. Rendering checks such as overflow stay with `npm run check` in the decks repository.
- **PDF.** A PDF is first converted to Markdown by Claude, with its links, under `~/.local/share/unified-review/runs/converted/`. The script checks the conversion word by word against the PDF's text and prints any words missing or added. The Markdown is then reviewed like any Markdown file, with line numbers and the review page. Reviewing the same PDF again reuses its Markdown and your edits to it. With `--no-md`, a plain-prose PDF reaches the panel as text, and one with figures, images, ruled tables, or equations is opened by each panelist directly. Findings then cite pages, and edits go in the source document. This needs Ghostscript and poppler (`brew install ghostscript poppler`).
- **Supporting material** (`--context FILE`, repeatable): reviewer comments, a call for proposals, or a source paper that every panelist and voter reads but does not review. Text or PDF.
- **Focus** (`-n "..."`): extra instructions for this review.
- **Review rules.** The first found wins: `--rules FILE`, then `$UNIFIED_REVIEW_RULES`, then the `# Writing and review guidelines` section of `~/.claude/CLAUDE.md`, then the same section of this repo's [`CLAUDE.md`](CLAUDE.md). Either CLAUDE.md section is followed by the "Reviewer rules" section of the [`unified-review` skill](skills/unified-review/SKILL.md). The script reads `~/.claude/CLAUDE.md` as plain text and does not follow its `@` imports. Reviewers also apply the `logic`, `statistics`, `figures`, and `documents` skills. The script tells reviewers to ignore any cap on findings or ordering rule, because it orders findings itself.

## Output

Each run writes a folder under `~/.local/share/unified-review/runs/` (or `$UNIFIED_REVIEW_RUNS`), outside the project, named `<date>-<time>-<project>-<file>-v<N>`, such as `2026-10-08-1342-myproject-memo-v7`. Versions count up like SVN revisions: version 1 is the first text of a file reviewed, and unchanged text keeps its number. Each folder holds:

- `unified.md`: the review.
- `factcheck.md` (with `--verify`): each claim in draft order, with each checker's verdict, notes, and sources.
- `reviewed/`: an exact copy of the text reviewed.
- `results.json`, `factcheck.json`: findings, votes, groups, verdicts, checks, the text's fingerprint and git commit, and per-stage timings.
- `review-<model>.md`, `votes-<model>.txt`, `*.err`: raw panel output and logs.

`unified.md` gives findings by severity. Within each severity, findings about the whole draft come first, then findings in draft order, then findings about the focus material. Each shows its section, file, and line, the point, an inline diff (~~deleted~~ and 🟢 **added**), and the votes, as in `Claude ✓ · **GPT** raised · Gemini ~` (✓ agree, ~ partial, ✗ disagree). The text being changed appears once, in the diff. A finding without a diff quotes the text it is about. **Contested** means at least one model other than the raiser agreed and at least one disagreed. Then come these sections, each only when it has entries:

- **Since the last review:** earlier findings this review did not repeat, resolved if their passage changed.
- **Checks** and **Typos**, as on the page.
- **Previously declined:** new findings that match a point you declined.
- **Held back to stop churn**, with the reason for each.
- **Not reported**: findings no second model backed, one line each with the model that raised it.
- **Agreement:** ordinal Krippendorff's alpha over the votes, with a bootstrap 95% confidence interval over findings, leaving out each model's votes on its own findings. Most votes are "agree", and that imbalance pulls alpha down even when raw agreement is high.

For one Markdown file the page opens. Otherwise `unified.md` opens in Cursor or VS Code if you ran the command there, or in your default Markdown app. Inside the Claude or Codex app, the script prints `OPEN IN APP: <path>`. Set `UNIFIED_REVIEW_OPEN_APP` to always use one app.

## Working with agents

The `unified-review` skill lets Claude Code, Codex, and Cursor run a review and act on its findings by number ("address 3", "apply 2, 4, 7", "fix K5"). Before an agent edits, it runs:

```
unified-review --item 3,7,K2 [--run DIR]
```

This prints the items from the newest run for a file in the current folder: the file's path, whether it changed since the review, each item's current line, the quoted text, votes, and diff, and the whole current file with line numbers.

To iterate, ask an agent to "iterate on FILE" (3 rounds by default) or "iterate 5 rounds". Each round reviews, applies findings every voter agreed with plus Critical and Substantive findings a majority agreed with, records the rest as declined, and reviews again. It stops early when nothing qualifies, then lists the contested and whole-draft findings it skipped. Each version is saved beside the file as `memo-v7.md`, `memo-v8.md`, and so on, with a pattern added to `.gitignore`, and `memo-v7-to-v10.md` shows every change since the start. The loop uses `unified-review --snapshot FILE` and `unified-review --changes N FILE`, which also work alone.

Decisions can also be recorded from the command line:

```
unified-review --ignore 5,7 --note "intentional"
unified-review --applied 3
unified-review --unignore D2
unified-review --decisions
```

They go into `decisions.json` in the runs folder, per file. A decline lasts while its quoted text is in the file. Rewrite the sentence and the point can come back.

## Also in this repo

- **Skills.** `install.sh` links each folder in `skills/` into Claude Code, Codex, and Cursor, which load a skill when a task matches it:
  - `unified-review`: run the panel and act on its findings.
  - `logic`: check an argument from the document's arc down to a sentence. Reviews apply it.
  - `statistics`: experimental design and inference from data. Reviews apply it.
  - `figures`: making, styling, captioning, and sourcing figures. Reviews apply it.
  - `documents`: equations, citations, and tables in Markdown. Reviews apply it.
  - `papers-and-proposals`: structuring papers, grants, summaries, and rebuttals, from Mensh and Kording, "Ten simple rules for structuring papers" (*PLOS Computational Biology*, 2017, [doi:10.1371/journal.pcbi.1005619](https://doi.org/10.1371/journal.pcbi.1005619)), and the posts at [bitsandbrains.io](https://bitsandbrains.io/).
  - `pdf` and `slides`: building PDFs and Marp decks in the house style.
- **PDFs.** `make-pdf FILE.md` builds a PDF in New Computer Modern (Sans Bold headings, Book body and math), 1 in margins, 11 pt, justified, with a rule under each table row and references on a new page (`references-page-break: false` keeps them inline). It passes pandoc only the cited bibliography entries and builds without a reference list when the bibliography cannot be read. SVG figures are converted on the fly. The style lives in `typeset/`, which a project with its own build can include.
- **Slides.** The Marp theme in `slides/` uses the same type family. A decks repository links `theme/` to `slides/theme`.
- **[CLAUDE.md](CLAUDE.md)** is the author's general instructions for coding agents. It is an example, not something the tool needs, except as the fallback review rules.

## Install

You need Python 3.9 or later, macOS or Linux, and these CLIs, logged in:

- [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`)
- [Codex CLI](https://github.com/openai/codex) (`codex`, or the copy inside the ChatGPT app, which the script finds on its own)
- [Cursor CLI](https://cursor.com/cli) (`cursor-agent`)

Then run `./install.sh`. It links `unified-review` and `make-pdf` into `~/.local/bin`, links every skill into `~/.claude/skills`, `~/.codex/skills`, and `~/.cursor/skills`, and installs the fonts into `~/Library/Fonts` (`~/.local/share/fonts` on Linux). It does not overwrite real files. If a CLI lives somewhere unusual, set `CLAUDE_BIN`, `CODEX_BIN`, or `CURSOR_BIN`.

**In a GitHub Codespace (untested).** To run the tool in the cloud instead of on your Mac, name this repository as your dotfiles repository in your [Codespaces settings](https://github.com/settings/codespaces). Every new codespace then runs `install.sh`, which runs `codespaces/setup.sh` to install the three CLIs, poppler, and Ghostscript, and fixes the page's port at 8737. Log in to each CLI once per codespace, or store a `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY`, a `CODEX_API_KEY`, and a `CURSOR_API_KEY` as Codespaces secrets. `unified-review --page FILE` then prints the page's forwarded address, which only your GitHub account can open. Edits go to the codespace's checkout, so commit and push from there. The codespace uses your monthly Codespaces allowance and stops after its idle timeout.

## Limits

- Grouping duplicates depends on voters flagging them. Two findings that make the same point about different sentences can both survive.
- Anonymizing reviewers reduces self-preference but does not remove it, since models can recognize their own text.
- Reviews run without web search. Factual claims are checked only with `--verify`.
- The fact-check keeps the most cautious verdict, so a checker that fails to find a source pulls a claim down to "plausible" even when another confirmed it. A carried-over confirmation is not rechecked until its sentence changes.
- The churn guards count your own rewrites as changes, so Polish findings on a passage you just rewrote wait one round.

## Tests

```
python3 -m unittest discover tests
```

The tests use made-up fixtures and fake CLI calls, so they run offline and make no model calls.

## License

MIT. See [LICENSE](LICENSE).
