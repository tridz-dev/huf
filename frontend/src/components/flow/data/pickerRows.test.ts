import { describe, expect, it } from 'vitest';
import type { FlowEdge, FlowNode } from '@/types/flow.types';
import { buildPickerModel } from '@/lib/flow-data/model';
import { parentView, resolveTyped, searchRows, viewRows, viewTitle } from './pickerRows';

const node = (id: string, label: string, nodeType: 'trigger' | 'action' | 'end', extra: Record<string, unknown> = {}): FlowNode =>
  ({ id, type: nodeType, position: { x: 0, y: 0 }, data: { label, nodeType, configured: true, ...extra } }) as FlowNode;
const edge = (source: string, target: string, handle?: string): FlowEdge => ({ id: `${source}-${target}`, source, target, sourceHandle: handle, data: handle === 'body' ? { route: 'body' } : undefined }) as FlowEdge;

const ORDER = { customer: { name: 'Ada Lovelace', email: 'ada@example.com' }, total: 450, items: [{ sku: 'A-1', qty: 2 }, { sku: 'B-2', qty: 1 }] };
const nodes = [node('t', 'Webhook', 'trigger', { triggerConfig: { type: 'webhook' }, sample: ORDER }), node('a', 'Look up', 'action'), node('m', 'Mail', 'action')];
const edges = [edge('t', 'a'), edge('a', 'm')];
const model = buildPickerModel(nodes, edges, 'm', null);

describe('picker levels', () => {
  it('level 1: the trigger first, each step with a plain subtitle', () => {
    const rows = viewRows({ kind: 'steps' }, model, 'value');
    expect(rows.map((r) => r.title)).toEqual(['Trigger: Webhook', 'Look up']);
    expect(rows.map((r) => r.subtitle)).toEqual(['5 fields', 'No sample yet']);
    expect(rows.every((r) => r.action.type === 'view')).toBe(true);
  });

  it('level 2: fields by label with their example; a field picks, a list opens', () => {
    const rows = viewRows({ kind: 'fields', stepId: 't' }, model, 'value');
    const name = rows.find((r) => r.title === 'Customer > Name');
    expect(name).toMatchObject({ sample: 'Ada Lovelace', action: { type: 'pick', pick: { ref: 'input.customer.name', stepTitle: 'Webhook' } } });
    expect(rows.find((r) => r.title === 'Items (2)')).toMatchObject({ chevron: true, action: { type: 'view', view: { kind: 'list', path: 'input.items' } } });
  });

  it('a thing with parts offers a summary table and its parts', () => {
    const rows = viewRows({ kind: 'object', stepId: 't', path: 'input.customer' }, model, 'value');
    expect(rows[0]).toMatchObject({ title: 'Show as summary table', action: { type: 'pick', pick: { ref: 'input.customer', mode: 'summary' } } });
    expect(rows.slice(1).map((r) => r.title)).toEqual(['Customer > Name', 'Customer > Email']);
  });

  it('a list offers each / first / all joined / how many in plain words', () => {
    const rows = viewRows({ kind: 'list', stepId: 't', path: 'input.items' }, model, 'value');
    expect(rows.map((r) => r.title)).toEqual(['Each item (use in a loop)', 'First item', 'All items, joined with commas', 'How many items']);
    expect(rows[0].disabled).toBe(true); // not inside a loop over this list
    expect(rows[2].action).toMatchObject({ pick: { ref: 'input.items', mode: 'joined' } });
    expect(rows[3]).toMatchObject({ sample: '2', action: { pick: { ref: 'input.items', mode: 'count' } } });
  });

  it('the first item opens its fields, written as a path to item 0', () => {
    const rows = viewRows({ kind: 'item', stepId: 't', path: 'input.items[0]' }, model, 'value');
    expect(rows.map((r) => r.title)).toEqual(['Show as summary table', 'SKU', 'Qty']);
    expect(rows[1].action).toMatchObject({ pick: { ref: 'input.items[0].sku' } });
  });

  it('never offers a bare input or trigger anywhere', () => {
    const all = [
      ...viewRows({ kind: 'steps' }, model, 'value'),
      ...viewRows({ kind: 'fields', stepId: 't' }, model, 'value'),
      ...viewRows({ kind: 'fields', stepId: 't' }, model, 'ref'),
    ];
    const refs = all.flatMap((r) => (r.action.type === 'pick' ? [r.action.pick.ref] : []));
    expect(refs.some((r) => r === 'input' || r === 'trigger')).toBe(false);
  });
});

