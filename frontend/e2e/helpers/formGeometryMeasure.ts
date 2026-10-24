/**
 * In-page measurement for e2e/form-geometry.spec.ts.
 *
 * Row detection is the UI audit's (RepoStructure/ongoing6/measure/audit.mjs MEASURE): a DOM
 * parent whose visible children ("cells") each hold form controls and sit side by side. The
 * functions here run inside the page via page.evaluate, so they must stay self-contained.
 */
import type { Page } from '@playwright/test';

export interface RowItem {
  kind: 'input' | 'select' | 'textarea' | 'toggle' | 'button';
  text: string;
  top: number;
  bottom: number;
  height: number;
  /** Cell is a FieldAction (reserved label slot) or carries data-field-reserve. */
  exempt: boolean;
  /** Cell contains a ui/field label or note slot. */
  inField: boolean;
}

export interface MeasuredRow {
  /** Stable signature used by the allowlist: kind:text of each item, left to right. */
  signature: string;
  container: string;
  items: RowItem[];
}

export interface Violation {
  signature: string;
  rule: 'top-offset' | 'bottom-offset' | 'height';
  detail: string;
}

export const STANDARD_HEIGHTS = [30, 34, 38];

/** Collect every qualifying row (2+ non-button controls) on the current page. */
export const collectRows = (): MeasuredRow[] => {
  const vis = (e: Element) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const CTRL =
    'input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea,[role=combobox],button,[role=switch]';
  const all = [...document.querySelectorAll(CTRL)].filter(vis).filter((e) => !e.closest('[aria-hidden=true]'));
  const kind = (e: Element): RowItem['kind'] =>
    e.matches('textarea') ? 'textarea'
      : e.matches('[role=switch]') ? 'toggle'
      : e.matches('[role=combobox],select') ? 'select'
      : e.matches('input') ? 'input'
      : 'button';
  // Stable text for the allowlist signature: never a React useId (":r2p:"), which changes
  // with render order.
  const desc = (e: Element) => {
    const stableId = e.id && !/^[:\u00ab]/.test(e.id) ? e.id : '';
    const forLabel = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`)?.textContent : '';
    return (e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.textContent || (e as HTMLInputElement).name || forLabel || stableId || '')
      .trim().replace(/\s+/g, ' ').slice(0, 40);
  };
  const path = (e: Element) => {
    const p: string[] = [];
    let n: Element | null = e;
    for (let i = 0; i < 3 && n && n !== document.body; i++, n = n.parentElement) {
      p.unshift(n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\s+/).slice(0, 3).join('.') : ''));
    }
    return p.join(' > ');
  };
  const rows: MeasuredRow[] = [];
  const seen = new Set<string>();
  for (const P of document.querySelectorAll('body *')) {
    if (!vis(P)) continue;
    const kids = [...P.children].filter(vis);
    if (kids.length < 2) continue;
    const slots: { k: Element; c: Element; kr: DOMRect }[] = [];
    for (const k of kids) {
      const ctrls = (k.matches(CTRL) ? [k] : [...k.querySelectorAll(CTRL)]).filter((c) => all.includes(c));
      if (!ctrls.length) continue;
      slots.push({ k, c: ctrls.find((c) => kind(c) !== 'button') || ctrls[0], kr: k.getBoundingClientRect() });
    }
    if (slots.length < 2) continue;
    const ys = slots.map((s) => s.kr);
    if (!ys.every((r) => r.top < ys[0].bottom - 2 && r.bottom > ys[0].top + 2)) continue;
    if (slots.some((s) => s.kr.height > 220)) continue;
    const key = slots.map((s) => all.indexOf(s.c)).join(',');
    if (seen.has(key)) continue;
    seen.add(key);
    const items: RowItem[] = slots.map((s) => {
      const r = s.c.getBoundingClientRect();
      const reservedLabel = !!s.k.querySelector(':scope > [data-field-label][aria-hidden=true], [data-field-label][aria-hidden=true]');
      return {
        kind: kind(s.c),
        text: desc(s.c),
        top: Math.round(r.top + scrollY),
        bottom: Math.round(r.bottom + scrollY),
        height: Math.round(r.height),
        exempt: reservedLabel || !!s.k.closest('[data-field-reserve]') || !!s.k.querySelector('[data-field-reserve]'),
        inField: !!s.k.querySelector('[data-field-label],[data-field-note]'),
      };
    });
    // Qualifies when 2+ non-button controls (a switch only counts inside a Field).
    const nonButton = items.filter((i) => i.kind !== 'button' && (i.kind !== 'toggle' || i.inField));
    if (nonButton.length < 2) continue;
    rows.push({ signature: items.map((i) => `${i.kind}:${i.text}`).join(' | '), container: path(P), items });
  }
  return rows;
};

/** Apply the geometry contract to measured rows. */
export function findViolations(rows: MeasuredRow[]): Violation[] {
  const out: Violation[] = [];
  for (const row of rows) {
    // Alignment set: every control except plain buttons whose cell is exempt for bottom, and
    // toggles (shorter than a control by design) which only join the top comparison.
    const aligned = row.items;
    const tops = aligned.map((i) => i.top);
    const dTop = Math.max(...tops) - Math.min(...tops);
    if (dTop > 1) {
      out.push({ signature: row.signature, rule: 'top-offset', detail: `tops=${tops.join('/')} delta=${dTop}` });
    }
    const bottoms = aligned.filter((i) => i.kind !== 'toggle' && !i.exempt).map((i) => i.bottom);
    if (bottoms.length > 1) {
      const dBot = Math.max(...bottoms) - Math.min(...bottoms);
      if (dBot > 1) out.push({ signature: row.signature, rule: 'bottom-offset', detail: `bottoms=${bottoms.join('/')} delta=${dBot}` });
    }
    const bad = row.items.filter((i) => i.kind !== 'toggle' && i.kind !== 'textarea' && !STANDARD_HEIGHTS.includes(i.height));
    if (bad.length) {
      out.push({ signature: row.signature, rule: 'height', detail: bad.map((i) => `${i.kind}:${i.text}=${i.height}`).join(', ') });
    }
  }
  return out;
}

/** Remove toasts and un-clip scroll containers so every control is measurable. */
export const expandLayout = (): string | number => {
  document.querySelectorAll('[data-sonner-toaster],[data-sonner-toast],ol[class*=toast],[role=region][aria-label*=otif]').forEach((n) => n.remove());
  if (document.querySelector('[role=dialog],[role=alertdialog]')) return 'dialog';
  for (const el of [document.documentElement, document.body]) {
    el.style.height = 'auto';
    el.style.overflow = 'visible';
  }
  let n = 0;
  for (const el of document.querySelectorAll<HTMLElement>('body *')) {
    const cs = getComputedStyle(el);
    const clipped = /(auto|scroll|hidden)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 4;
    const fixedH = cs.height.endsWith('px') && String(el.className).match(/\b(h-screen|h-svh|h-dvh|h-full|min-h-0|max-h-|flex-1)\b/);
    if (clipped || fixedH) {
      el.style.overflow = 'visible';
      el.style.overflowY = 'visible';
      el.style.height = 'auto';
      el.style.maxHeight = 'none';
      n++;
    }
  }
  return n;
};

export const measurePage = async (page: Page): Promise<MeasuredRow[]> => {
  await page.evaluate(expandLayout);
  await page.waitForTimeout(200);
  return page.evaluate(collectRows);
};
