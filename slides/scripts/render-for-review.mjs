#!/usr/bin/env node
// Render a Marp deck to HTML and CSS for the review page, with the deck theme.
//
//   node scripts/render-for-review.mjs <deck.md> <theme.css>
//
// Prints JSON: {html, css}. The HTML is one inline SVG per slide, so each
// slide scales to the width of its container. Relative URLs (images, the
// theme's fonts) are left as written: the page resolves them from the deck's
// folder.

import { readFileSync } from 'node:fs';
import { Marp } from '@marp-team/marp-core';

const [md, theme] = process.argv.slice(2);
if (!md || !theme) { console.error('usage: node scripts/render-for-review.mjs <deck.md> <theme.css>'); process.exit(2); }
const marp = new Marp({ html: true, inlineSVG: true, script: false });
marp.themeSet.default = marp.themeSet.add(readFileSync(theme, 'utf8'));
const { html, css } = marp.render(readFileSync(md, 'utf8'));
process.stdout.write(JSON.stringify({ html, css }));
