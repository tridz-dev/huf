/**
 * What the "Use data" picker shows at each level, as plain rows. Pure, so the wording and the choices are tested without a screen.
 * Level 1 steps -> level 2 a step's fields -> (a thing with parts) its parts -> (a list) what to do with the items.
 */
import { isValidRef } from '@/lib/flow-data/chips';
import { sampleText, sentenceLabel } from '@/lib/flow-data/infer';
import type { PickerModel, PickerStep } from '@/lib/flow-data/model';
import type { CatalogField, DataPick, PickMode } from '@/lib/flow-data/types';

export type PickerView =
  | { kind: 'steps' }
  | { kind: 'fields'; stepId: string }
  | { kind: 'object'; stepId: string; path: string }
  | { kind: 'list'; stepId: string; path: string }
  | { kind: 'item'; stepId: string; path: string };

export type RowAction = { type: 'view'; view: PickerView } | { type: 'pick'; pick: DataPick } | { type: 'none' };

export interface PickerRow {
  key: string;
  testId: string;
  title: string;
  subtitle?: string;
  sample?: string;
  step?: PickerStep;
  disabled?: boolean;
  /** Opens a deeper level. */
  chevron?: boolean;
  action: RowAction;
}

/** `value`: text with chips; `list`: a list to go through; `ref`: a plain reference (prompts and conditions, where the form writes the text itself). */
export type Accept = 'value' | 'list' | 'ref';

const parentOf = (path: string) => path.replace(/(\.[^.[\]]+|\[\d+\])$/, '');

const find = (model: PickerModel, id: string) => model.steps.find((s) => s.id === id);
const fieldAt = (step: PickerStep, path: string) => step.fields.find((f) => f.path === path);

const pick = (step: PickerStep, ref: string, label: string, mode?: PickMode): RowAction => ({ type: 'pick', pick: { ref, label, stepTitle: step.chipTitle, stepId: step.id, mode } });

function fieldRow(step: PickerStep, f: CatalogField, accept: Accept, showStep: boolean): PickerRow {
  const sample = sampleText(f.sample, f.type);
  const base = { key: `${step.id}:${f.path}`, testId: `flow-use-data-field-${f.path}`, title: f.label, step, subtitle: showStep ? step.chipTitle : undefined };
  if (f.type === 'list') {
    const count = f.list?.count ?? 0;
    const title = `${f.label} (${count})`;
    if (accept === 'list') return { ...base, title, subtitle: 'Each item (use in a loop)', action: pick(step, f.path as string, f.label) };
    if (accept === 'ref') return { ...base, title, sample: f.list?.item_texts?.slice(0, 2).join(', '), action: pick(step, f.path as string, f.label) };
    return { ...base, title, sample: f.list?.item_texts?.slice(0, 2).join(', '), chevron: true, action: { type: 'view', view: { kind: 'list', stepId: step.id, path: f.path as string } } };
  }
  if (f.type === 'object') {
    const hasParts = step.fields.some((c) => c.path && parentOf(c.path) === f.path);
    return { ...base, sample, chevron: true, action: { type: 'view', view: { kind: 'object', stepId: step.id, path: f.path as string } }, disabled: !hasParts && accept === 'list' };
  }
  if (accept === 'list') return { ...base, sample, disabled: true, action: { type: 'none' } };
  return { ...base, sample, action: pick(step, f.path as string, f.label) };
}

export function stepRows(model: PickerModel): PickerRow[] {
  return model.steps.map((s) => {
    const n = s.fields.filter((f) => f.path && !f.advanced_only).length;
    const subtitle = s.hasSample ? (s.kind === 'loop' ? 'The item being worked on' : `${n} ${n === 1 ? 'field' : 'fields'}`) : 'No sample yet';
    return { key: s.id, testId: `flow-use-data-step-${s.id}`, title: s.title, subtitle, step: s, chevron: true, action: { type: 'view', view: { kind: 'fields', stepId: s.id } } };
  });
}

/** Rows that match a search anywhere (or inside one step). */
export function searchRows(model: PickerModel, query: string, accept: Accept, stepId?: string): PickerRow[] {
  const q = query.trim().toLowerCase();
  const out: PickerRow[] = [];
  for (const step of model.steps) {
    if (stepId && step.id !== stepId) continue;
    const stepHit = step.title.toLowerCase().includes(q);
    for (const f of step.fields) {
      if (!f.path || f.advanced_only) continue;
      if (accept === 'list' && f.type !== 'list') continue;
      const text = `${f.label} ${sampleText(f.sample, f.type)}`.toLowerCase();
      if (text.includes(q) || (stepHit && !stepId)) out.push(fieldRow(step, f, accept, true));
    }
  }
  return out;
}

function listRows(model: PickerModel, step: PickerStep, path: string): PickerRow[] {
  const f = fieldAt(step, path);
  if (!f?.list) return [];
  const loopHere = model.loopItemsPath === path;
  const label = f.label;
  const first: PickerRow = f.list.item_fields.length
    ? { key: 'first', testId: 'flow-use-data-first', title: 'First item', subtitle: f.list.item_texts?.[0], chevron: true, step, action: { type: 'view', view: { kind: 'item', stepId: step.id, path: `${path}[0]` } } }
    : { key: 'first', testId: 'flow-use-data-first', title: 'First item', sample: f.list.item_texts?.[0], step, action: pick(step, `${path}[0]`, `${label} first item`) };
  return [
    loopHere
      ? { key: 'each', testId: 'flow-use-data-each', title: 'Each item (use in a loop)', subtitle: 'The item this loop is working on', step, action: pick(step, 'foreach.item', 'Current item') }
      : { key: 'each', testId: 'flow-use-data-each', title: 'Each item (use in a loop)', subtitle: 'Add a Loop step to go through them one by one', disabled: true, step, action: { type: 'none' } },
    first,
    { key: 'joined', testId: 'flow-use-data-joined', title: 'All items, joined with commas', sample: (f.list.item_texts ?? []).join(', '), step, action: pick(step, path, label, 'joined') },
    { key: 'count', testId: 'flow-use-data-count', title: 'How many items', sample: String(f.list.count), step, action: pick(step, path, label, 'count') },
  ];
}

