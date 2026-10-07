---
name: documents
description: Rules for equations, citations, and tables in Markdown documents (papers, chapters, memos, reports, grants). Use whenever the task writes or edits display math, adds or fixes citations or a bibliography, or creates a table.
---

# Documents

## Equations

- Display equations use `$$…\tag{N}$$` with sequential integer `N` per chapter.
- In-text refs are `Eq. (N)`.
- Define every symbol in prose before its first equation. No forward definitions.
- Optimization problems follow Boyd & Vandenberghe (minimize / subject to structure).
- Use `\begin{array}`, never `\begin{align}` or `\begin{equation}`. Test equations on GitHub before finalizing.

**GitHub rendering:** GitHub's math parser (MathJax) is strict about LaTeX environments. To ensure equations render reliably on GitHub, Obsidian, and all downstream builds:
- **Use `\begin{array}…\end{array}`** for all displayed equations, wrapping with `$$…\tag{N}$$`. This is the safest format.
- **Avoid `\begin{equation}`, `\begin{align}`, and nested environments** — they cause rendering failures on GitHub.
- **Use plain `\\` for line breaks** in arrays; never `\\[6pt]` or other spacing syntax (renders as literal text).
- **Use `\left[` and `\right]`** for large brackets spanning aligned rows, or plain `[` for simple cases. Avoid splitting brackets across lines.
- **Use `\middle|` for conditioning bars** (e.g., in expectations: `\mathbb{E}[\cdots \middle| \cdots]`).
- **Keep long equations on one line** where possible. If multi-line, use simple array rows with `\\` between them.
- **Test critical equations** by viewing the committed `.md` file on GitHub before finalizing — GitHub's preview is the gold standard.

## Citations

- **Which bibliography.** If the project uses a shared bibliography, follow that bibliography's own instructions. Otherwise follow the project's citation instructions. For a ready-made shared bibliography (Zotero, Better BibTeX, one `references.bib` for many repos, with agent instructions), see [jovo/bib](https://github.com/jovo/bib).
- Never invent a citation key. Look it up in the project's bibliography.
- With pandoc, cite in prose as `[@Key]` or `[@Key1; @Key2]`. Do not hand-roll `[k]` numbers. Citeproc numbers references and collapses three or more consecutive ones into a range.
- Include a DOI or stable URL for each entry. For open-access sources, note the license.
- **Cite the published version, not the preprint.** If a paper appeared in a journal or at a conference, the entry carries that venue and its DOI. An arXiv or bioRxiv URL is a fallback for work that is genuinely unpublished, and an entry that names a venue should never link to arXiv instead of to the DOI. When citing a preprint because no published version exists, say so in a `note` field so a later pass can upgrade it.

## Tables

- Markdown pipe tables. Keep to ≤8 rows and ≤6 columns where possible; larger tables go in an appendix.
- Number tables per chapter as `Table C.N`. Put `<a id="table-C-N"></a>` on its own line immediately above the italic caption, and reference every table from prose as a link: `[Table C.N](#table-C-N)` same-file, `[Table C.N](<chapter>.md#table-C-N)` cross-file.
- Every numeric column carries its unit in the header, e.g. "Conduction velocity (m/s)".
