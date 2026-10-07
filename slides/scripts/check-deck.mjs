#!/usr/bin/env node
// Render a Marp deck and report every slide where content does not fit.
//
//   node scripts/check-deck.mjs <deck-folder-or-deck.md>
//
// Errors (exit 1):   an element extends past the slide edge, or an image is
//                    wider/taller than the box that holds it.
// Warnings:          an element extends into the slide's padding.
// Needs Chrome/Chromium: set CHROME_PATH, or it tries the usual macOS/Linux paths.

import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer-core';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const arg = process.argv[2];
if (!arg) { console.error('usage: node scripts/check-deck.mjs <deck-folder-or-deck.md>'); process.exit(2); }
const md = statSync(arg).isDirectory() ? join(resolve(arg), 'deck.md') : resolve(arg);
const deckDir = dirname(md);

const chrome = process.env.CHROME_PATH || [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].find(existsSync);
if (!chrome) { console.error('No Chrome found. Set CHROME_PATH.'); process.exit(2); }

// Bare template: every slide visible, stacked. Written beside deck.md so the
// relative asset and font paths resolve exactly as in deck.html.
const out = join(deckDir, `.check-${process.pid}.html`);
const marp = join(repo, 'node_modules', '.bin', 'marp');
execFileSync(existsSync(marp) ? marp : 'npx', [
  ...(existsSync(marp) ? [] : ['@marp-team/marp-cli']),
  '--template', 'bare', '--html', '--allow-local-files',
  '--theme-set', join(repo, 'theme', 'base.css'),
  '-o', out, md,
], { stdio: ['ignore', 'ignore', 'inherit'] });

const browser = await puppeteer.launch({ executablePath: chrome, args: ['--allow-file-access-from-files', ...(process.getuid?.() === 0 ? ['--no-sandbox'] : [])] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });
  await page.goto(pathToFileURL(out).href, { waitUntil: 'networkidle0' });
  await page.evaluate(() => document.fonts.ready);

  const report = await page.evaluate(() => {
    const T = 1.5; // px tolerance
    const sections = [...document.querySelectorAll('section')]
      .filter(s => !['background', 'pseudo'].includes(s.dataset.marpitAdvancedBackground));
    const label = el => {
      const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '';
      const txt = (el.getAttribute('alt') || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
      return `<${el.tagName.toLowerCase()}${cls}> ${txt ? `"${txt}"` : ''}`.trim();
    };
    const slides = [];
    sections.forEach(sec => {
      const n = Number(sec.dataset.marpitPagination || sec.id || slides.length + 1);
      if (sec.classList.contains('full')) return;
      const S = sec.getBoundingClientRect();
      const cs = getComputedStyle(sec);
      const scale = S.width / sec.offsetWidth || 1;
      const pad = { t: parseFloat(cs.paddingTop) * scale, r: parseFloat(cs.paddingRight) * scale,
                    b: parseFloat(cs.paddingBottom) * scale, l: parseFloat(cs.paddingLeft) * scale };
      const errors = [], warnings = [];
      for (const el of sec.querySelectorAll('*')) {
        const R = el.getBoundingClientRect();
        if (el.tagName === 'IMG' && (R.width < 2 || R.height < 2) && getComputedStyle(el).display !== 'none') {
          errors.push(`${label(el)} is not visible (rendered ${Math.round(R.width)}×${Math.round(R.height)}px)`); continue;
        }
        if (!R.width || !R.height) continue;
        const over = Math.max(R.right - S.right, R.bottom - S.bottom, S.left - R.left, S.top - R.top);
        if (over > T) { errors.push(`${label(el)} runs ${Math.round(over / scale)}px past the slide edge`); continue; }
        const inPad = Math.max(R.right - (S.right - pad.r), R.bottom - (S.bottom - pad.b),
                               (S.left + pad.l) - R.left, (S.top + pad.t) - R.top);
        const st = getComputedStyle(el);
        if (inPad > T && st.position !== 'absolute' && st.display !== 'inline') warnings.push(`${label(el)} enters the padding by ${Math.round(inPad / scale)}px`);
        if (el.tagName === 'IMG' && el.parentElement) {
          const P = el.parentElement.getBoundingClientRect();
          const o = Math.max(R.right - P.right, R.bottom - P.bottom);
          if (o > T) errors.push(`${label(el)} overflows its container by ${Math.round(o / scale)}px`);
        }
      }
      for (const q of sec.querySelectorAll(':scope > blockquote')) {
        const lh = parseFloat(getComputedStyle(q).lineHeight) || 34;
        const pad = parseFloat(getComputedStyle(q).paddingTop) + parseFloat(getComputedStyle(q).paddingBottom);
        const tallest = Math.max(0, ...[...q.querySelectorAll('img')].map(i => i.getBoundingClientRect().height / scale));
        if (q.getBoundingClientRect().height / scale - pad > Math.max(lh * 1.5, tallest + lh * 0.5)) errors.push(`${label(q)} takeaway wraps to more than one line`);
      }
      if (errors.length || warnings.length) slides.push({ n, errors: [...new Set(errors)], warnings: [...new Set(warnings)] });
    });
    return { count: sections.length, slides };
  });

  let bad = 0;
  for (const s of report.slides) {
    if (s.errors.length) bad++;
    for (const e of s.errors.slice(0, 5)) console.log(`slide ${s.n}: ERROR   ${e}`);
    for (const w of s.warnings.slice(0, 3)) console.log(`slide ${s.n}: warning ${w}`);
  }
  console.log(`${report.count} slides checked, ${bad} with errors, ${report.slides.length - bad} with warnings only.`);
  process.exitCode = bad ? 1 : 0;
} finally {
  await browser.close();
  try { (await import('node:fs')).rmSync(out); } catch {}
}
