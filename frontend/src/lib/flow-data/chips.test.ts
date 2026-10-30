import { describe, expect, it } from 'vitest';
import {
  chipBefore, insertChip, isValidRef, lengthOf, makeChip, modeOfName, parseValue, positionOf, removeChip, replaceChip,
  serializeValue, variableName, type Segment,
} from './chips';

const round = (v: unknown) => serializeValue(parseValue(v));

describe('stored forms round trip', () => {
  const cases: Array<[string, unknown]> = [
    ['empty text', ''],
    ['plain text', 'Hello there'],
    ['text with braces is just text', 'Hi {name} and {{x}}'],
    ['whole value is one reference', { $from: 'n1.customer.name' }],
    ['trigger reference', { $from: 'input.items[0].sku' }],
    ['loop item', { $from: 'foreach.item.name' }],
    ['text and one chip', { $template: 'Hi {name}', vars: { name: { $from: 'input.name' } } }],
    ['two chips and escaped braces', { $template: '{{ {a} }} and {b}!', vars: { a: { $from: 'input.a' }, b: { $from: 'n1' } } }],
    ['one chip alone kept as a template', { $template: '{a}', vars: { a: { $from: 'input.a' } } }],
    ['summary marker', { $template: '{table_order}', vars: { table_order: { $from: 'input.order' } } }],
    ['same chip twice', { $template: '{a} / {a}', vars: { a: { $from: 'input.a' } } }],
    ['template without a vars key', { $template: 'plain {{x}}' }],
    ['template with empty vars', { $template: 'plain', vars: {} }],
    ['variable that is not a reference', { $template: 'Hi {n}', vars: { n: { $template: '{x}', vars: { x: { $from: 'input.x' } } } } }],
    ['literal variable', { $template: 'Hi {n}', vars: { n: 'Ada' } }],
    ['variable never mentioned', { $template: 'Hi', vars: { unused: { $from: 'input.x' } } }],
    ['placeholder with no variable', { $template: 'Hi {gone}', vars: {} }],
    ['number', 42],
    ['yes', true],
    ['list of values', ['a', { $from: 'input.a' }]],
    ['object of values', { to: 'a@b.c', n: { $from: 'input.n' } }],
  ];
  for (const [name, value] of cases) it(name, () => expect(round(value)).toEqual(value));

  it('property: random stored values survive parse then serialize', () => {
    let seed = 7;
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
    const pick = <T,>(xs: T[]) => xs[Math.floor(rnd() * xs.length)];
    const pieces = ['Hi ', ' ', '{', '}', '{{', '}}', 'é', '😀', '\n', '$from', '"', 'a b'];
    const refs = ['input.a', 'input.customer.name', 'n_1', 'n_1.items[0]', 'foreach.item', 'foreach.index', 'row.x'];
    for (let i = 0; i < 400; i++) {
      let template = '';
      const vars: Record<string, unknown> = {};
      const count = Math.floor(rnd() * 4);
      for (let k = 0; k < Math.floor(rnd() * 5); k++) template += pick(pieces).replace(/\{/g, '{{').replace(/\}/g, '}}');
      for (let k = 0; k < count; k++) {
        const name = `${pick(['v', 'table_', 'joined_', 'count_'])}${k}`;
        vars[name] = rnd() < 0.8 ? { $from: pick(refs) } : pick(['lit', 3, { $template: 'x' }]);
        template += `${pick(pieces).replace(/\{/g, '{{').replace(/\}/g, '}}')}{${name}}`;
      }
      if (rnd() < 0.2) vars.never_used = { $from: pick(refs) };
      const stored = rnd() < 0.15 ? { $from: pick(refs) } : rnd() < 0.15 ? template.replace(/\{\{|\}\}/g, '-') : { $template: template, ...(rnd() < 0.9 || count ? { vars } : {}) };
      expect(round(stored)).toEqual(stored);
    }
  });
});

