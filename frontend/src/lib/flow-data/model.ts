/**
 * The picker's model: which steps a field can read from, their fields and examples, and what a chip means.
 * Built from the flow in the editor (so a step added a moment ago is there) plus the server's catalog (the examples).
 */
import { enclosingLoops, guaranteedPredecessors, loopBodyNodes, type RefScope } from '../flow/flowRefs';
import type { FlowEdge, FlowNode } from '../../types/flow.types';
import { gatewayPickerFields } from './gatewayFields';
import { isGatewayKindId } from '../flow-gateway/gatewayWords';
import { GATEWAY_TRIGGER_KINDS } from '../flow-gateway/triggerKinds';
import type { GatewayRegistry } from '../flow-gateway/gatewayTrigger.types';
import { inferFields, sampleText, sentenceLabel } from './infer';
import type { CatalogField, CatalogStep, DataCatalog, ListInfo, DataPick, PickMode, SampleSource } from './types';
import type { Chip, Segment } from './chips';

export type PickerStepKind = 'trigger' | 'loop' | 'step';

export interface PickerStep {
  id: string;
  /** What the row says: "Trigger: Webhook", "This loop: current item", the step's title. */
  title: string;
  /** The step's own title, for chips ("New order"). */
  chipTitle: string;
  kind: PickerStepKind;
  node?: FlowNode;
  /** Fields the person can pick. Their `path` is ready to store. */
  fields: CatalogField[];
  hasSample: boolean;
  source: SampleSource;
  /** Where "type the field name yourself" starts: `input`, a step id or `foreach.item`. */
  root: string;
  canFetchLast: boolean;
  /** The loop's list, when this row is the current item of a loop. */
  doctype?: string | null;
}

export interface PickerModel {
  steps: PickerStep[];
  /** Everything pickable, by path (for describing chips). */
  fieldByPath: Map<string, { field: CatalogField; step: PickerStep }>;
  nodes: FlowNode[];
  loopItemsPath: string | null;
}

type Edge = Pick<FlowEdge, 'source' | 'target' | 'sourceHandle' | 'data'>;

/** Longest distance from a trigger, so "newest first" puts the step right before this one on top. */
function depths(nodes: FlowNode[], edges: Edge[]): Map<string, number> {
  const out = new Map<string, number>();
  const next = new Map<string, string[]>();
  for (const e of edges) next.set(e.source, [...(next.get(e.source) ?? []), e.target]);
  const walk = (id: string, d: number, seen: Set<string>) => {
    if (seen.has(id) || (out.get(id) ?? -1) >= d) return;
    out.set(id, d);
    seen.add(id);
    for (const t of next.get(id) ?? []) walk(t, d + 1, seen);
    seen.delete(id);
  };
  for (const n of nodes) if (n.data.nodeType === 'trigger') walk(n.id, 0, new Set());
  return out;
}

const serverStep = (catalog: DataCatalog | null, id: string): CatalogStep | undefined =>
  catalog?.trigger?.id === id ? catalog.trigger : catalog?.steps.find((s) => s.id === id);

const asRecord = (v: unknown): Record<string, unknown> | undefined => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined);

