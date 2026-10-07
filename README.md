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

3. **Render.** The script groups duplicates (two voters calling them duplicates, or one voter plus overlapping quoted text), keeps the best-voted version of each, sets aside findings a majority rejects, and writes `unified.md`. The file opens in your default Markdown app.
4. **Fact-check (optional, `--verify`).** A detached background process lists the draft's checkable claims, has each panelist check them with web search, keeps the most cautious verdict per claim, writes `factcheck.md`, and opens it.

The default panel is one model per lab, chosen for speed: Claude Sonnet (via `claude`), GPT-5.6 Luna at low effort (via `codex`), and Gemini 3.8 Flash Low (via `cursor-agent`). `grok` is also available. The fact-check uses stronger Claude and GPT models, since it runs in the background. Edit `PANELISTS` and `FACTCHECK_PANELISTS` at the top of `bin/unified-review` to change them.

On one 1,300-word memo, a review took 40 to 120 seconds and the fact-check about 2 more minutes. Times depend on the models, the draft, and the providers' load.

## Output

Each run writes a folder, `feedback/<file>-<timestamp>/`:

- `unified.md`: an overview, then findings in the order of the draft under its own section headings, then findings about any focus material, then rejected findings with the voters' reasons. Each finding shows the file and line, the quoted text, the point and diff, and one line of votes such as `Claude ✓ · **GPT** ✓ · Gemini ~` (✓ agree, ~ partial, ✗ disagree, bold for the model that raised it). A finding is marked contested when at least one model agreed and at least one disagreed. The header lists any panelist that failed and why, and warns when fewer than two models reviewed or voted. There is no cap on the number of findings.
- `factcheck.md` (with `--verify`): each claim in draft order, with its sentence, each checker's verdict, notes, and sources.
- `reviewed/`: an exact copy of the text reviewed. The header of `unified.md` gives its content fingerprint and git commit.
- `results.json`, `factcheck.json`: findings, votes, groups, verdicts, and per-stage timings.
- `review-<model>.md`, `votes-<model>.txt`, `*.err`: raw panel output and logs.

## Acting on findings

```
unified-review --item 3,7,K2 [--run DIR]
```

This prints the items from the newest run (under `./feedback`, else the last run made anywhere): the reviewed file's full path, whether it has changed since the review, each item's current line, the quoted text, the votes, the diff, and the whole current file with line numbers. The skill tells agents to run it before giving an opinion on an item or editing, so they work from the current text.

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

Reviewers follow a rules file. The first one found wins: `--rules FILE`, then `$UNIFIED_REVIEW_RULES`, then the `# Writing and review guidelines` section of `~/.claude/CLAUDE.md`, then [`rules/default-review.md`](rules/default-review.md). The script tells reviewers to ignore any cap on findings or ordering rule in those rules, because it orders findings itself.

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
