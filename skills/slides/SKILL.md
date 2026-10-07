---
name: slides
description: Make or edit slide decks, slides, presentations, or talks (Marp Markdown with the shared deck theme). Use whenever the task creates, edits, plans, renders, checks, or reviews a deck.
---

# Deck conventions

All decks are Marp/CSS-native unless the user explicitly
asks for a different format. A deck consists of editable Markdown content and the
shared theme `theme/base.css`. Do not create PPTX-first decks or use absolute-positioned HTML extracted from
slides as the source of truth.

At the start of every editing turn, read this file and the deck-local
`CLAUDE.md` (when one exists) in full, even if you read them earlier in the
conversation, then read `theme/base.css`. Render and inspect the result before
declaring the deck done.


## Where the theme lives

The theme (`theme/base.css`, its fonts, and `scripts/check-deck.mjs`) lives in
the agent-council repository under `slides/`. A decks repository links to it,
so every path below is relative to the decks repository root:

```
ln -s ~/github/agent-council/slides/theme theme
ln -s ~/github/agent-council/slides/scripts/check-deck.mjs scripts/check-deck.mjs
```

Run `npm install` once in `~/github/agent-council/slides` for the check script.
Edit the theme there, not through a copy. A change to the theme changes every deck.

## The two rules that matter most

1. **Avoid HTML at all costs.** A deck is Markdown. Before writing any HTML
   tag, check this list of native forms, in order:
   - prose, lists, emphasis, links: plain Markdown
   - takeaway: `> One bold sentence.`
   - italic `*word*`, bold `**word**`, highlighted (accent colour) `***word***`
   - source line: `<!-- _footer: Source: … -->`
   - figure: `![alt](file.svg)` on its own line (several lines = several
     figures)
   - equation: `![alt](assets/equations/x.svg)`
   - image beside text: `cols` with a text cell and a `<figure>` image cell
   - two images: `![bg left:60% contain](a.jpg)` then `![bg contain](b.jpg)`
   - anything table-shaped: a pipe table; yes / partly / no as `●` `◐` `○`
   - full-slide media with a link: `_class: full`, `![bg](…)`,
     `[Play · 2:10](url)`
   - numbered steps: `1.` `2.` `3.`

   HTML is allowed only for what Markdown cannot express: the `cols` /
   `contrast` wrappers, a `<span>` label inside them, a `<figure>` that is a
   column or needs a heading, the paired title `<span>`s, and `<video>`. Never
   use inline `style=`, `<style>` blocks, `<br>` for spacing, or `<p>`,
   `<strong>`, `<em>`, `<mark>` for anything Markdown already does. If you
   reach for any other tag, stop and find the Markdown form, or ask.

2. **`theme/base.css` is finished design. Keep it simple.** Every deck uses
   it unchanged. It has three sizes, two fonts, one bold, three stack
   spacings, and four components (`cols`, `contrast`, `rows-2`, `flow`). When a new
   deck needs something, solve it in this order: existing Markdown form →
   existing component → change the content or the asset (crop the image,
   draw the legend into the figure, split the slide). Propose a change to
   `base.css` only when the pattern will recur across decks, and do not make
   it until the user agrees. A new deck should leave the theme alone or make
   it smaller, never larger.

Before calling a deck done: `npm run check -- <deck>` passes, and the HTML
count (`grep -o '<[a-z]' <deck>/deck.md | wc -l`) has not grown without a
reason you can name.

One deck per folder: `<folder>/deck.md` and its rendered `deck.html`. Do not
keep versioned copies (`deck_v1.md`) in the folder. When a version is done
(presented or sent), tag it in git, `git tag <folder>-vN`; read an old version
with `git show <folder>-vN:<folder>/deck.md`. A migrated deck replaces the old
one in the same folder; tag the old one first. Never copy assets to migrate.

## Theme and classes

Every new deck gets a folder with `deck.md` and `assets/`. All decks use the
same theme: front matter says `theme: base`. There are no per-deck themes or
deck CSS files. Keep every deck folder one level below the repository root:
the theme loads its fonts from `../theme/fonts/`, relative to `deck.html`.

From the repository root, run `npm install` once, then:

```
npm run render -- <deck>/deck.md   # writes <deck>/deck.html
npm run check -- <deck>            # lists slides whose content does not fit
```

The class vocabulary in `base.css` is the complete list. Do not add
deck-specific classes.

- Slide layouts (`_class`): none (the default: title, then body), `cover`,
  `divider`, `full` (full-bleed image or video; use Marp `![bg](...)` for
  images).