export function buildPickerModel(nodes: FlowNode[], edges: Edge[], nodeId: string | null | undefined, catalog: DataCatalog | null, scope: RefScope = 'ancestors', registry: GatewayRegistry | null = null): PickerModel {
  const steps: PickerStep[] = [];
  const trigger = scope === 'ancestors' ? nodes.find((n) => n.data.nodeType === 'trigger') : undefined;
  if (trigger) {
    const server = serverStep(catalog, trigger.id);
    const local = asRecord(trigger.data.sample);
    const kind = (trigger.data.triggerConfig as { type?: string } | undefined)?.type;
    // A chat trigger is described by the server registry (friendly names), not guessed from a sample's keys.
    const gatewaySpec = isGatewayKindId(kind) ? registry?.specs[GATEWAY_TRIGGER_KINDS.find((k) => k.id === kind)!.nodeType] : undefined;
    const fields = gatewaySpec ? gatewayPickerFields(gatewaySpec, local) : local ? inferFields(local, 'input', 'What the trigger sent') : server?.fields ?? [];
    steps.push({
      id: trigger.id,
      title: `Trigger: ${trigger.data.label}`,
      chipTitle: trigger.data.label,
      kind: 'trigger',
      node: trigger,
      fields,
      hasSample: fields.length > 0,
      source: local ? 'pinned' : gatewaySpec ? 'example' : server?.source ?? 'none',
      root: 'input',
      canFetchLast: kind === 'webhook',
      doctype: server?.doctype ?? (trigger.data.triggerConfig as { doctype?: string } | undefined)?.doctype ?? null,
    });
  }
  if (scope === 'loop-body' && nodeId) {
    // A loop's "result to collect": what the steps inside this loop produce, and the item being worked on.
    const loopNode = nodes.find((n) => n.id === nodeId);
    steps.push({
      id: `${nodeId}:item`, title: 'This loop: current item', chipTitle: loopNode?.data.label ?? 'Loop', kind: 'loop', node: loopNode,
      fields: [{ path: 'foreach.item', label: 'Current item', type: 'text', sample: null }, { path: 'foreach.index', label: 'Item number', type: 'number', sample: null }],
      hasSample: false, source: 'none', root: 'foreach.item', canFetchLast: false,
    });
    for (const id of loopBodyNodes(nodeId, edges)) {
      const n = nodes.find((x) => x.id === id);
      if (!n || n.data.nodeType !== 'action') continue;
      steps.push({ id: n.id, title: n.data.label, chipTitle: n.data.label, kind: 'step', node: n, fields: [], hasSample: false, source: 'none', root: n.id, canFetchLast: false });
    }
  } else if (nodeId) {
    const loops = enclosingLoops(nodeId, nodes, edges);
    if (loops.length > 0) {
      const loopNode = nodes.find((n) => n.id === loops[0]);
      const itemFields = catalog?.loop?.id === loops[0] ? catalog.loop.item_fields : [];
      const fields: CatalogField[] = [
        ...itemFields,
        ...(itemFields.length === 0 ? [{ path: 'foreach.item', label: 'Current item', type: 'text' as const, sample: null }] : []),
        { path: 'foreach.index', label: 'Item number', type: 'number', sample: null },
      ];
      steps.push({
        id: `${loops[0]}:item`, title: 'This loop: current item', chipTitle: loopNode?.data.label ?? 'Loop', kind: 'loop', node: loopNode,
        fields, hasSample: itemFields.length > 0, source: itemFields.length > 0 ? 'last_run' : 'none', root: 'foreach.item', canFetchLast: false,
      });
    }
    const guaranteed = guaranteedPredecessors(nodeId, nodes, edges);
    const depth = depths(nodes, edges);
    const before = nodes
      .filter((n) => guaranteed.has(n.id) && n.data.nodeType === 'action' && !loops.includes(n.id))
      .sort((a, b) => (depth.get(b.id) ?? 0) - (depth.get(a.id) ?? 0) || (b.position?.y ?? 0) - (a.position?.y ?? 0));
    for (const n of before) {
      const server = serverStep(catalog, n.id);
      const local = asRecord(n.data.sample);
      const fields = local ? inferFields(local, n.id) : server?.fields ?? [];
      steps.push({
        id: n.id, title: n.data.label, chipTitle: n.data.label, kind: 'step', node: n, fields, hasSample: fields.length > 0,
        source: local ? 'pinned' : server?.source ?? 'none', root: n.id, canFetchLast: false,
      });
    }
  }
  const fieldByPath = new Map<string, { field: CatalogField; step: PickerStep }>();
  for (const step of steps) for (const field of step.fields) if (field.path && !fieldByPath.has(field.path)) fieldByPath.set(field.path, { field, step });
  const loopItemsPath = nodeId && catalog?.loop ? catalog.loop.items_path : null;
  return { steps, fieldByPath, nodes, loopItemsPath };
}

// ---- what a chip means ----

export interface ChipInfo {
  /** "Customer name" */
  label: string;
  /** "New order" */
  stepTitle: string;
  /** The example, in words; '' when there is none. */
  sample: string;
  /** The step or field is gone. */
  missing: boolean;
  /** Not a reference the picker made (a nested value, an unfinished placeholder). */
  opaque: boolean;
  type?: CatalogField['type'];
}

const INDEX = /\[(\d+)\]/;

function tailLabel(path: string): string {
  const rest = path.replace(/^(input|trigger|row)\.?/, '').replace(/^foreach\.(item|index)\.?/, '');
  const parts = rest.split(/\.(?![^[]*\])/).filter(Boolean);
  return parts
    .map((p) => p.replace(INDEX, (_m, n) => ` ${Number(n) === 0 ? 'first item' : `item ${Number(n) + 1}`}`).trim())
    .map((p, i) => (i === 0 ? sentenceLabel(p) : sentenceLabel(p)))
    .join(' > ');
}

/** The last part of a field's name, lower-cased unless it is an acronym ("Items" -> "items", "SKU" stays). */
const lastWord = (label: string) => {
  const part = label.split(' > ').pop() ?? label;
  return part.replace(/\b([A-Z])([a-z])/g, (_m, a: string, b: string) => `${a.toLowerCase()}${b}`);
};

const MODE_LABEL: Record<PickMode, (l: string) => string> = {
  summary: (l) => `Summary of ${l}`,
  joined: (l) => `All ${lastWord(l)}, joined`,
  count: (l) => `How many ${lastWord(l)}`,
};

