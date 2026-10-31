import { describe, it, expect } from 'vitest';
import {
  friendlyDate, friendlyRunTitle, humanize, humanizeMessageText, humanizeSentence, labelFor, nodeText, placeTriggerInput, sameData, startedByWords,
  type HumanNode,
} from './humanize';

const rowsOf = (n: HumanNode) => (n.kind === 'rows' ? n.rows : []);

describe('labelFor', () => {
  it('turns keys into Title Case labels and keeps acronyms', () => {
    expect(labelFor('customer_name')).toBe('Customer Name');
    expect(labelFor('orderId')).toBe('Order ID');
    expect(labelFor('shipping-url')).toBe('Shipping URL');
    expect(labelFor('sku')).toBe('SKU');
  });
  it('prefers a schema title', () => {
    expect(labelFor('amt', 'Order amount')).toBe('Order amount');
  });
});

describe('humanize objects', () => {
  it('shows labelled rows, hides nulls, empties and bookkeeping keys', () => {
    const n = humanize({ customer_name: 'Ada', note: null, empty: '', tags: [], owner: 'x@y.z', docstatus: 0, _trigger: { a: 1 }, paid: true });
    expect(rowsOf(n).map((r) => [r.label, nodeText(r.node)])).toEqual([['Customer Name', 'Ada'], ['Paid', 'Yes']]);
  });
  it('shows nested objects as nested rows', () => {
    const n = humanize({ customer: { first_name: 'Ada', city: 'London' } });
    const inner = rowsOf(n)[0].node;
    expect(rowsOf(inner).map((r) => r.label)).toEqual(['First Name', 'City']);
    expect(rowsOf(inner)[0].path).toBe('customer.first_name');
  });
  it('uses schema labels by key or path', () => {
    const n = humanize({ amt: 5, who: { n: 'x' } }, { labels: { amt: 'Order amount', 'who.n': 'Full name' } });
    expect(rowsOf(n)[0].label).toBe('Order amount');
    expect(rowsOf(rowsOf(n)[1].node)[0].label).toBe('Full name');
  });
  it('is empty when nothing is worth showing', () => {
    expect(humanize({ a: null, b: '' }).kind).toBe('empty');
    expect(humanize(null).kind).toBe('empty');
    expect(humanize({}).kind).toBe('empty');
  });
  it('resolves step ids to step titles, even unknown ones', () => {
    const n = humanize({ next: 'node_1793273127004', other: 'node_1793273127999', plain: 'approved' }, { names: { node_1793273127004: 'Approved' } });
    expect(rowsOf(n).map((r) => nodeText(r.node))).toEqual(['Approved', 'Another step', 'approved']);
  });
  it('parses a JSON object that was stored as text', () => {
    const n = humanize('{"amount": 42, "note": null}');
    expect(rowsOf(n).map((r) => [r.label, nodeText(r.node)])).toEqual([['Amount', '42']]);
  });
});

describe('scalars', () => {
  it('formats booleans, numbers and dates', () => {
    const rows = rowsOf(humanize({ ok: false, count: 12000, order_id: 123456, year: 2026, created_at: '2026-10-29T17:15:54Z', due: '2026-11-02' }));
    const by = Object.fromEntries(rows.map((r) => [r.key, nodeText(r.node)]));
    expect(by.ok).toBe('No');
    expect(by.count).toMatch(/12.000|12,000/);
    expect(by.order_id).toBe('123456');
    expect(by.year).toBe('2026');
    expect(by.created_at).not.toMatch(/T17|Z$|2026-10-29/);
    expect(by.created_at).toMatch(/Oct 29, 2026/);
    expect(by.due).toMatch(/Nov 2, 2026/);
  });
  it('friendlyDate leaves non-dates alone', () => {
    expect(friendlyDate('hello')).toBe('hello');
  });
  it('collapses long text, keeps the full text, strips HTML', () => {
    const long = 'word '.repeat(60).trim();
    const n = humanize({ body: long, short: '<p>Hi</p>' });
    const [body, short] = rowsOf(n);
    expect(body.node.kind === 'text' && body.node.long).toBe(true);
    expect(body.node.kind === 'text' && body.node.preview.length).toBeLessThanOrEqual(121);
    expect(body.node.kind === 'text' && body.node.text).toBe(long);
    expect(nodeText(short.node)).toBe('Hi');
  });
  it('treats text over three lines as long', () => {
    const n = humanize('a\nb\nc\nd');
    expect(n.kind === 'text' && n.long).toBe(true);
  });
});

describe('lists', () => {
  it('counts items and summarizes scalar lists', () => {
    const n = humanize({ names: ['Ada', 'Grace', 'Linus', 'Ken'] });
    const list = rowsOf(n)[0].node;
    expect(list.kind).toBe('list');
    if (list.kind === 'list') {
      expect(list.count).toBe(4);
      expect(list.summary).toBe('Ada, Grace, Linus and 1 more');
    }
  });
  it('shows object items as cards with a title and key facts', () => {
    const n = humanize({ lines: [{ name: 'Widget', qty: 2, price: 5 }, { name: 'Gadget', qty: 1, price: 9 }] });
    const list = rowsOf(n)[0].node;
    if (list.kind !== 'list') throw new Error('expected list');
    expect(list.items.map((i) => i.title)).toEqual(['Widget', 'Gadget']);
    expect(list.items[0].facts).toBe('Price: 5, Qty: 2');
    expect(list.items[0].body.kind).toBe('rows');
    expect(list.items[0].body.kind === 'rows' && list.items[0].body.rows.map((r) => r.key)).toEqual(['qty', 'price']);
  });
  it('falls back to Item N and ignores empty entries', () => {
    const list = humanize([{ qty: 2 }, null, { qty: 3 }]);
    if (list.kind !== 'list') throw new Error('expected list');
    expect(list.count).toBe(2);
    expect(list.items.map((i) => i.title)).toEqual(['Item 1', 'Item 3']);
  });
  it('humanizeSentence reads "N items"', () => {
    expect(humanizeSentence([1, 2, 3])).toBe('3 items: 1, 2, 3');
    expect(humanizeSentence(['solo'])).toBe('1 item: solo');
  });
});