- Slide modifiers: `center` (centres the body on the slide; the title stays at
  the top and any takeaway and footer at the bottom), `invert` (light
  palette; put `class: invert` in the front matter for a whole light deck).
- Components: `cols` (equal columns, one per child; a leading `<span>` in a
  cell is its label), `contrast`, `rows-2` and `flow` (modifiers on `cols`;
  `flow` draws an arrow between consecutive columns, for process steps).

Native Marp features replace classes where they can:

- Takeaway: a Markdown blockquote, `> One bold line.` It renders as a centred
  band (accent left border, light accent fill) at the same height on every
  slide, just above the reserved footer line. The band always wraps its full
  text; `npm run check` flags a takeaway that runs to a second line.
- Text emphasis is standard Markdown: `*word*` italic, `**word**` bold, and
  `***word***` highlighted (accent colour, bold, upright) anywhere: titles,
  body, tables.
- Movie link on a `full` slide: `[Play · 2:10](url)`, drawn as a corner label.
- Two images side by side with text: `![bg left:60% contain](a.jpg)` then
  `![bg contain](b.jpg)`; contained background images keep the slide margins.

- References: author-date, the standard short form (APA / Chicago author-date):
  `- De Silva et al. (2023). [Title](url)`. First author, `et al.` for more
  than one, year in parentheses and a full stop, then the linked title. A list item that ends
  with a link renders as a citation in small grey text.
- Tables: anything shaped like a table (rows × attributes, a capability
  matrix, a component list, an evolution timeline) is a Markdown pipe table,
  never HTML or `cols`. Tables render with no fill and no lines, left-aligned;
  use `:---:` only for columns that should be centred (e.g. ● ◐ ○) and `--:`
  for numbers. For yes / partly / no, type `●` `◐` `○`: the theme draws them
  as green, orange and red circles. For other values, write words; bold marks
  the value that matters and renders white.
- Source line: `<!-- _footer: Source: Lazer et al., 2014 -->` on the slide. It
  sits in a line reserved at the bottom of every content slide, below the
  takeaway.
- Image beside text: the title spans the whole slide; only the body is split.
  Use `cols` with a text cell and a `<figure><img …></figure>` cell. Do not
  use split backgrounds (`![bg left:40%]`) on a slide with a title, because
  they narrow the title too. Split backgrounds are only for slides with no
  `#` title.
- Image size: when images in `cols` cells need a common size, use Marp's
  `![h:170 alt](file)` with the same value for every image on the slide. Do
  not size images in CSS.

Without classes: `# h1` is the slide title. A figure is one or more
Markdown images on their own lines (`![alt text](file.svg)`, one per line,
with a blank line before and after); it fills the remaining height. Use an
HTML `<figure>` only when it needs a caption or heading, or as a cell of
`cols`. `***word***` carries the accent colour.
SVGs in `assets/equations/` are exported at body size and shrink to fit
their column. Write Markdown
inside `cols` cells, leaving a blank line after the opening `<div>` and before
the closing one.
In a `cols` cell, use `### Title` for a column title over ordinary text, and
`## Claim` when the paragraph right after it is a grey explanation of the
claim. Use a leading `<span>` only for a short category label (Data, KPI 1,
Prediction) that is smaller than the content it names.
Items in `cols` cells line up row by row across columns (up to ten items per
cell), so put parallel items in the same order in every cell. Use one paragraph
per item, not a list, when the items should align.

### No slide-specific styling

Never write slide-specific or content-specific CSS anywhere: not in
`base.css`, not in a deck-level CSS file, not in a `<style>` block, and not
as inline `style=` attributes. This includes:

- classes named after a slide, topic, figure, method, or position (for
  example `definetti-slide`, `scenario3-legend`, `foraging-takeaway`,
  `title-2line`)
- selectors that target one slide (`section:nth-of-type(...)`, `#id`, or an
  attribute selector on a single image path)
- one-off sizes, offsets, transforms, or absolute positions to make one slide
  fit

When a slide does not fit or does not look right, fix the content, not the
theme. Cut or split the text, use an existing component, crop or regenerate the
image, or draw legends, labels, and overlays into the figure asset itself. If no
existing class works, say so to the user and propose a generic addition. Do not
add it until the user agrees.

A change to `base.css` is acceptable only when the user approves it and the
pattern is generic enough to recur across decks. Give it a generic name, add it
to the class list above, and render every deck that uses the theme.

