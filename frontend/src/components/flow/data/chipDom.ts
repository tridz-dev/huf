/**
 * The DOM side of the chip editor: text and chips in one editable box.
 * The segment list (lib/flow-data/chips.ts) is the truth; these functions draw it, read it back, and map the caret between
 * the screen and the "one position per typed character and one per chip" count the segment edits use.
 */
import type { Chip, Segment } from '@/lib/flow-data/chips';
import { normalize } from '@/lib/flow-data/chips';
import type { ChipInfo } from '@/lib/flow-data/model';

const CHIP_BASE = 'mx-0.5 inline-flex max-w-full cursor-pointer select-none items-baseline gap-1 rounded-md border px-1.5 text-meta leading-5 align-baseline text-left';
const CHIP_TONE = {
  ok: 'border-border bg-muted text-foreground hover:border-signal',
  missing: 'border-destructive bg-destructive-tint text-destructive',
  opaque: 'border-warning bg-warning-tint text-warning',
} as const;

export const chipTitle = (info: ChipInfo) =>
  info.missing ? 'This step was deleted. Pick the data again.' : info.opaque ? 'A value set another way. Click to choose data instead.' : info.sample ? `${info.sample} (example)` : 'No sample yet. Run a test to see a value.';

export function chipElement(chip: Chip, info: ChipInfo, editable: boolean): HTMLElement {
  const el = document.createElement('span');
  el.dataset.chip = chip.id;
  el.contentEditable = 'false';
  el.className = `${CHIP_BASE} ${info.missing ? CHIP_TONE.missing : info.opaque ? CHIP_TONE.opaque : CHIP_TONE.ok}`;
  const text = info.missing ? `Missing: ${info.stepTitle}` : info.stepTitle ? `${info.label} · ${info.stepTitle}` : info.label;
  // The full name is always on hover, even when a narrow box has to wrap it over two lines.
  el.title = `${text}. ${chipTitle(info)}`;
  el.setAttribute('aria-label', `${text}${info.sample ? `. Example: ${info.sample}` : ''}. Press Enter to change.`);
  el.setAttribute('role', 'button');
  el.tabIndex = -1;
  const label = document.createElement('span');
  label.className = 'min-w-0 whitespace-normal break-words';
  label.textContent = text;
  el.append(label);
  if (editable) {
    const x = document.createElement('span');
    x.dataset.remove = chip.id;
    x.setAttribute('role', 'button');
    x.setAttribute('aria-label', `Remove ${info.label}`);
    x.className = 'cursor-pointer px-0.5 text-muted-foreground hover:text-foreground';
    x.textContent = '×';
    el.append(x);
  }
  return el;
}

/** Draw `segments` into `root`. A trailing newline needs a spare line break or the box would not show the empty last line. */
export function renderSegments(root: HTMLElement, segments: Segment[], describe: (c: Chip) => ChipInfo, editable: boolean): void {
  const nodes: Node[] = [];
  for (const s of segments) nodes.push(s.kind === 'text' ? document.createTextNode(s.text) : chipElement(s.chip, describe(s.chip), editable));
  const last = segments[segments.length - 1];
  if (last && last.kind === 'text' && last.text.endsWith('\n')) {
    const pad = document.createElement('br');
    pad.dataset.pad = '1';
    nodes.push(pad);
  }
  root.replaceChildren(...nodes);
  root.dataset.empty = segments.length === 0 ? 'true' : 'false';
}

/** Read the box back. `chips` supplies each chip by id so edits keep their reference and name. */
export function readSegments(root: HTMLElement, chips: Map<string, Chip>): Segment[] {
  const out: Segment[] = [];
  const walk = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      out.push({ kind: 'text', text: (node.textContent ?? '').replace(/ /g, ' ').replace(/​/g, '') });
      return;
    }
    if (!(node instanceof HTMLElement)) return;
    if (node.dataset.chip) {
      const chip = chips.get(node.dataset.chip);
      if (chip) out.push({ kind: 'chip', chip });
      return;
    }
    if (node.tagName === 'BR') {
      if (!node.dataset.pad) out.push({ kind: 'text', text: '\n' });
      return;
    }
    // A block the browser made on its own (Enter in some browsers): its content on its own line.
    const isBlock = node.tagName === 'DIV' || node.tagName === 'P';
    if (isBlock && out.length > 0) out.push({ kind: 'text', text: '\n' });
    node.childNodes.forEach(walk);
  };
  root.childNodes.forEach(walk);
  return normalize(out);
}

const sizeOf = (node: Node) => (node.nodeType === Node.TEXT_NODE ? (node.textContent ?? '').length : node instanceof HTMLElement && node.dataset.chip ? 1 : node instanceof HTMLElement && node.tagName === 'BR' && !node.dataset.pad ? 1 : 0);

/** The caret as a position in the segment count, or null when the caret is not in this box. */
export function caretPosition(root: HTMLElement): number | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || !root.contains(sel.anchorNode)) return null;
  const { anchorNode, anchorOffset } = sel;
  let pos = 0;
  for (const child of Array.from(root.childNodes)) {
    if (child === anchorNode) return pos + (child.nodeType === Node.TEXT_NODE ? anchorOffset : 0);
    if (child.contains(anchorNode)) return pos + (child instanceof HTMLElement && child.dataset.chip ? 1 : 0);
    pos += sizeOf(child);
  }
  if (anchorNode === root) {
    pos = 0;
    Array.from(root.childNodes).slice(0, anchorOffset).forEach((c) => (pos += sizeOf(c)));
    return pos;
  }
  return pos;
}

export function setCaret(root: HTMLElement, position: number): void {
  const sel = window.getSelection();
  if (!sel) return;
  const range = document.createRange();
  let left = position;
  let placed = false;
  for (const child of Array.from(root.childNodes)) {
    const size = sizeOf(child);
    if (child.nodeType === Node.TEXT_NODE && left <= size) {
      range.setStart(child, left);
      placed = true;
      break;
    }
    if (size > 0 && left === 0) {
      range.setStartBefore(child);
      placed = true;
      break;
    }
    left -= size;
  }
  if (!placed) range.setStart(root, root.childNodes.length - (root.lastChild instanceof HTMLElement && root.lastChild.dataset.pad ? 1 : 0));
  range.collapse(true);
  sel.removeAllRanges();
  sel.addRange(range);
}
