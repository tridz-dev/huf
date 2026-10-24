import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GEOMETRY_ROUTES, mockFormGeometryApis } from './helpers/formGeometryMocks';
import { findViolations, measurePage } from './helpers/formGeometryMeasure';

/**
 * Form geometry guard (UI form standard, Phase A / WP10). Offline: /api/** is mocked
 * (helpers/formGeometryMocks.ts, ported from the UI audit driver). For each of the 33
 * audited screens at 1440x900 and 1024x768, every row holding 2+ non-button controls must:
 *   - align control tops and bottoms within 1px (a FieldAction / data-field-reserve cell is
 *     exempt from the bottom comparison: it is a button sharing the row, not a field), and
 *   - use control heights from the token scale {30, 34, 38} (textareas and switches excepted).
 *
 * Known remaining rows live in form-geometry.allowlist.json (owner + note per entry). The
 * allowlist can only shrink: MAX_ALLOWLIST below is a ceiling that is lowered as entries are
 * removed, and an entry that no longer matches a failing row fails the test ("remove it").
 *
 * Local run with a system browser (CI uses Playwright's chromium):
 *   PW_CHANNEL=chrome npx playwright test e2e/form-geometry.spec.ts
 */

/** Ratchet: lower this when allowlist entries are removed; never raise it. */
const MAX_ALLOWLIST = 0;

interface AllowEntry {
  route: string;
  viewports: number[];
  signature: string;
  rules: string[];
  owner: string;
  note: string;
}

const here = path.dirname(fileURLToPath(import.meta.url));
const allowlist: AllowEntry[] = JSON.parse(fs.readFileSync(path.join(here, 'form-geometry.allowlist.json'), 'utf8')).entries;

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
];

test.describe('form geometry allowlist', () => {
  test('only shrinks', () => {
    expect(allowlist.length, 'allowlist grew; fix the row instead of adding an entry').toBeLessThanOrEqual(MAX_ALLOWLIST);
    for (const e of allowlist) expect(e.owner && e.note, `entry ${e.route} needs owner and note`).toBeTruthy();
  });
});

for (const vp of VIEWPORTS) {
  test.describe(`form geometry @${vp.width}`, () => {
    test.use({ viewport: vp });

    for (const route of GEOMETRY_ROUTES) {
      test(route.id, async ({ page }) => {
        test.setTimeout(60_000);
        await mockFormGeometryApis(page);
        await page.goto(route.path);
        await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
        await page.waitForTimeout(900);
        if (route.act) await route.act(page);
        await page.waitForTimeout(500);

        const rows = await measurePage(page);
        const violations = findViolations(rows);

        if (process.env.FORM_GEOMETRY_DUMP) {
          // Debug/reporting aid: one JSON file per route+viewport in the given directory.
          fs.mkdirSync(process.env.FORM_GEOMETRY_DUMP, { recursive: true });
          fs.writeFileSync(
            path.join(process.env.FORM_GEOMETRY_DUMP, `${route.id}.${vp.width}.json`),
            JSON.stringify({ route: route.id, viewport: vp.width, rows: rows.length, violations }, null, 1),
          );
        }

        const mine = allowlist.filter((e) => e.route === route.id && e.viewports.includes(vp.width));
        const unmatched: string[] = [];
        const allowed = new Set<string>();
        const stale = mine.filter((e) => {
          const hit = violations.filter((v) => v.signature === e.signature && e.rules.includes(v.rule));
          hit.forEach((v) => allowed.add(`${v.signature}#${v.rule}`));
          return hit.length === 0;
        });
        for (const v of violations) {
          if (!allowed.has(`${v.signature}#${v.rule}`)) unmatched.push(`${v.rule}: [${v.signature}] ${v.detail}`);
        }
        expect(stale.map((e) => `${e.route}@${vp.width} [${e.signature}]`), 'stale allowlist entries: remove them').toEqual([]);
        expect(unmatched, `${route.id}@${vp.width}: ${rows.length} rows measured`).toEqual([]);
      });
    }
  });
}
