import { describe, expect, it } from 'vitest';
import type { FlowEdge, FlowNode } from '../../types/flow.types';
import { makeChip, parseValue, type Segment } from './chips';
import { inferFields, sampleText } from './infer';
import { buildPickerModel, describeChip, previewOf } from './model';
import type { DataCatalog } from './types';

const node = (id: string, label: string, nodeType: 'trigger' | 'action' | 'end', extra: Record<string, unknown> = {}, y = 0): FlowNode =>
  ({ id, type: nodeType, position: { x: 0, y }, data: { label, nodeType, configured: true, ...extra } }) as FlowNode;
const edge = (source: string, target: string, handle?: string): FlowEdge => ({ id: `${source}-${target}`, source, target, sourceHandle: handle }) as FlowEdge;

const ORDER = { customer: { name: 'Ada Lovelace', email: 'ada@example.com' }, total: 450, placed: '2026-10-29', items: [{ sku: 'A-1', qty: 2 }, { sku: 'B-2', qty: 1 }], _x: 1, 'bad-key': 3 };

describe('inferFields', () => {
  const fields = inferFields(ORDER, 'input');
  const by = Object.fromEntries(fields.filter((f) => f.path).map((f) => [f.path, f]));
  it('names fields in plain words with examples', () => {
    expect(by['input.customer.name'].label).toBe('Customer > Name');
    expect(by['input.total']).toMatchObject({ type: 'number', sample: 450 });
    expect(by['input.placed'].type).toBe('date');
    expect(by['input.customer'].sample).toBe('Ada Lovelace');
  });
  it('lists carry a count, readable items and the fields of one item', () => {
    expect(by['input.items'].list).toMatchObject({ count: 2, item_type: 'object', item_texts: expect.any(Array) });
    expect(by['input.items'].list?.item_fields.map((f: { path: string | null }) => f.path)).toEqual(['sku', 'qty']);
  });
  it('hides internal keys and marks odd keys advanced only', () => {
    expect(fields.some((f) => f.path === 'input._x')).toBe(false);
    expect(fields.find((f) => f.advanced_only)).toMatchObject({ path: null, label: 'Bad key' });
  });
  it('keeps to 40 fields and handles a plain text result', () => {
    expect(inferFields(Object.fromEntries(Array.from({ length: 90 }, (_, i) => [`k${i}`, i])), 'n').length).toBe(40);
    expect(inferFields('Hello', 'n1', 'Reply')).toEqual([{ path: 'n1', label: 'Reply', type: 'text', sample: 'Hello' }]);
  });
  it('writes examples as people read them', () => {
    expect(sampleText(true, 'yes_no')).toBe('Yes');
    expect(sampleText(null, 'text')).toBe('');
  });
});

describe('picker model', () => {
  const nodes = [
    node('t', 'Webhook', 'trigger', { triggerConfig: { type: 'webhook' }, sample: ORDER }, 0),
    node('a', 'Look up customer', 'action', {}, 100),
    node('b', 'Ask the AI', 'action', {}, 200),
    node('c', 'Send email', 'action', {}, 300),
    node('side', 'Other branch', 'action', {}, 150),
    node('e', 'End', 'end', {}, 400),
  ];
  const edges = [edge('t', 'a'), edge('a', 'b'), edge('b', 'c'), edge('c', 'e'), edge('t', 'side')];
  const catalog: DataCatalog = {
    flow_id: 'f', node_id: 'c', loop: null,
    trigger: null,
    steps: [{ id: 'a', title: 'Look up customer', type: 'tool.call', is_trigger: false, source: 'last_run', ran_at: null, has_sample: true, fields: inferFields({ tier: 'gold' }, 'a') }],
  };
  const model = buildPickerModel(nodes, edges, 'c', catalog);

  it('lists the trigger first, then steps that always ran before, closest first', () => {
    expect(model.steps.map((s) => s.title)).toEqual(['Trigger: Webhook', 'Ask the AI', 'Look up customer']);
  });
  it('uses the example saved on the trigger and the server examples for steps', () => {
    expect(model.steps[0].hasSample).toBe(true);
    expect(model.steps[0].source).toBe('pinned');
    expect(model.steps[1].hasSample).toBe(false);
    expect(model.steps[2].fields[0].sample).toBe('gold');
  });
  it('never offers a bare input or trigger', () => {
    expect([...model.fieldByPath.keys()].every((p) => p !== 'input' && p !== 'trigger')).toBe(true);
  });
  it('offers nothing from steps after, or on another path', () => {
    expect(buildPickerModel(nodes, edges, 'a', null).steps.map((s) => s.id)).toEqual(['t']);
  });
  it('a trigger without an example says so', () => {
    const bare = buildPickerModel([node('t', 'Webhook', 'trigger', { triggerConfig: { type: 'webhook' } }), node('a', 'Mail', 'action')], [edge('t', 'a')], 'a', null);
    expect(bare.steps[0]).toMatchObject({ hasSample: false, canFetchLast: true, fields: [] });
  });
});

describe('chips in words', () => {
  const nodes = [node('t', 'New order', 'trigger', { triggerConfig: { type: 'webhook' }, sample: ORDER }), node('a', 'Mail', 'action')];
  const model = buildPickerModel(nodes, [edge('t', 'a')], 'a', null);
  const chip = (ref: string, mode?: 'summary' | 'joined' | 'count') => makeChip(ref, 'x', mode);

  it('describes a field with its step and example', () => {
    expect(describeChip(chip('input.customer.name'), model)).toMatchObject({ label: 'Customer > Name', stepTitle: 'New order', sample: 'Ada Lovelace', missing: false });
  });
  it('describes the first item of a list and its fields', () => {
    expect(describeChip(chip('input.items[0].sku'), model)).toMatchObject({ label: 'Items > First item > SKU', sample: 'A-1' });
  });
  it('words for the list verbs', () => {
    expect(describeChip(chip('input.items', 'count'), model)).toMatchObject({ label: 'How many items', sample: '2' });
    expect(describeChip(chip('input.items', 'joined'), model).sample).toContain(',');
  });
  it('a deleted step is a missing chip', () => {
    expect(describeChip(chip('gone.value'), model)).toMatchObject({ missing: true, stepTitle: 'step deleted' });
  });
  it('previews the text with examples and names what has no example yet', () => {
    const segs: Segment[] = [
      { kind: 'text', text: 'Hi ' }, { kind: 'chip', chip: chip('input.customer.name') }, { kind: 'text', text: ' - ' },
      { kind: 'chip', chip: chip('input.nothing') },
    ];
    expect(previewOf(segs, model)).toEqual({ text: 'Hi Ada Lovelace - [Nothing: no sample yet]', complete: false });
    const gone = parseValue({ $template: 'x {a}', vars: { a: { $from: 'gone.q' } } }).segments;
    expect(previewOf(gone, model).text).toBe('x [Missing: step deleted]');
  });
});
