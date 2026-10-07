# Review rules

These rules go to every reviewer on the panel. Replace them with your own by passing `--rules FILE`, setting `UNIFIED_REVIEW_RULES`, or adding a `# Writing and review guidelines` section to `~/.claude/CLAUDE.md`.

Reviewer instructions for feedback on drafts. This covers verification and how findings get reported.

### Factual claims

- Reviewers have no web access, so they do not verify or tag claims.
- Flag a claim that needs a source and lacks one, or that looks wrong on its face, and say why.
- Run with `--verify` to check claims with web search. That pass tags each claim `[confirmed: source]`, `[plausible, unverified]`, or `[unverifiable: recommend cut or hedge]`.

### What to flag

- Logical gaps, overstated claims, unaddressed counterarguments, internal redundancy.
- Violations of the project's own style rules, if it has any.

### What not to touch

- Argument structure and section order, unless actually broken (a claim doesn't follow, or a section contradicts another one elsewhere). Don't restructure a passage that already works.
- Equations and notation. Flag an equation or symbol that is wrong, unused, or redundant, but do not remove one only to make the prose read faster.

### Output format

- Start with an overview: findings about the whole draft or its structure, most severe first. Then work through the draft from top to bottom, under its section headings, giving findings in the order of the text they target. Label each finding's severity: **Critical** (breaks the argument or is factually wrong), **Substantive** (weakens the argument or is unclear), or **Polish** (style, phrasing). Enumerate every finding with a sequential integer that runs through the whole response, overview first, so a finding can be cited by number alone. For each finding, state the point, then immediately show its diff, before moving to the next finding. Do not collect all diffs into a separate list at the end.
- Show every diff as an **inline revision of the original text**, not as a `Replace:` / `With:` pair. Strike deletions with `~~tildes~~`. Bold each addition and prefix it with `🟢 `. Tildes mark deletions only, never additions. Leave genuinely unchanged sentences plain, and for a mostly-rewritten paragraph strike the whole old block and follow it with the whole new one rather than a word-level diff.

### Math and markup inside a diff

The inline form needs the surrounding Markdown to render, so anything in the quoted text that is itself Markdown or LaTeX has to be handled deliberately.

- **Math carried along as unchanged context**: leave it in whatever form the source uses. Inline math stays `$...$`, display equations stay `$$...$$` on their own lines with blank lines around them, which is what GFM needs to render them at all.
- **When the edit itself targets math or markup source** (an equation's internals, a `\tag{}`, an anchor, table pipes, a citation key): put that diff in a fenced code block instead, with the old and new lines one above the other. Rendering it would hide the exact characters being changed, which are the point.
- Never rewrite `$...$` into `$$...$$` just to make a diff render. That changes inline math into a display equation and silently edits the source.
