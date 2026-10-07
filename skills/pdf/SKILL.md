---
name: pdf
description: Build PDFs from Markdown in the house style with make-pdf (pandoc, XeTeX, New Computer Modern). Use whenever the task makes, exports, prints, or restyles a PDF of a document, memo, paper, or chapter.
---

# PDFs

Build PDFs from Markdown with `make-pdf FILE.md` (from `~/github/agent-council`, on the PATH via its `install.sh`). It applies the house style through `typeset/pdf-preamble.tex` and `typeset/pdf-filters.lua`. A project with its own build (for example a book) includes that preamble and keeps these defaults. Do not hand-roll a different pandoc or LaTeX setup.

- Pandoc with XeTeX (tectonic), about 3 s for a memo. Only the cited bibliography entries are passed to pandoc. The PDF builds even when references fail: a missing key shows as unresolved, and an unreadable bibliography (missing file, unreachable URL) is replaced by an empty one with a warning. Margins 1 in, 11 pt, justified text. No title page: start at the document's own H1. References start on a new page under a "References" heading. To keep them on the same page, set `references-page-break: false` in the front matter.
- Fonts: New Computer Modern, the same family as the deck theme. New Computer Modern Sans Bold for headings (# 21 pt, ## 14 pt, ### 12 pt, #### body size), New Computer Modern Book for body text, New Computer Modern Math Book for math. `install.sh` installs them from `typeset/fonts`.
- Links in two tones: cross-references and URLs in blue `#1A4D8F`, citations in green `#2E7D5B`. Citation numbers and DOIs are links.
- Nested list markers follow Google Docs: filled disc, open circle, filled square. Tables get a rule under each row.
- Characters the text font lacks (≤ ≥ ≠ ≈ ↔ ⇒ ✓ ✗) are drawn from the math font, so they can be typed directly. Write primes in math (`$5'$`): a ′ typed in prose prints blank.
- Manual page break: `<div style="page-break-after: always;"></div>`, which Obsidian honors and the PDF build turns into a page break.
- Figures: SVG works directly. Pandoc converts it to vector PDF during the build with `rsvg-convert` (Homebrew `librsvg`). The caption is the italic line under the image, so alt text never prints as a second caption.
- Footnotes: do not reuse a `[^N]` marker. Obsidian and GitHub link a reuse back to one note, but the PDF prints it as a new, renumbered footnote.
- Slide decks use the same family through the deck theme (`slides/theme`), so documents and decks match.