describe('modes of the picker', () => {
  it('a list field takes a whole list when the input wants one', () => {
    const rows = viewRows({ kind: 'fields', stepId: 't' }, model, 'list');
    expect(rows.map((r) => r.title)).toEqual(['Items (2)']);
    expect(rows[0]).toMatchObject({ subtitle: 'Each item (use in a loop)', action: { type: 'pick', pick: { ref: 'input.items' } } });
  });

  it('a reference field picks any field directly and may take a step whole', () => {
    const rows = viewRows({ kind: 'fields', stepId: 'a' }, model, 'ref');
    expect(rows.map((r) => r.title)).toEqual(['Its result']);
    expect(rows[0].action).toMatchObject({ pick: { ref: 'a' } });
    expect(viewRows({ kind: 'object', stepId: 't', path: 'input.customer' }, model, 'ref')[0].title).toBe('Everything in Customer');
  });
});

describe('search and navigation', () => {
  it('finds fields in every step by label or by example', () => {
    expect(searchRows(model, 'email', 'value').map((r) => r.title)).toEqual(['Customer > Email']);
    expect(searchRows(model, 'lovelace', 'value').map((r) => r.title)).toContain('Customer > Name');
    expect(searchRows(model, 'nothing here', 'value')).toEqual([]);
  });

  it('knows where back goes and what each level is called', () => {
    expect(parentView({ kind: 'item', stepId: 't', path: 'input.items[0]' })).toEqual({ kind: 'list', stepId: 't', path: 'input.items' });
    expect(parentView({ kind: 'fields', stepId: 't' })).toEqual({ kind: 'steps' });
    expect(viewTitle({ kind: 'steps' }, model)).toBe('Use data from');
    expect(viewTitle({ kind: 'list', stepId: 't', path: 'input.items' }, model)).toBe('Items: what to use');
  });

  it('inside a loop over this list, "each item" is the loop item', () => {
    const loopNodes = [nodes[0], node('l', 'Loop', 'action', { actionConfig: { type: 'foreach' } }), node('p', 'Post', 'action')];
    const loopEdges = [edge('t', 'l'), edge('l', 'p', 'body')];
    const catalog = { flow_id: 'f', node_id: 'p', trigger: null, steps: [], loop: { id: 'l', title: 'Loop', items_path: 'input.items', item_fields: [] } };
    const m = buildPickerModel(loopNodes, loopEdges, 'p', catalog);
    expect(m.steps.map((s) => s.title)).toContain('This loop: current item');
    expect(viewRows({ kind: 'list', stepId: 't', path: 'input.items' }, m, 'value')[0]).toMatchObject({ action: { pick: { ref: 'foreach.item' } } });
  });
});

describe('typed names', () => {
  const step = model.steps[0];
  it('a full reference that starts at an offered step is used as it is', () => {
    expect(resolveTyped('input.customer.name', model)).toMatchObject({ ref: 'input.customer.name', stepId: 't', stepTitle: 'Webhook', label: 'Name' });
    expect(resolveTyped('a.tier', model)).toMatchObject({ ref: 'a.tier', stepId: 'a' });
  });
  it('inside a step a short name starts at that step', () => {
    expect(resolveTyped('customer.name', model, step)?.ref).toBe('input.customer.name');
    expect(resolveTyped('order total', model, step)?.ref).toBe('input.order_total');
  });
  it('never a bare input or trigger, nothing odd, nothing from a step that is not offered', () => {
    expect(resolveTyped('input', model)).toBeNull();
    expect(resolveTyped('input', model, step)?.ref).toBe('input.input');
    expect(resolveTyped('', model, step)).toBeNull();
    expect(resolveTyped('customer.name', model)).toBeNull();
    expect(resolveTyped('m.value', model)).toBeNull();
    expect(resolveTyped('a-b.c', model, step)).toBeNull();
  });
});

describe('a step that has not run yet', () => {
  it('can still be used as a whole: "Its result"', () => {
    const rows = viewRows({ kind: 'fields', stepId: 'a' }, model, 'value');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ title: 'Its result', subtitle: 'No sample yet: run a test to see it', action: { type: 'pick', pick: { ref: 'a', stepTitle: 'Look up' } } });
  });
  it('a step with examples offers its whole result as a summary table when it has no single value', () => {
    const withSample = [nodes[0], { ...nodes[1], data: { ...nodes[1].data, sample: { tier: 'gold', credit: 5 } } }, nodes[2]];
    const m = buildPickerModel(withSample as FlowNode[], edges, 'm', null);
    const rows = viewRows({ kind: 'fields', stepId: 'a' }, m, 'value');
    expect(rows.map((r) => r.title)).toEqual(['Tier', 'Credit', 'Show everything as a summary table']);
    expect(rows[2].action).toMatchObject({ pick: { ref: 'a', mode: 'summary' } });
  });
});