describe('what the editor stores', () => {
  const text = (t: string): Segment => ({ kind: 'text', text: t });
  const chip = (ref: string, label: string, mode?: 'summary' | 'joined' | 'count'): Segment => ({ kind: 'chip', chip: makeChip(ref, label, mode) });

  it('text only is a plain string, braces and all', () => {
    expect(serializeValue({ segments: [text('Order {42} {{x}}')] })).toBe('Order {42} {{x}}');
  });

  it('one chip alone is a reference', () => {
    expect(serializeValue({ segments: [chip('input.name', 'Customer name')] })).toEqual({ $from: 'input.name' });
  });

  it('text around a chip is a template and typed braces are escaped (leak 16)', () => {
    const v = serializeValue({ segments: [text('Hi {x}, '), chip('input.name', 'Customer name'), text(' }')] });
    expect(v).toEqual({ $template: 'Hi {{x}}, {customer_name} }}', vars: { customer_name: { $from: 'input.name' } } });
  });

  it('a second insert appends: two chips, two variables', () => {
    const v = serializeValue({ segments: [text('Hi '), chip('input.name', 'Customer name'), text(' from '), chip('input.company', 'Company')] });
    expect(v).toEqual({
      $template: 'Hi {customer_name} from {company}',
      vars: { customer_name: { $from: 'input.name' }, company: { $from: 'input.company' } },
    });
  });

  it('two chips with the same name that read different data get different variables', () => {
    const v = serializeValue({ segments: [chip('n1.name', 'Name'), text(' & '), chip('n2.name', 'Name')] }) as { $template: string; vars: Record<string, unknown> };
    expect(v.$template).toBe('{name} & {name_2}');
    expect(v.vars).toEqual({ name: { $from: 'n1.name' }, name_2: { $from: 'n2.name' } });
  });

  it('a whole object or list is written as a template with a marker, never as a bare reference', () => {
    expect(serializeValue({ segments: [chip('input.order', 'Order', 'summary')] })).toEqual({ $template: '{table_order}', vars: { table_order: { $from: 'input.order' } } });
    expect(serializeValue({ segments: [chip('input.items', 'Items', 'count')] })).toEqual({ $template: '{count_items}', vars: { count_items: { $from: 'input.items' } } });
  });

  it('a number field stores a number', () => {
    expect(serializeValue({ segments: [text('12.5')] }, { kind: 'number' })).toBe(12.5);
    expect(serializeValue({ segments: [text('12x')] }, { kind: 'number' })).toBe('12x');
  });

  it('chips and text read back after a save', () => {
    const stored = serializeValue({ segments: [text('Hi '), chip('input.name', 'Customer name'), text('!')] });
    const back = parseValue(stored);
    expect(back.segments.map((s) => (s.kind === 'text' ? s.text : `[${s.chip.ref}]`))).toEqual(['Hi ', '[input.name]', '!']);
  });
});

describe('edits', () => {
  it('inserts at a position, splitting the text', () => {
    const segs = insertChip([{ kind: 'text', text: 'abcd' }], 2, makeChip('input.x', 'X'));
    expect(segs.map((s) => (s.kind === 'text' ? s.text : '*'))).toEqual(['ab', '*', 'cd']);
    expect(lengthOf(segs)).toBe(5);
  });

  it('inserts at the ends and into an empty value', () => {
    expect(insertChip([], 0, makeChip('input.x', 'X'))).toHaveLength(1);
    const segs = insertChip([{ kind: 'text', text: 'ab' }], 2, makeChip('input.x', 'X'));
    expect(segs.map((s) => s.kind)).toEqual(['text', 'chip']);
  });

  it('finds, swaps and removes a chip', () => {
    const c = makeChip('input.x', 'X');
    const segs = insertChip([{ kind: 'text', text: 'ab' }], 1, c);
    expect(positionOf(segs, c.id)).toBe(1);
    expect(chipBefore(segs, 2)?.id).toBe(c.id);
    const swapped = replaceChip(segs, c.id, makeChip('input.y', 'Y'));
    expect(swapped.some((s) => s.kind === 'chip' && s.chip.ref === 'input.y' && s.chip.id === c.id)).toBe(true);
    expect(removeChip(segs, c.id)).toEqual([{ kind: 'text', text: 'ab' }]);
  });
});

describe('names and references', () => {
  it('builds safe variable names', () => {
    expect(variableName('Customer name')).toBe('customer_name');
    expect(variableName('2nd item')).toBe('v_2nd_item');
    expect(variableName('', 'count')).toBe('count_data');
    expect(variableName('Items', 'joined')).toBe('joined_items');
    expect(modeOfName('table_order')).toBe('summary');
    expect(modeOfName('order')).toBeUndefined();
  });

  it('knows the reference grammar', () => {
    for (const ok of ['input.a', 'trigger.x', 'n_1', 'n_1.items[0].sku', 'foreach.item.name', 'foreach.index']) expect(isValidRef(ok)).toBe(true);
    for (const bad of ['', 'input.', 'a-b.c', 'input[x]', 'input..a', 'a b', 'input.a.']) expect(isValidRef(bad)).toBe(false);
  });
});
