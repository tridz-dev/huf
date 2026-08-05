#!/usr/bin/env node
/**
 * Design-system parity guard.
 *
 * Exists because a tab bar was "fixed" twice with no visible effect: the
 * component was correct each time, but the page passed
 * `className="px-3 sm:min-w-[110px]"` to the trigger, and `cn()` (tailwind-merge)
 * applies the callsite LAST. The design system is only advisory unless
 * something enforces it — this is that something.
 *
 * Checks, in order of how badly they bite:
 *   1. UNDEFINED TOKENS  — a colour class naming a token that does not exist.
 *      Tailwind emits no CSS for these and tsc cannot see them, so they pass
 *      typecheck AND build, then render nothing at runtime.
 *   2. RAW PALETTE       — zinc/gray/red/... instead of the design tokens.
 *   3. DEAD dark:        — darkMode is false, so these can never apply.
 *   4. OVERRIDES         — padding/radius/colour/font/shadow/size passed via
 *      className to a shared UI component (the tab-bar bug's exact shape).
 *
 * Usage:  node scripts/check-design-parity.mjs [--strict]
 * Without --strict, only checks 1–3 fail the build; overrides are reported
 * as warnings, since the ~347 existing ones are being paid down incrementally.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const SRC = join(ROOT, 'src');
const STRICT = process.argv.includes('--strict');

// ---------------------------------------------------------------- tokens ---
// Parsed from tailwind.config.js so this never drifts from the real config.
function definedColorTokens() {
  const cfg = readFileSync(join(ROOT, 'tailwind.config.js'), 'utf8');
  const colors = cfg.slice(cfg.indexOf('colors:'), cfg.indexOf('spacing:'));
  const names = new Set();
  for (const m of colors.matchAll(/^\s*'?([a-z][a-z0-9-]*)'?\s*:/gim)) names.add(m[1]);
  // shadcn sub-keys (card.foreground etc.) render as card-foreground
  for (const m of colors.matchAll(/'?([a-z-]+)'?\s*:\s*\{([^}]*)\}/gis)) {
    for (const s of m[2].matchAll(/'?([a-z][a-z0-9-]*)'?\s*:/gi)) {
      names.add(s[1] === 'DEFAULT' ? m[1] : `${m[1]}-${s[1]}`);
    }
  }
  return names;
}

const TOKENS = definedColorTokens();
const COLOR_PREFIX = '(?:bg|text|border|ring|fill|stroke|from|via|to|divide|outline|shadow|accent|caret|decoration|placeholder)';

// ------------------------------------------------------------------ scan ---
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (['.tsx', '.ts'].includes(extname(p))) out.push(p);
  }
  return out;
}

const SHARED = [
  'Button', 'Badge', 'Card', 'CardHeader', 'CardContent', 'CardTitle',
  'CardDescription', 'CardFooter', 'Alert', 'Input', 'Textarea',
  'SelectTrigger', 'Checkbox', 'Switch', 'RadioGroupItem', 'Label',
  'TabsList', 'TabsTrigger', 'TableHead', 'TableCell', 'Avatar',
];
const OVERRIDE = new RegExp(
  `\\b(?:p|px|py|pt|pb|pl|pr)-|\\brounded|\\bshadow|\\btext-(?:xs|sm|base|lg|xl|\\[)|` +
  `\\bfont-(?:bold|semibold|medium|normal)|\\buppercase\\b|\\btracking-|` +
  `\\b(?:h|w|size|min-w|min-h)-(?!full\\b|auto\\b)|${COLOR_PREFIX}-`,
);

const findings = { undefinedToken: [], rawPalette: [], deadDark: [], override: [] };

for (const file of walk(SRC)) {
  const rel = relative(ROOT, file);
  // These legitimately carry their own palettes.
  const exempt = /shiki|highlight|chart|recharts|cytoscape|reactflow|nodeStyles|monaco|codemirror|mermaid|code-block/i.test(rel);

  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    const at = `${rel}:${i + 1}`;

    // 1. colour class naming a token that does not exist
    for (const m of line.matchAll(new RegExp(`\\b${COLOR_PREFIX}-([a-z][a-z0-9-]*)\\b`, 'g'))) {
      const name = m[1];
      if (TOKENS.has(name)) continue;
      // strip a trailing segment to catch invented suffixes (good-ink, signal-tint)
      const base = name.replace(/-(?:ink|tint|soft|deep|dark)$/, '');
      if (base !== name && TOKENS.has(base)) findings.undefinedToken.push(`${at}  ${m[0]}  (no such token; '${base}' exists)`);
    }

    if (!exempt) {
      // 2. raw Tailwind palette
      const raw = line.match(new RegExp(`\\b${COLOR_PREFIX}-(?:zinc|slate|gray|grey|neutral|stone|red|green|blue|amber|yellow|emerald|rose|orange|indigo|violet|purple|teal|cyan|pink|lime|sky|fuchsia)-\\d{2,3}\\b`, 'g'));
      if (raw) findings.rawPalette.push(`${at}  ${[...new Set(raw)].join(' ')}`);

      // 4. override passed to a shared component
      const tag = line.match(/<([A-Z][A-Za-z]*)[\s>]/);
      if (tag && SHARED.includes(tag[1])) {
        const cls = line.match(/className=(?:"([^"]*)"|\{`([^`]*)`\})/);
        const v = cls?.[1] ?? cls?.[2];
        if (v && OVERRIDE.test(v)) findings.override.push(`${at}  <${tag[1]}>  "${v.slice(0, 90)}"`);
      }
    }

    // 3. dead dark: utilities (darkMode is false)
    if (/\bdark:[a-z[]/.test(line) && !rel.endsWith('.css')) findings.deadDark.push(`${at}  ${line.trim().slice(0, 90)}`);
  });
}

// ---------------------------------------------------------------- report ---
const report = (title, items, fatal) => {
  if (!items.length) return 0;
  console.log(`\n${fatal ? 'FAIL' : 'warn'}  ${title}: ${items.length}`);
  for (const l of items.slice(0, 30)) console.log(`      ${l}`);
  if (items.length > 30) console.log(`      … and ${items.length - 30} more`);
  return fatal ? items.length : 0;
};

let fatal = 0;
fatal += report('undefined colour tokens (render as nothing — build will NOT catch these)', findings.undefinedToken, true);
fatal += report('raw Tailwind palette instead of design tokens', findings.rawPalette, true);
fatal += report('dead dark: classes (darkMode is false)', findings.deadDark, true);
fatal += report('design-system overrides on shared components', findings.override, STRICT);

if (!fatal && !findings.override.length) console.log('Design parity: clean.');
else if (!fatal) console.log(`\nDesign parity: no blocking issues (${findings.override.length} overrides tracked; run with --strict to enforce).`);

process.exit(fatal ? 1 : 0);
