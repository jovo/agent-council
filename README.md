# agent-council

agent-council has models from different labs review the same document, vote on each other's findings, and merge the result into one review you read top to bottom. It drives the coding-agent CLIs you already use (Claude Code, Codex, and Cursor), so it needs no API keys beyond your existing logins.

The command is `unified-review`. A skill of the same name lets Claude Code, Codex, and Cursor run it and act on its findings by number ("address 3", "apply 2, 4, 7", "fix K5").

## Why a panel that votes

A single model reviewing a draft misses things another model catches. A single model merging several reviews favors its own findings. LLM evaluators recognize their own outputs and rate them higher (Panickssery et al. 2024, [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)). A panel of judges from different model families tracks human judgments more closely than one large judge and shows less intra-model bias (Verga et al. 2024, [arXiv:2404.18796](https://arxiv.org/abs/2404.18796)).

So agent-council does not let any one model decide. Each model reviews independently. Every model then votes on every finding, with reviewers anonymized. The script, not a model, groups duplicates and sets aside findings most voters reject. Andrej Karpathy's [llm-council](https://github.com/karpathy/llm-council) is a precursor to this.

## How it works

```
unified-review [-n FOCUS] [-p PANEL] [--verify] [--rules FILE] [-o OUTDIR] FILE [FILE...]
```

Before starting, the script checks that each CLI is logged in, using its status command, and drops any panelist that is not.

1. **Review.** Each panelist reviews the draft without web search. Findings come back in a fixed format: severity, title, the exact text targeted, then the point and an inline diff.
2. **Vote.** Each panelist votes agree, partial, or disagree on every finding, sees reviewers only as A, B, C, and flags duplicates.
A model call that times out, errors, or returns nothing gets one retry, except after a login error. A reply in the wrong format also gets one retry.

3. **Render.** The script groups duplicates (two voters calling them duplicates, or one voter plus overlapping quoted text), keeps the best-voted version of each, sets aside findings a majority rejects, and writes `unified.md`. The file opens where you ran the command: in Cursor or VS Code if you ran it there, in your default Markdown app from a terminal. Inside the Claude or Codex app, the script prints `OPEN IN APP: <path>` and the skill has the agent show the file. Set `UNIFIED_REVIEW_OPEN_APP` to always use one app.
4. **Fact-check (optional, `--verify`).** A detached background process lists the draft's checkable claims, has each panelist check them with web search, keeps the most cautious verdict per claim, writes `factcheck.md`, and opens it.

The default panel is one model per lab, chosen for speed: Claude Sonnet (via `claude`), GPT-5.6 Luna at low effort (via `codex`), and Gemini 3.8 Flash Low (via `cursor-agent`). `grok` is also available. The fact-check uses stronger Claude and GPT models, since it runs in the background. Edit `PANELISTS` and `FACTCHECK_PANELISTS` at the top of `bin/unified-review` to change them.

On one 1,300-word memo, a review took 40 to 120 seconds and the fact-check about 2 more minutes. Times depend on the models, the draft, and the providers' load.

## Output

Each run writes a folder under `~/.local/share/unified-review/runs/`, outside every project, named like SVN revisions, `<project>-<file>-v<N>`, with `-run2`, `-run3` when the same version is reviewed again, so nothing is added to the project you review. Set `UNIFIED_REVIEW_RUNS` to put runs elsewhere. Each run folder holds:

- `unified.md`: the review. See [Reading unified.md](#reading-unifiedmd).
- `factcheck.md` (with `--verify`): each claim in draft order, with its sentence, each checker's verdict, notes, and sources.
- `reviewed/`: an exact copy of the text reviewed. The title of `unified.md` gives its version number, and `results.json` its fingerprint and git commit.
- `results.json`, `factcheck.json`: findings, votes, groups, verdicts, and per-stage timings.
- `review-<model>.md`, `votes-<model>.txt`, `*.err`: raw panel output and logs.

## Reading unified.md

- The title is the reviewed file and its version number. Versions count up like SVN revisions: version 1 is the first text of that file reviewed, version 2 the next different text, and unchanged text keeps its number. `versions.json` in that runs folder maps each version to a fingerprint of the exact text. `reviewed/` in the run folder holds a copy of that text, and `results.json` records the fingerprint, git commit, and whether there were uncommitted edits.
- Findings are grouped by severity: Critical, then Substantive, then Polish. Within each group, findings about the whole draft come first, then findings in the order of the draft, then findings about any focus material (`-n`). Each finding shows its draft section, file, and line. Findings most voters rejected come last, with their reasons.
- Each finding is the best-voted version among duplicates. It shows the file and line, the quoted text, the point, an inline diff (~~deleted~~ and 🟢 **added**), and a line of votes such as `Claude ✓ · **GPT** ✓ · Gemini ~`: ✓ agree, ~ partial, ✗ disagree, bold for the model that raised the point.
- **Contested** means at least one model agreed and at least one disagreed.
- **Agreement** is ordinal Krippendorff's alpha over the votes (agree > partial > disagree), with a bootstrap 95% confidence interval over findings. Each model's votes on its own findings are left out. 1 is full agreement, 0 is chance level. Most votes are "agree", and that imbalance pulls alpha down even when raw agreement is high.
- A "Failed" line or a warning appears only when a panelist failed or fewer than two models took part.

## Acting on findings

```
unified-review --item 3,7,K2 [--run DIR]
```

This prints the items from the newest run that reviewed a file in the current folder (else the last run made): the reviewed file's full path, whether it has changed since the review, each item's current line, the quoted text, the votes, the diff, and the whole current file with line numbers. The skill tells agents to run it before giving an opinion on an item or editing, so they work from the current text.

## Skills

`install.sh` links every folder in `skills/` into Claude Code, Codex, and Cursor, which load a skill when a task matches its description:

- `unified-review`: run the panel review and act on its findings by number.
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

`make-pdf FILE.md` builds a PDF in a consistent style: New Computer Modern (Sans Bold headings, Book body, Book math), 1 in margins, 11 pt, justified, two-tone links, a rule under each table row, and references on a new page. It passes pandoc only the cited bibliography entries. `install.sh` installs the fonts. The style lives in `typeset/pdf-preamble.tex` and `typeset/pdf-filters.lua`, which a project with its own build can include.

## Install

You need Python 3.9 or later, macOS (the script uses `open` and notifications), and these CLIs, logged in:

- [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`)
- [Codex CLI](https://github.com/openai/codex) (`codex`, or the copy inside the ChatGPT app)
- [Cursor CLI](https://cursor.com/cli) (`cursor-agent`)

Then:

```
git clone https://github.com/jovo/agent-council
cd agent-council
./install.sh
```

`install.sh` links `unified-review` into `~/.local/bin` and the skill into `~/.claude/skills`, `~/.codex/skills`, and `~/.cursor/skills`. It does not overwrite real files.

## Review rules

Reviewers follow a set of review rules. The first one found wins: `--rules FILE`, then `$UNIFIED_REVIEW_RULES`, then the `# Writing and review guidelines` section of your `~/.claude/CLAUDE.md`, then the same section of this repo's [`CLAUDE.md`](CLAUDE.md). The script tells reviewers to ignore any cap on findings or ordering rule in those rules, because it orders findings itself.

## CLAUDE.md


## Limits

- Grouping duplicates depends on voters flagging them. Two findings that make the same point about different sentences can both survive.
- Anonymizing reviewers reduces self-preference but does not remove it, since models can recognize their own text. Voting by all panelists limits how much any one model's bias moves the result.
- Reviews run without web search. Factual claims are tagged unverified unless you run `--verify`.
- The fact-check marks a claim with the most cautious verdict across checkers. A checker that fails to find a source pulls a claim down to "plausible" even when another confirmed it.

## Tests

```
python3 -m unittest discover tests
```

The tests use made-up fixtures and fake CLI calls, so they run offline and make no model calls.

## License

MIT. See [LICENSE](LICENSE).