## Footers

Use footers sparingly. A footer (`<!-- _footer: … -->`) cites what is on the
slide (see Content rules). A takeaway is a `>` blockquote, not a footer.

## Mathematical notation

Every mathematical expression in a deck must be authored in LaTex and rendered
as a local vector asset. This includes displayed equations, inline symbols,
subscripts and superscripts, probability laws, operators, sets, and formal
function signatures. Do not substitute Unicode math, HTML subscripts, or a
text font for LaTex merely because the expression is short. Keep the `.tex`
source beside the generated SVG in the deck's `assets/equations/` directory.
Export every equation at body-text size so the SVG needs no CSS scaling:
compile the 10pt `standalone` source and convert with `dvisvgm --zoom=2.1`.
The theme shrinks wide equations to fit their column and scales equations in
captions and footers down to small size. Equation colour is baked into the
SVG: a deck with `class: invert` exports equations in dark ink.
Use ordinary prose for non-mathematical arrows or labels. 

## Design schematic: binary contrasts

Every slide that establishes a binary contrast uses `<div class="cols
contrast">` with exactly two child cells. This includes conceptual comparisons,
theorem comparisons, control comparisons, and paired result comparisons. Do not
make a one-off two-column layout for such a slide.

The left column is the neutral baseline. The right column is the proposed,
prospective, or otherwise focal case. `base.css` provides equal columns, a
single central divider, a light accent tint on the right, and accent emphasis
on marked words.

Write the paired column titles as the slide title, one span per column:
`# <span>Baseline</span> <span>***Focal*** case</span>`. They sit at normal
title position and size, aligned with the columns. Put rows in a
Markdown list; rows line up across the two columns. A plain paragraph after
the list is the cell's verdict line, pinned to the bottom. Cells may also be `<figure>` elements for paired
figures.

Keep the two statements syntactically parallel. State the common language in
both columns and mark only the minimal differing terms with `***word***`. Do not add modifier classes for contrasts.

## Spacing

Spacing comes from three stack levels in `base.css`: `--stack-slide` between
blocks on a slide, `--stack-cell` between items in a column or figure, and
`--stack-list` between list items. Do not add margins to individual
components. Use the stack level that matches.

## Typography

Use one type scale with three sizes, defined in `theme/base.css`. Slides
never set sizes:

- title: 45px (every `# h1`: slide, cover, divider)
- body: 28px (body text; bold for `##`/`###` headings, claims, verdicts,
  takeaways)
- small: 22px, always grey (labels, captions, tables, explanations, sources,
  cover byline)

Text uses one bold weight (`--bold`, 700), no uppercase or letter-spaced
labels, and two font families from New Computer Modern, the same family as
the PDF house style: New Computer Modern Sans Bold for headings (`#`, `##`, `###`),
New Computer Modern Book for everything a viewer reads as text (body, bold phrases, verdicts,
takeaways, labels, captions, tables, sources). These are the only treatments:

- title: white bold
- body: white regular, or white bold
- small: grey bold (labels, captions, table headers; accent colour on the
  right of a contrast) or grey regular (explanations, table cells, sources, byline)
- italic `*word*` and bold `**word**` in the colour of the surrounding text
- highlighted words `***word***`: accent colour (yellow on dark, blue on
  light), bold, any size

Never underline anything, including links and references. A link keeps the
colour of the surrounding text; the theme marks it with a small grey ↗ after
it (except the corner label on a `full` slide).

Do not add a size or another combination of colour, weight, or case. Nothing
is smaller than 22px.

Do not solve overflow
by shrinking text. Cut content, simplify the visual, split the slide, or move
detail to speaker notes. Tables must use at least 22px text. Render the deck
and inspect every slide after changing shared typography.

## Content rules

- Plan about one slide per minute of the slot, and plan to speak for 65 to 75
  percent of the allotted time. One point per slide.
- No more than two consecutive content slides without a figure or image.
- A plain list carries at most three items. Longer parallel content goes in
  `cols`.
- End a talk with an acknowledgements slide that shows the people involved,
  with photos.
- Titles and section dividers use sentence case: capitalize only the first
  word and proper names, acronyms, or branded terms.
- Numbers on slides have at most two significant digits; round before placing
  them. Never assert a magnitude beyond what is measured or sourced. When only
  one proof point exists, say so instead of generalizing from it.
