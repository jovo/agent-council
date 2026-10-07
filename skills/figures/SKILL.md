---
name: figures
description: Rules for making, styling, captioning, and sourcing figures and plots (matplotlib, seaborn, any plotting code, or figures borrowed from papers). Use whenever the task creates, edits, reviews, or captions a figure, chart, plot, or schematic.
---

# Figures

## Before styling

- Settle the figure's one main point and its audience first. A reader shown the figure without its caption should be able to name that point.
- Group a multi-method, multi-setting comparison by the comparison the reader has to make.

## Style

- Apply Tufte by default: no gridlines, minimal data-ink, range-bounded axes, informative titles.
- Encode the model/family by color and a condition (e.g. with/without an ablation) by line style. The proposed/new method is the red line.
- Diverging colormaps: sns.diverging_palette(145,300,s=60,as_cmap=True), centered at 0.
- Two-class scatter: black + gray (plus o/x markers), not hue.
- Label lines directly when there is room. Otherwise put the legend in a horizontal row below the panels, never inside.
- Number every figure ("Figure N." in the caption, sequential) and refer to figures by number in prose.
- Don't restate panel/axis labels in the title.
- Fonts must be >=9 pt when the figure sits in a ~6.5 in text column on letter paper: author figures <=7.2 in wide with >=10 pt fonts.
- Markdown captions go as italic text on their own line beneath the image (alt text doesn't render).
- Show run-to-run variance as a shaded 25-75 percentile (IQR) band around the bold median, NOT as per-seed/per-run traces, whenever there are more than 3 repetitions (seeds). With <=3 reps, thin per-run traces are fine. Use a low band alpha (~0.15-0.2) so overlapping series stay legible.
- To compare two methods, also plot the paired per-seed differences (same seed, same split), not only the two medians.
- Any decision-forest / random-forest series is ALWAYS the red line (my signature). This takes precedence over the proposed-method-is-red default: if a forest and another would-be-red series (e.g. an MLP) share a plot, keep red for the forest and recolor the other series.
- Always add a method's curve to its figure at whatever number of seeds/repetitions has run so far. Never wait for a target seed count before showing a curve. Plot it now (with the IQR band if >3 reps), note the count in the caption, and re-render as more complete.
- Axis tick labels: only at the min, the max, and 0 if 0 falls within the axis range. No other tick labels. Font size 12pt, calibrated to a 6.5in-wide figure (scale proportionally for other widths).
- Keep each method's color fixed across every figure in a document, and use that color for nothing else.
- Use gray as the default series color and reserve black and red for emphasis. Use a sequential palette for series that vary one parameter, such as training-set size.
- Axis labels are words with units, not symbols or abbreviations. A log axis says "log" in its label.
- Name methods. Never label one "proposed" or "ours" in a figure.
- Export vector graphics (SVG for documents). Use line widths above the plotting library's defaults, and clearly distinct markers.
- Bar charts start at zero on a linear axis. No pie charts. No 3D for 2D data.
- Never distort the aspect ratio by rescaling width and height independently.
- In a multipanel figure, drop axes and labels that repeat across panels.

## Captions

- Number figures with a `**Figure N.**` prefix (or `**Figure N.M.**` for multi-panel numbering within a chapter). Reference by number in prose.
- Captions are Markdown italic on the line beneath the image. Alt-text does not render on GitHub.
- Do not restate axis labels or panel letters already visible on the figure.
- Open each caption with its take-home message. For a multipanel figure, one sentence gives the collective message, then each panel gets a clause.
- State the sample size, the statistical test when one applies, and what each band or error bar shows.
- Define every acronym that appears in the figure.

## Sources and licensing

- Openly-licensed figures are preferred. Acceptable, in order:
  - bioRxiv preprints (author-deposited CC-BY / CC-BY-NC-ND). Always check bioRxiv first for any neuroscience paper.
  - Wikimedia Commons (public domain, CC-BY, CC-BY-SA) — credit the author.
  - eLife, PLoS, Frontiers, BMC, MDPI, NCBI Bookshelf open content, or any CC-BY journal.
  - US-government publications (NIH, NSF, NIDA, NIAAA) — public domain.
  - OpenStax open textbooks.
- **Figures from non-CC-BY publications may be embedded under fair use with full attribution in the caption and bibliography.** Standard practice for personal scholarly / educational works; the author has authorized this. Always include the source citation; never strip attribution.
- Download figures to `figures/fig<N>.<M>.<ext>` (or `figures/NN-shortname/figK.ext` for multi-figure chapters tied to one paper). Do not hot-link.
- For Wikimedia thumbnails: `https://upload.wikimedia.org/wikipedia/commons/thumb/<x>/<xx>/<file>.svg/960px-<file>.svg.png`.
- Verify every URL resolves before committing.
- Prefer openly licensed images or our own. Cite every copyrighted image (rights holder, year). Never fabricate an image (no generated stock-style or stand-in images).
