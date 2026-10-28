import { describe, it, expect } from 'vitest';
import { summarizeDocPayload } from './flowRunDoc';

const doc = {
  doctype: 'ToDo', name: 'abc123', owner: 'Administrator', modified_by: 'Administrator', docstatus: 0, idx: 0,
  creation: '2026-10-28 09:00:00', modified: '2026-10-28 09:00:00',
  description: 'Call the supplier', status: 'Open', priority: 'Medium', date: '', allocated_to: null, items: [{ a: 1 }],
};

describe('summarizeDocPayload', () => {
  it('shows the document and its entered fields, without internal keys', () => {
    const s = summarizeDocPayload(doc, 'after_insert');
    expect(s).toMatchObject({ doctype: 'ToDo', name: 'abc123', event: 'Created' });
    expect(s?.fields.map((f) => f.key)).toEqual(['description', 'status', 'priority']);
    expect(s?.fields[0]).toEqual({ key: 'description', label: 'Description', value: 'Call the supplier' });
    const keys = s?.fields.map((f) => f.key) ?? [];
    for (const internal of ['owner', 'modified_by', 'docstatus', 'idx', 'doctype']) expect(keys).not.toContain(internal);
    expect(s?.hidden).toBe(3); // empty date, null allocated_to, items table
  });
  it('is null for anything that is not a document', () => {
    expect(summarizeDocPayload({ text: 'hi' })).toBeNull();
    expect(summarizeDocPayload(null)).toBeNull();
    expect(summarizeDocPayload([1])).toBeNull();
  });
  it('leaves the event out when it is unknown and caps long values and field counts', () => {
    const s = summarizeDocPayload({ doctype: 'X', name: 'n', a: 'x'.repeat(300), ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`f${i}`, i + 1])) }, null, 3);
    expect(s?.event).toBeNull();
    expect(s?.fields).toHaveLength(3);
    expect(s?.fields[0].value.length).toBe(120);
    expect(s?.hidden).toBe(10);
  });
});