- A takeaway (`>`) sits at the same height on every slide, just above the
  footer line, and is one line per slide. It adds an implication,
  consequence, or decision; it never restates the title or summarizes the
  body. If it has nothing to add, delete it. If it does not fit on one line,
  cut it to the claim.
- A footer only cites what is on the slide (an image's source, a figure's
  paper, a quote's origin). Never use it for a disclaimer, caveat, or scope
  note. It fits on one line: cut the least essential entry rather than wrap.
- On a multi-column slide whose evidence is a graphic, every panel uses the
  same order: short label, graphic, explanation, then any implication.
- Body copy is fragments, not sentences: phrases joined with a comma or a
  colon, no full stops. Titles are one-line claims. Exceptions: theorem
  statements, theorem-style comparisons, and references keep their full
  wording and punctuation.
- Labels and table headers use sentence case too: "Cumulative spend", "6
  months", never "Cumulative Spend" or "6 MONTHS".
- On a slide built from columns, every piece of content lives in exactly one
  of four places: the title, a column, the takeaway (`>`), or the footer.
  Nothing sits between the columns and the bottom of the slide. Text that
  relates two columns goes into a column's own items.
- Body copy is left-aligned. Centring is only for the `center` layout, display
  equations, standalone graphics, and the takeaway band.
- Colour encodes a stable meaning. The accent (`***word***`) marks the focal
  or differing terms; white carries the thesis and ordinary text; grey is for
  labels and context. Never use colour just to separate two phrases in one
  sentence.
- Do not draw a line just to group or decorate. Lines are allowed only when
  they encode information: an axis, a timeline, a threshold, or the
  contrast's centre divider. Tables have no lines.
- Citations on a slide are only for borrowed figures, images, and direct
  quotes, in the footer as author or organization plus year (`Source: Lazer
  et al., 2014`), one line. Every factual claim still has a verified source,
  in the speaker notes or the references slide, even when the slide shows no
  citation.
- Reference slides list one entry per line in author-date form: first author
  (`et al.` for more than one), year in parentheses and a full stop, then the linked title. No venue, volume, pages, or DOI in
  the visible entry; the link carries the full citation.
- Movies: a `full` slide with a thumbnail (`![bg](thumb.jpg)`, which may be
  the video site's own thumbnail URL) and one link as the corner label
  (`[Play · 2:10](url)`, or `[Title · Play](url)` when the slide has a
  title). Do not embed players. Cite the rights holder in the footer.

## Images

- No file in the repo is larger than 500 KB. Size images for a 1280×720
  slide (longest side at most 1920 px): JPEG for photos, PNG for flat
  graphics, WebP when a photo needs transparency. Compress videos (for
  example `ffmpeg -crf 34`, 15 fps, 960 px wide). Store data as compact JSON,
  never pickle.

- Cite copyrighted images in the slide footer (rights holder, year).
- People photos stay square; no cropping or circles.

## Process

- Speaker scripts (for example `companion.md`) change only when the user asks,
  even when slides are reordered or removed.
- Do not build PDFs (or PNG exports) of a deck unless the user asks. The
  deliverable is `deck.md` and its rendered `deck.html`.
- Never edit an `AGENTS.md`. Each one is a symlink to the `CLAUDE.md` beside
  it; edit that `CLAUDE.md` instead. A new deck folder that needs local rules
  gets `CLAUDE.md` plus `ln -s CLAUDE.md AGENTS.md`.
- Never commit or push a file larger than 500 KB, not even in a commit that
  later replaces it: git keeps every version. Run `npm run check-size` before
  every commit; it lists any tracked file over 500 KB. If a big file was
  committed but not pushed, rewrite those commits before pushing.
- For live rebuilds while editing, run
  `npx marp --watch --html --allow-local-files --theme-set theme/base.css
  <deck>/deck.md`.

## Figures

The figure rules in the `figures` skill apply, with one change for slides: any caption, legend,
or label is part of the figure file itself, not Markdown text beneath the
image. This replaces the master rule that captions go as italic text below the
image. Use fonts of at least 12pt on presentation figures.

## Verification

Keep the Markdown and `theme/base.css` as the source of truth. Run
`npm run check -- <deck>` after every change and fix every error it reports
before declaring the deck done. An error means content runs past the slide
edge, an image overflows its box or renders invisible, or a takeaway wraps
to a second line. `overflow: hidden` hides these from view,
so do not rely on looking at the slides alone. Inspect all changed slides at presentation scale. Check title visibility, type size, image crops, equation legibility, table fit, citations, and overflow before declaring the deck done.