function partRows(step: PickerStep, path: string, accept: Accept, summaryLabel?: string): PickerRow[] {
  const parts = step.fields.filter((c) => c.path && parentOf(c.path) === path);
  const rows: PickerRow[] = [];
  if (accept === 'ref' && summaryLabel) {
    rows.push({ key: 'all', testId: 'flow-use-data-all', title: `Everything in ${summaryLabel}`, step, action: pick(step, path, summaryLabel) });
  }
  if (accept === 'value' && summaryLabel) {
    rows.push({ key: 'summary', testId: 'flow-use-data-summary', title: 'Show as summary table', subtitle: 'All of it as labelled rows', step, action: pick(step, path, summaryLabel, 'summary') });
  }
  return [...rows, ...parts.map((f) => fieldRow(step, f, accept, false))];
}

export function viewRows(view: PickerView, model: PickerModel, accept: Accept): PickerRow[] {
  if (view.kind === 'steps') return stepRows(model);
  const step = find(model, view.stepId);
  if (!step) return [];
  if (view.kind === 'fields') {
    const shown = accept === 'list' ? step.fields.filter((f) => f.type === 'list' && f.path) : step.fields.filter((f) => f.path && !f.advanced_only);
    const rows = shown.map((f) => fieldRow(step, f, accept, false));
    // A step's whole result: a loop collects it, a step that has not run yet has no fields to pick from.
    if (step.kind === 'step') {
      const hasRoot = step.fields.some((f) => f.path === step.id);
      if (!step.hasSample) rows.push({ key: 'result', testId: 'flow-use-data-result', title: 'Its result', subtitle: 'No sample yet: run a test to see it', step, action: pick(step, step.id, step.chipTitle) });
      else if (!hasRoot) {
        const summary = accept === 'value';
        rows.push({ key: 'result', testId: 'flow-use-data-result', title: summary ? 'Show everything as a summary table' : 'Everything this step produced', step, action: pick(step, step.id, step.chipTitle, summary ? 'summary' : undefined) });
      }
    }
    return rows;
  }
  if (view.kind === 'object') return partRows(step, view.path, accept, fieldAt(step, view.path)?.label);
  if (view.kind === 'list') return listRows(model, step, view.path);
  // The first item of a list: its fields, with the path pointing at item 0.
  const listPath = view.path.replace(/\[0\]$/, '');
  const list = fieldAt(step, listPath);
  const rows: PickerRow[] = [{ key: 'summary', testId: 'flow-use-data-summary', title: 'Show as summary table', subtitle: 'All of the first item as rows', step, action: pick(step, view.path, `${list?.label ?? 'Item'} first item`, 'summary') }];
  for (const f of list?.list?.item_fields ?? []) {
    if (!f.path || f.advanced_only) continue;
    rows.push({ key: `item:${f.path}`, testId: `flow-use-data-field-${view.path}.${f.path}`, title: f.label, sample: sampleText(f.sample, f.type), step, action: pick(step, `${view.path}.${f.path}`, `${list?.label ?? 'Item'} first ${f.label}`) });
  }
  return rows;
}

export function viewTitle(view: PickerView, model: PickerModel): string {
  if (view.kind === 'steps') return 'Use data from';
  const step = find(model, view.stepId);
  if (view.kind === 'fields') return step?.title ?? 'Use data from';
  const path = view.kind === 'item' ? view.path.replace(/\[0\]$/, '') : view.path;
  const label = step ? fieldAt(step, path)?.label : undefined;
  return view.kind === 'list' ? `${label ?? 'List'}: what to use` : view.kind === 'item' ? `${label ?? 'List'}: first item` : label ?? 'Parts';
}

export function parentView(view: PickerView): PickerView {
  if (view.kind === 'steps') return view;
  if (view.kind === 'fields') return { kind: 'steps' };
  if (view.kind === 'item') return { kind: 'list', stepId: view.stepId, path: view.path.replace(/\[0\]$/, '') };
  return { kind: 'fields', stepId: view.stepId };
}

/**
 * Data typed by hand ("Can't find it? Type the field name"). A full reference (`input.customer.name`, `n_5.total`) is used as it is when
 * it starts at the trigger, the loop or a step the picker offers; inside a step's fields a short name (`customer.name`) starts at that
 * step. A bare `input` or `trigger` is never accepted: it would hand over everything the trigger sent.
 */
export function resolveTyped(text: string, model: PickerModel, step?: PickerStep): DataPick | null {
  const typed = text.trim().replace(/\s+/g, '_');
  if (!typed) return null;
  const roots = new Map(model.steps.map((s) => [s.root, s]));
  const full = roots.get(typed.split(/[.[]/)[0]) ?? (typed.startsWith('foreach.') ? model.steps.find((s) => s.kind === 'loop') : undefined);
  const startsHere = full && typed.length > full.root.length && isValidRef(typed) && typed !== full.root;
  const ref = startsHere ? typed : step ? `${step.root}.${typed}` : '';
  const owner = startsHere ? full : step;
  if (!owner || !isValidRef(ref) || ref === owner.root) return null;
  return { ref, label: sentenceLabel(ref.split(/[.[]/).filter(Boolean).pop() ?? ref), stepTitle: owner.chipTitle, stepId: owner.id };
}