export function describeChip(chip: Chip, model: PickerModel): ChipInfo {
  const wrap = (label: string) => (chip.mode ? MODE_LABEL[chip.mode](label) : label);
  if (chip.unbound) return { label: 'Choose data', stepTitle: '', sample: '', missing: false, opaque: true };
  if (chip.raw !== undefined) return { label: 'Custom value', stepTitle: '', sample: '', missing: false, opaque: true };
  const ref = chip.ref;
  const root = ref.split(/[.[]/)[0] === 'foreach' ? ref.split('.').slice(0, 2).join('.') : ref.split(/[.[]/)[0];
  const known = model.fieldByPath.get(ref);
  let step: PickerStep | undefined = known?.step;
  if (!step) {
    if (root === 'input' || root === 'trigger') step = model.steps.find((s) => s.kind === 'trigger');
    else if (root.startsWith('foreach')) step = model.steps.find((s) => s.kind === 'loop');
    else step = model.steps.find((s) => s.id === root);
  }
  const nodeGone = !root.startsWith('foreach') && root !== 'input' && root !== 'trigger' && root !== 'row' && !model.nodes.some((n) => n.id === root);
  if (nodeGone) return { label: tailLabel(ref) || 'Data', stepTitle: 'step deleted', sample: '', missing: true, opaque: false };
  if (known) {
    const { field } = known;
    let sample = sampleText(field.sample, field.type);
    if (chip.mode === 'count' && field.list) sample = String(field.list.count);
    if (chip.mode === 'joined' && field.list) sample = joinedSample(field.list);
    return { label: wrap(field.label), stepTitle: step?.chipTitle ?? '', sample, missing: false, opaque: false, type: field.type };
  }
  // A path into the first item of a list: `input.items[0].sku`.
  const m = INDEX.exec(ref);
  if (m) {
    const listPath = ref.slice(0, m.index);
    const list = model.fieldByPath.get(listPath);
    if (list?.field.list) {
      const rest = ref.slice(m.index + m[0].length).replace(/^\./, '');
      const item = rest ? list.field.list.item_fields.find((f) => f.path === rest) : undefined;
      const idx = Number(m[1]);
      const word = idx === 0 ? 'First item' : `Item ${idx + 1}`;
      const label = `${list.field.label} > ${word}${item ? ` > ${item.label}` : rest ? ` > ${sentenceLabel(rest)}` : ''}`;
      const sample = item ? sampleText(item.sample, item.type) : !rest ? list.field.list.item_texts?.[idx] ?? '' : '';
      return { label: wrap(label), stepTitle: step?.chipTitle ?? '', sample, missing: false, opaque: false };
    }
  }
  if (ref === 'foreach.item') return { label: 'Current item', stepTitle: step?.chipTitle ?? 'Loop', sample: '', missing: false, opaque: false };
  if (ref === 'foreach.index') return { label: 'Item number', stepTitle: step?.chipTitle ?? 'Loop', sample: '', missing: false, opaque: false };
  if (ref === 'input' || ref === 'trigger') return { label: 'Everything the trigger sent', stepTitle: step?.chipTitle ?? '', sample: '', missing: false, opaque: false };
  if (!root.includes('.') && root === ref) return { label: 'Result', stepTitle: step?.chipTitle ?? '', sample: '', missing: false, opaque: false };
  return { label: wrap(tailLabel(ref) || 'Data'), stepTitle: step?.chipTitle ?? '', sample: '', missing: false, opaque: false };
}

function joinedSample(list: ListInfo): string {
  const texts = list.item_texts ?? [];
  return `${texts.join(', ')}${list.count > texts.length ? '…' : ''}`;
}

/** The sentence under an input: what the text becomes with the examples filled in. `[Name: no sample yet]` where there is none. */
export function previewOf(segments: Segment[], model: PickerModel): { text: string; complete: boolean } {
  let complete = true;
  const text = segments
    .map((s) => {
      if (s.kind === 'text') return s.text;
      const info = describeChip(s.chip, model);
      if (info.missing) return '[Missing: step deleted]';
      if (info.opaque) return `[${info.label}]`;
      if (info.sample) return info.sample;
      complete = false;
      return `[${info.label}: no sample yet]`;
    })
    .join('');
  return { text, complete };
}

/** Whether a pick of this field must be written as text-with-marker (an object or a list is never pasted as a raw value). */
export function toPick(field: CatalogField, step: PickerStep, mode?: PickMode, pathOverride?: string, labelOverride?: string): DataPick | null {
  const ref = pathOverride ?? field.path;
  if (!ref) return null;
  return { ref, label: labelOverride ?? field.label, stepTitle: step.chipTitle, stepId: step.id, mode };
}
