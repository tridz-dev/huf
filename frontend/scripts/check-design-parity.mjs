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
 *   5. CASING             — Title Case where the house style is sentence
 *      case. This one has a history: it took FOUR separate sweeps to land
 *      ("catch bare text", "catch DialogTitle", "catch bare indented JSX
 *      text nodes"...), each declared done, each blind to a surface the
 *      others didn't look at. This check covers bare JSX text, Title/menu
 *      component children, title/label/placeholder/aria-label props, and
 *      label:/title:/heading: object-literal copy (filter dropdowns, tab
 *      configs, breadcrumbs, row actions) in one pass so a fifth sweep is
 *      never needed again.
 *
 * Usage:  node scripts/check-design-parity.mjs [--strict]
 * Without --strict, only checks 1–3 fail the build; overrides and casing are
 * reported as warnings — overrides because the ~347 existing ones are being
 * paid down incrementally, casing because it is brand new and legacy copy
 * shouldn't break the build on day one.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const SRC = join(ROOT, 'src');
const STRICT = process.argv.includes('--strict');
const ALL = process.argv.includes('--all');

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
// Text alignment / wrapping / truncation are composition, not design-system
// decisions — `text-right` on a numeric table cell is correct and must not be
// reported. Only size, weight, transform, tracking and colour count.
const TEXT_LAYOUT = 'left|center|right|justify|start|end|wrap|nowrap|balance|pretty|ellipsis|clip|top|middle|bottom';
// Sanctioned scale steps. `text-xs`/`text-sm`/`text-base` map to 12/14/16px,
// all three of which the design doc uses heavily (16px alone appears 50 times),
// so they are part of the system rather than drift. Only ARBITRARY sizes —
// `text-[Npx]` — and the larger display sizes count as an override.
const TEXT_SANCTIONED = 'xs|sm|base';
const OVERRIDE = new RegExp(
  `\\b(?:p|px|py|pt|pb|pl|pr)-|\\brounded|\\bshadow|\\btext-(?:lg|xl|\\[)|` +
  `\\bfont-(?:bold|semibold|medium|normal)|\\buppercase\\b|\\btracking-|` +
  `\\b(?:h|w|size|min-w|min-h)-(?!full\\b|auto\\b)|` +
  `\\b(?:bg|border|ring|fill|stroke|divide|outline|accent|caret|decoration|placeholder)-|` +
  `\\btext-(?!${TEXT_LAYOUT}|${TEXT_SANCTIONED}\\b)[a-z]`,
);

// ----------------------------------------------------------------- case ---
// House style: sentence case for every heading, label, button and menu
// item; uppercase only in mono eyebrows, column heads, group labels, stat
// labels (those are visually all-caps via CSS, not authored as Title Case
// text, so they don't show up here). "Title Case" = two or more consecutive
// Capitalised Words. A single capitalised word is never enough to flag —
// that's just a normal sentence-case first word or a proper noun.
//
// Acronyms/initialisms and product/brand names are exempt. Extend this list
// rather than loosening the detector when a new one shows up.
const CASING_ALLOWLIST = new Set([
  // acronyms / initialisms
  'API', 'MCP', 'SSH', 'URL', 'JSON', 'LLM', 'AI', 'UI', 'HTTP', 'CSV',
  'PDF', 'ID', 'VK', 'SMS', 'DocType',
  // product / brand names (including multi-word ones, matched word-by-word)
  'OpenAI', 'GitHub', 'Slack', 'WhatsApp', 'Telegram', 'Frappe', 'Claude',
  'Google', 'Chat', 'Microsoft', 'Teams', 'Postgres', 'Gmail',
]);

// Strip leading/trailing punctuation/quotes so "Profile," and "(Settings)"
// compare cleanly against the Capitalised-Word shape.
const stripEdges = (w) => w.replace(/^[^A-Za-z]+|[^A-Za-z']+$/g, '');

// A "Capitalised Word" is First-cap, rest-lowercase — this structurally
// excludes ALL-CAPS acronyms (API, SSH) without needing the allowlist, and
// excludes internal-cap identifiers (DocType) since only single words ever
// reach that shape and single words are never flagged on their own.
const isCapitalisedWord = (w) => /^[A-Z][a-z']*$/.test(w);

// ...but an acronym is only innocent on its own. "AI Providers", "MCP Servers"
// and "SSH Connections" are Title Case and were sitting in the sidebar unseen,
// because the acronym scored nothing and the one following word could never
// reach a run of 2 by itself. An acronym therefore opens a run without being a
// violation: acronym-then-Capitalised trips, a lone acronym does not.
const isAcronym = (w) => /^[A-Z]{2,6}$/.test(w);

function isTitleCase(text) {
  const words = text.split(/\s+/).map(stripEdges).filter(Boolean);

  // Prose gate. The rule governs headings, labels, buttons and menu items —
  // all of which are SHORT. Body copy and help text are full sentences that
  // legitimately contain capitalised feature names ("...enabling the Python
  // Code Execution tool...", "...managed by admins in the Frappe desk."), and
  // flagging those is not just noise, it is wrong. Anything sentence-shaped —
  // more than 6 words, or carrying sentence punctuation — is body copy, not a
  // label, so it is out of scope for this check.
  if (words.length > 6) return false;
  if (/[.!?](\s|$)/.test(text.trim().slice(0, -1) + ' ')) return false;

  let run = 0;
  for (const w of words) {
    // Allowlisted brand/acronym words neither extend nor bridge a run —
    // "Google Chat" and "New GitHub Repo" must not trip the detector.
    // ...but an allowlisted ACRONYM must not reset, or it shields the word
    // after it: "MCP Servers" and "AI Providers" scored zero and sat in the
    // page titles unflagged. Brand words still reset ("Google Chat"); an
    // acronym falls through to the run-opening branch below.
    if (CASING_ALLOWLIST.has(w) && !isAcronym(w)) { run = 0; continue; }
    if (isCapitalisedWord(w)) {
      run += 1;
      if (run >= 2) return true;
    } else if (isAcronym(w)) {
      run = Math.max(run, 1);
    } else {
      run = 0;
    }
  }
  return false;
}

// Component families whose children are user-visible copy: dialog/sheet/card
// titles (surface 2) and menu items (surface 3). Matched same-line, which
// covers the common `<CardTitle>Recent Activity</CardTitle>` shape; the
// multi-line shape (text on its own indented line) is already caught by the
// bare-JSX-text-node check below, so it isn't duplicated here.
const TITLE_AND_MENU_TAGS = [
  'DialogTitle', 'AlertDialogTitle', 'SheetTitle', 'CardTitle',
  'DropdownMenuItem', 'CommandItem', 'ContextMenuItem', 'MenubarItem',
  // Form field labels are copy too. "Allow SSH Execution" and "Allowlisted
  // SSH Connections" sat in AdvancedTab unflagged because FormLabel/Label
  // were not in this list and the text is same-line.
  'FormLabel', 'Label', 'TabsTrigger', 'SelectItem',
];
const TITLE_TAG_RE = new RegExp(
  `<(${TITLE_AND_MENU_TAGS.join('|')})(?:\\s[^>]*)?>([^<{]+)</\\1>`, 'g',
);

// Common string props that carry user-visible copy (surface 4).
const CASING_PROP_RE = /\b(?:title|label|placeholder|aria-label)="([^"]+)"/g;

// Surface 6: `label:`/`title:`/`heading:` string literals inside object
// literals — filter dropdown options, tab configs, breadcrumb trails, and
// row actions are almost universally declared this way (`{ label: 'Channel
// Credentials' }`, `{ title: 'Microsoft Teams', icon }`), never touching
// JSX at all, so surfaces 1–4 above never see them. A grep for this shape
// alone finds ~86 hits across the codebase.
//
// Exact-string allowlist: legitimate Title Case because it names a real
// product/brand, not authored copy. Extend this (not the detector) when a
// new proper noun shows up — do not loosen isTitleCase to fit it.
const OBJECT_LITERAL_CASING_ALLOWLIST = new Set([
  'Google Sheets', 'Google Calendar', 'Google Drive', 'Google Maps',
  'Google Meet', 'Microsoft Teams', 'Frappe Cloud', 'Frappe File',
  'OpenRouter', 'Google AI Studio', 'Model Context Protocol',
  // Already correct sentence case: every capital in it is a proper noun
  // (Gemini, Google AI Studio). The detector cannot tell that from Title
  // Case, so it is listed rather than "corrected" into 'Try gemini with...'.
  'Try Gemini with Google AI Studio',
]);

// Files whose label/title/heading-shaped strings are not UI copy at all, so
// the whole file is out of scope for this surface (test fixtures aren't
// copy; tableIcons.ts mirrors lucide icon identifiers, not labels).
const OBJECT_LITERAL_CASING_FILE_EXEMPT = [
  /\.test\.tsx?$/,
  /(^|\/)src\/data\/tableIcons\.ts$/,
];

const OBJECT_LITERAL_CASING_RE = /\b(?:label|title|heading):\s*(['"])((?:(?!\1).)+)\1/g;
// `{ label: 'Common Destination', value: 'Common Destination' }` mirrors a
// backend enum verbatim — label and value must not diverge, so an exact
// label===value match on the same line is exempt structurally rather than
// via the allowlist above (covers e.g. SkillsPage.tsx's 'Common
// Destination'/'App Provided' and knowledge.ts's 'Frappe File').
const OBJECT_LITERAL_VALUE_RE = /\bvalue:\s*(['"])((?:(?!\1).)+)\1/g;

// A bare JSX text node: an indented line that is just prose — starts with a
// capital letter and contains none of the characters that show up in code
// (tags, braces, assignment, statement punctuation, string quotes). This is
// deliberately narrow: it's meant to catch `  Manage your account` sitting
// between tags, not object keys, enum members, or type annotations.
const BARE_TEXT_RE = /^\s{2,}[A-Z][A-Za-z0-9'’,.:!?&/() -]*$/;
// `Key: 'Some Value',` is an object property, not a JSX text node — the
// straight quotes around the value are invisible to BARE_TEXT_RE (it treats
// `'` as prose apostrophe), so rule it out explicitly.
const OBJECT_PROPERTY_RE = /:\s*['"][^'"]*['"]\s*,?\s*$/;

const findings = { undefinedToken: [], rawPalette: [], deadDark: [], override: [], titleCase: [] };

for (const file of walk(SRC)) {
  const rel = relative(ROOT, file);
  // These legitimately carry their own palettes.
  const exempt = /shiki|highlight|chart|recharts|cytoscape|reactflow|nodeStyles|monaco|codemirror|mermaid|code-block/i.test(rel);
  // Test/spec/story files contain fixture copy, not real UI copy.
  const casingExempt = /\.(test|spec|stories)\.[jt]sx?$/.test(rel);
  // Object-literal labels: test fixtures and the icon-identifier table.
  const objectLiteralExempt = OBJECT_LITERAL_CASING_FILE_EXEMPT.some((re) => re.test(rel));

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

    // 5. Title Case copy, across all three authored surfaces at once.
    const trimmed = line.trim();
    const isComment = trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*');
    if (!casingExempt && !isComment) {
      // 5a. Dialog/Sheet/Card titles and menu items.
      for (const m of line.matchAll(TITLE_TAG_RE)) {
        // A <SelectItem value="X">X</SelectItem> is rendering a backend enum
        // verbatim (79 of them here: "FIFO", "Read", "Common Destination").
        // Sentence-casing the text would desync it from the doctype option it
        // names, so the same label===value rule used for object literals
        // applies. Only the display-text-differs-from-value case is copy.
        const mirrorsValue = new RegExp(
          `value=(['"])${m[2].trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\1`,
        ).test(line);
        if (mirrorsValue) continue;
        if (isTitleCase(m[2])) findings.titleCase.push(`${at}  <${m[1]}>${m[2].trim()}</${m[1]}>`);
      }
      // 5b. title=/label=/placeholder=/aria-label= props.
      for (const m of line.matchAll(CASING_PROP_RE)) {
        if (isTitleCase(m[1])) findings.titleCase.push(`${at}  ${m[0]}`);
      }
      // 5c. Bare JSX text nodes.
      if (BARE_TEXT_RE.test(line) && !OBJECT_PROPERTY_RE.test(trimmed) && isTitleCase(trimmed)) {
        findings.titleCase.push(`${at}  ${trimmed}`);
      }
      // 5d. label:/title:/heading: string literals in object literals —
      // filter dropdowns, tab configs, breadcrumbs, row actions (surface 6).
      if (!objectLiteralExempt) {
        for (const m of line.matchAll(OBJECT_LITERAL_CASING_RE)) {
          const value = m[2];
          if (OBJECT_LITERAL_CASING_ALLOWLIST.has(value)) continue;
          const siblingValues = [...line.matchAll(OBJECT_LITERAL_VALUE_RE)].map((v) => v[2]);
          if (siblingValues.includes(value)) continue; // mirrors a backend enum verbatim
          if (isTitleCase(value)) findings.titleCase.push(`${at}  ${m[0]}`);
        }
      }
    }
  });
}

// ---------------------------------------------------------------- report ---
const report = (title, items, fatal) => {
  if (!items.length) return 0;
  console.log(`\n${fatal ? 'FAIL' : 'warn'}  ${title}: ${items.length}`);
  for (const l of (ALL ? items : items.slice(0, 30))) console.log(`      ${l}`);
  if (!ALL && items.length > 30) console.log(`      … and ${items.length - 30} more  (--all to list every one)`);
  return fatal ? items.length : 0;
};

let fatal = 0;
fatal += report('undefined colour tokens (render as nothing — build will NOT catch these)', findings.undefinedToken, true);
fatal += report('raw Tailwind palette instead of design tokens', findings.rawPalette, true);
fatal += report('dead dark: classes (darkMode is false)', findings.deadDark, true);
fatal += report('design-system overrides on shared components', findings.override, STRICT);
fatal += report('Title Case copy (house style is sentence case)', findings.titleCase, STRICT);

const warnCount = findings.override.length + findings.titleCase.length;
if (!fatal && !warnCount) console.log('Design parity: clean.');
else if (!fatal) console.log(`\nDesign parity: no blocking issues (${findings.override.length} overrides, ${findings.titleCase.length} casing tracked; run with --strict to enforce).`);

process.exit(fatal ? 1 : 0);
