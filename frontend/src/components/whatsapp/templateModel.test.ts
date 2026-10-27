// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { WhatsAppTemplate } from '@/services/whatsappApi';
import {
  ALL_OPTION, buildPreviewModel, draftStatusInfo, fillVariables, filterTemplates, insertVariable, nextVariableNumber,
  parseServerTime, qualityInfo, rejectionCopy, rowToPreviewInput, statusInfo, statusToastText, timeAgo,
} from './templateModel';

describe('variables', () => {
  it('fills samples and keeps blanks visible', () => {
    expect(fillVariables('Hi {{1}}, order {{ 2 }}', ['Ann', ''])).toBe('Hi Ann, order {{ 2 }}');
  });
  it('numbers and inserts the next variable at the caret', () => {
    expect(nextVariableNumber('Hi {{1}} {{3}}')).toBe(4);
    expect(insertVariable('Hello ', 6)).toEqual({ body: 'Hello {{1}}', caret: 11, number: 1 });
    expect(insertVariable('Hi {{1}}!', 3).body).toBe('Hi {{2}}{{1}}!');
    expect(insertVariable('ab', null).body).toBe('ab{{1}}');
  });
});

describe('status and reason copy', () => {
  it('maps statuses and quality', () => {
    expect(statusInfo('IN_APPEAL')).toMatchObject({ label: 'In appeal', tone: 'warning' });
    expect(statusInfo('approved').tone).toBe('success');
    expect(statusInfo('SOMETHING')).toMatchObject({ tone: 'neutral' });
    expect(qualityInfo('RED')?.tone).toBe('danger');
    expect(qualityInfo('UNKNOWN')).toBeNull();
  });
  it('explains every rejection reason in plain words', () => {
    for (const r of ['ABUSIVE_CONTENT', 'INCORRECT_CATEGORY', 'INVALID_FORMAT', 'PROMOTIONAL', 'SCAM', 'TAG_CONTENT_MISMATCH']) {
      const copy = rejectionCopy(r);
      expect(copy?.reason).toBeTruthy();
      expect(copy?.reason).not.toMatch(/[A-Z]_[A-Z]/);
    }
    expect(rejectionCopy('NONE')).toBeNull();
    expect(rejectionCopy('NEW_THING')?.advice).toBeTruthy();
  });
  it('builds toast text', () => {
    expect(statusToastText('promo', 'APPROVED')).toEqual({ text: 'Template promo approved', tone: 'success' });
    expect(statusToastText('promo', 'REJECTED').tone).toBe('error');
    expect(statusToastText('promo', 'PENDING').tone).toBe('info');
    expect(draftStatusInfo('Pending Review').label).toBe('Awaiting approval');
  });
});

describe('preview model', () => {
  it('substitutes samples and shapes header, footer and buttons', () => {
    const m = buildPreviewModel({
      headerType: 'TEXT', header: 'Order {{1}}', headerSample: '42', body: 'Hi {{1}}', samples: ['Ann'], footer: ' Bye ',
      buttons: [{ type: 'URL', text: 'Track', url: 'https://x' }, { type: 'QUICK_REPLY', text: ' ' }],
    });
    expect(m).toEqual({
      header: { kind: 'text', text: 'Order 42' }, body: 'Hi Ann', footer: 'Bye',
      buttons: [{ type: 'URL', text: 'Track' }, { type: 'QUICK_REPLY', text: 'Button' }],
    });
  });
  it('uses a media placeholder for image headers', () => {
    expect(buildPreviewModel({ headerType: 'IMAGE', headerSample: 'https://x/y.png', body: 'x', samples: [] }).header)
      .toEqual({ kind: 'media', media: 'IMAGE', url: 'https://x/y.png' });
  });
  it('converts list rows and draft payloads', () => {
    const row = {
      name: 'n', template_name: 'n', template: 'Hi {{1}}', sample_values: 'Ann,Bob', header_type: 'TEXT', header: 'H',
      buttons: [{ button_type: 'Visit Website', button_label: 'Go' }],
    } as WhatsAppTemplate;
    const input = rowToPreviewInput(row);
    expect(input.samples).toEqual(['Ann', 'Bob']);
    expect(input.buttons).toEqual([{ type: 'URL', text: 'Go' }]);
  });
});

describe('filters and time', () => {
  const rows = [
    { name: 'a', template_name: 'order_update', status: 'APPROVED', category: 'UTILITY', language_code: 'en_US', template: 'shipped' },
    { name: 'b', template_name: 'promo', status: 'REJECTED', category: 'MARKETING', language_code: 'fr', template: 'sale' },
  ] as WhatsAppTemplate[];
  const none = { search: '', status: ALL_OPTION, category: ALL_OPTION, language: ALL_OPTION };
  it('filters by search, status, category and language', () => {
    expect(filterTemplates(rows, none)).toHaveLength(2);
    expect(filterTemplates(rows, { ...none, search: 'SALE' }).map((r) => r.name)).toEqual(['b']);
    expect(filterTemplates(rows, { ...none, status: 'APPROVED' }).map((r) => r.name)).toEqual(['a']);
    expect(filterTemplates(rows, { ...none, category: 'MARKETING' }).map((r) => r.name)).toEqual(['b']);
    expect(filterTemplates(rows, { ...none, language: 'fr' }).map((r) => r.name)).toEqual(['b']);
  });
  it('parses server times and words the age', () => {
    expect(parseServerTime('nope')).toBeNull();
    const now = new Date('2026-10-14T12:00:00');
    expect(timeAgo('2026-10-14 11:59:30', now)).toBe('just now');
    expect(timeAgo('2026-10-14 11:30:00', now)).toBe('30 min ago');
    expect(timeAgo('2026-10-14T09:00:00', now)).toBe('3 h ago');
    expect(timeAgo('2026-10-12 12:00:00', now)).toBe('2 d ago');
  });
});