describe('humanizeSentence', () => {
  it('puts the telling facts first and counts the rest', () => {
    const s = humanizeSentence({ zeta: 'z', amount: 450, customer: 'Ada Lovelace', a: 1, b: 2, c: 3 });
    expect(s).toBe('Customer: Ada Lovelace, Amount: 450, Zeta: z, A: 1 and 2 more');
  });
});

describe('humanizeMessageText', () => {
  it('replaces embedded JSON with a readable form', () => {
    const text = 'Approve this order: {"amount":42,"customer":{"name":"Ada"},"note":null,"items":[1,2,3]}';
    const out = humanizeMessageText(text);
    expect(out).not.toMatch(/[{}"]/);
    expect(out).toMatch(/^Approve this order: /);
    expect(out).toContain('Amount: 42');
    expect(out).toContain('Items: 3 items');
    expect(out).toContain('Customer: Ada');
  });
  it('handles a python style dict and a list', () => {
    expect(humanizeMessageText("Check {'amount': 5, 'ok': True}")).toBe('Check Amount: 5, Ok: Yes');
    expect(humanizeMessageText('Pick from ["a","b"]')).toBe('Pick from 2 items: a, b');
  });
  it('leaves normal text and unmatched braces alone', () => {
    expect(humanizeMessageText('Ship order {input.id} today?')).toBe('Ship order {input.id} today?');
    expect(humanizeMessageText('Please approve')).toBe('Please approve');
    expect(humanizeMessageText('open { brace')).toBe('open { brace');
  });
  it('makes ISO timestamps friendly', () => {
    const out = humanizeMessageText('Needed by 2026-10-29T17:15:54Z please.');
    expect(out).not.toContain('2026-10-29T');
    expect(out).toContain('Oct 29, 2026');
  });
});

describe('trigger input placement', () => {
  const steps = [{ id: 's1', output: { amount: 7 } }, { id: 's2', output: 'x' }];
  it('merges an input the first step repeats', () => {
    expect(placeTriggerInput({ amount: 7 }, steps)).toEqual({ mode: 'merged', stepId: 's1' });
    expect(placeTriggerInput({ amount: 7, note: null }, steps)).toEqual({ mode: 'merged', stepId: 's1' });
  });
  it('merges into the first step when it has no output of its own', () => {
    expect(placeTriggerInput({ amount: 7 }, [{ id: 's1', output: undefined }])).toEqual({ mode: 'merged', stepId: 's1' });
  });
  it('keeps a separate block when the data differs, and none for no data', () => {
    expect(placeTriggerInput({ amount: 7 }, [{ id: 's1', output: { other: 1 } }])).toEqual({ mode: 'separate' });
    expect(placeTriggerInput({}, steps)).toEqual({ mode: 'none' });
    expect(placeTriggerInput({ a: null }, steps)).toEqual({ mode: 'none' });
  });
  it('sameData ignores key order and empties', () => {
    expect(sameData({ a: 1, b: { c: 2 } }, { b: { c: 2 }, a: 1, z: null })).toBe(true);
    expect(sameData({ a: 1 }, { a: 2 })).toBe(false);
  });
});

describe('run title', () => {
  it('says who started it in words', () => {
    expect(startedByWords({ triggerType: 'Manual', owner: 'a@x.com', currentUser: 'a@x.com' })).toBe('you');
    expect(startedByWords({ triggerType: 'Manual', owner: 'a@x.com', ownerName: 'Ada', currentUser: 'b@x.com' })).toBe('Ada');
    expect(startedByWords({ triggerType: 'Webhook', owner: 'Administrator' })).toBe('a webhook');
    expect(startedByWords({ triggerType: 'Schedule' })).toBe('a schedule');
    expect(startedByWords({ triggerType: 'Doc Event' })).toBe('a data change');
  });
  it('builds "Run #N · started by you · 2 mins ago" and never an id', () => {
    expect(friendlyRunTitle({ runNumber: 12, startedBy: 'you', ago: '2 mins ago' })).toBe('Run #12 · started by you · 2 mins ago');
    expect(friendlyRunTitle({ runNumber: 3, ago: 'Just now' })).toBe('Run #3 · just now');
    expect(friendlyRunTitle({})).toBe('Run');
  });
});

describe('chat message starter', () => {
  it('names the sender first and masks the number', () => {
    expect(startedByWords({ triggerType: 'Gateway', input: { provider: 'WhatsApp', display_name: 'Asha', sender_id: '919876543210' } })).toBe('a WhatsApp message from Asha (••••3210)');
    expect(startedByWords({ triggerType: 'Gateway', input: { provider: 'Telegram', sender_id: '12345678' } })).toBe('a Telegram message from ••••5678');
    expect(startedByWords({ triggerType: 'Gateway' })).toBe('a chat message');
  });
});
