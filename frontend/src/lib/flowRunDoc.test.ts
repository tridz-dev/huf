import { describe, it, expect } from 'vitest';
import { htmlToText, summarizeDocPayload } from './flowRunDoc';

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

describe('rich text values', () => {
  it('turns HTML into plain text with entities decoded', () => {
    expect(htmlToText('<div class="ql-editor read-mode"><p>Call &amp; confirm</p><p>Second&nbsp;line<br>third</p></div>')).toBe('Call & confirm\nSecond line\nthird');
    expect(htmlToText('1 < 2 and plain')).toBe('1 < 2 and plain');
  });
  it('shows the summary without markup and keeps the full text for Show more', () => {
    const long = `<div><p>${'word '.repeat(60)}</p></div>`;
    const s = summarizeDocPayload({ doctype: 'ToDo', name: 'a', description: long });
    const f = s?.fields[0];
    expect(f?.value).not.toContain('<');
    expect(f?.value.length).toBe(120);
    expect(f?.full).toBe(`${'word '.repeat(60)}`.trim());
    const short = summarizeDocPayload({ doctype: 'ToDo', name: 'a', description: '<p>Hi</p>' });
    expect(short?.fields[0]).toEqual({ key: 'description', label: 'Description', value: 'Hi' });
  });
});
