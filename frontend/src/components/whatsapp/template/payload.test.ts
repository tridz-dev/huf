import { describe, expect, it } from 'vitest';
import type { TemplateDetail } from '@/services/whatsappApi';
import { emptyButton, emptyDraft } from './draft';
import { fromTemplateDetail, toCreatePayload, toEditPayload } from './payload';
import { validateDraft } from './rules';

describe('toCreatePayload', () => {
  it('builds a minimal positional payload', () => {
    const d = { ...emptyDraft('MARKETING'), name: 'a_b', body: 'Hello' };
    expect(toCreatePayload(d)).toEqual({
      template_name: 'a_b',
      category: 'MARKETING',
      language_code: 'en_US',
      template: 'Hello',
      parameter_format: 'POSITIONAL',
    });
  });

  it('comma-joins numbered samples in order', () => {
    const d = { ...emptyDraft(), name: 'a', body: 'a {{2}} b {{1}} c', samples: { '1': 'x', '2': 'y', '9': 'stale' } };
    expect(toCreatePayload(d).sample_values).toBe('y,x');
  });

  it('sends named samples keyed by variable', () => {
    const d = { ...emptyDraft(), name: 'a', variableType: 'name' as const, body: 'a {{who}} b', samples: { who: ' Ann ' } };
    const p = toCreatePayload(d);
    expect(p.parameter_format).toBe('NAMED');
    expect(p.named_samples).toEqual({ who: 'Ann' });
    expect(p.sample_values).toBeUndefined();
  });

  it('maps headers', () => {
    const base = { ...emptyDraft(), name: 'a', body: 'Hello' };
    const text = toCreatePayload({ ...base, body: 'Hello', header: { type: 'text', text: 'Hi {{1}}', mediaSample: '' }, samples: { 'header.1': 'Ann' } });
    expect(text).toMatchObject({ header_type: 'TEXT', header: 'Hi {{1}}', sample: 'Ann' });
    const video = toCreatePayload({ ...base, header: { type: 'video', text: 'ignored', mediaSample: ' https://e.com/v.mp4 ' } });
    expect(video).toMatchObject({ header_type: 'VIDEO', sample: 'https://e.com/v.mp4' });
    expect(video.header).toBeUndefined();
    const loc = toCreatePayload({ ...base, header: { type: 'location', text: '', mediaSample: 'x' } });
    expect(loc.header_type).toBe('LOCATION');
    expect(loc.sample).toBeUndefined();
    expect(toCreatePayload(base).header_type).toBeUndefined();
  });

  it('maps buttons and ttl', () => {
    const buttons = [
      { ...emptyButton('QUICK_REPLY', '1'), text: 'Yes' },
      { ...emptyButton('URL', '2'), text: 'Site', url: 'https://e.com/{{1}}', urlExample: 'https://e.com/5' },
      { ...emptyButton('URL', '3'), text: 'Plain', url: 'https://e.com', urlExample: 'leftover' },
      { ...emptyButton('PHONE_NUMBER', '4'), text: 'Call', phoneNumber: '+1 (555) 123-4567' },
      { ...emptyButton('COPY_CODE', '5'), text: 'Copy', codeExample: 'SAVE20' },
    ];
    const p = toCreatePayload({ ...emptyDraft('UTILITY'), name: 'a', body: 'Hello', buttons, ttl: 600 });
    expect(p.buttons).toEqual([
      { type: 'QUICK_REPLY', text: 'Yes' },
      { type: 'URL', text: 'Site', url: 'https://e.com/{{1}}', example: 'https://e.com/5' },
      { type: 'URL', text: 'Plain', url: 'https://e.com' },
      { type: 'PHONE_NUMBER', text: 'Call', phone_number: '+15551234567' },
      { type: 'COPY_CODE', text: 'Copy', example: 'SAVE20' },
    ]);
    expect(p.ttl_seconds).toBe(600);
    expect(toCreatePayload({ ...emptyDraft('MARKETING'), name: 'a', body: 'Hello', ttl: 600 }).ttl_seconds).toBeUndefined();
  });

  it('drops name and language for edits and sends cleared parts explicitly', () => {
    const edit = toEditPayload({ ...emptyDraft(), name: 'a', body: 'Hello' });
    expect('template_name' in edit).toBe(false);
    expect('language_code' in edit).toBe(false);
    expect(edit).toMatchObject({ header_type: '', footer: '', buttons: [], template: 'Hello' });
  });
});

const detail = (over: Partial<TemplateDetail['components']> = {}, top: Partial<TemplateDetail> = {}): TemplateDetail =>
  ({
    name: 'x',
    template_id: '1',
    template_name: 'order_update',
    language_code: 'pt_BR',
    category: 'UTILITY',
    components: {
      header: { type: 'TEXT', text: 'Hi {{1}}', sample: 'Ann' },
      body: { text: 'Order {{1}} is on the way, {{2}}', sample_values: ['4821', 'Bo'] },
      footer: { text: 'Thanks' },
      buttons: [
        { type: 'URL', text: 'Track', url: 'https://e.com/{{1}}', example: 'https://e.com/9' },
        { type: 'PHONE_NUMBER', text: 'Call', phone_number: '+15551234567' },
      ],
      ...over,
    },
    ...top,
  }) as TemplateDetail;

describe('fromTemplateDetail', () => {
  it('prefills a numbered template and round-trips to a valid payload', () => {
    const d = fromTemplateDetail(detail());
    expect(d).toMatchObject({ name: 'order_update', language: 'pt_BR', category: 'UTILITY', variableType: 'number', footer: 'Thanks' });
    expect(d.samples).toEqual({ '1': '4821', '2': 'Bo', 'header.1': 'Ann' });
    expect(d.buttons.map((b) => b.type)).toEqual(['URL', 'PHONE_NUMBER']);
    expect(d.buttons[0].urlExample).toBe('https://e.com/9');
    expect(validateDraft(d)).toEqual({ body: expect.stringMatching(/end/) }); // fixture body ends with a variable
    expect(toCreatePayload(d).sample_values).toBe('4821,Bo');
  });

  it('detects named variables, media headers, copy code and ttl', () => {
    const d = fromTemplateDetail(
      detail(
        {
          header: { type: 'VIDEO' as never, text: '', sample: 'https://e.com/v.mp4' },
          body: { text: 'Hi {{first_name}}, thanks', sample_values: ['Ann'] },
          footer: null,
          buttons: [{ type: 'COPY_CODE' as never, text: 'Copy', example: 'SAVE20' }],
        },
        { ttl_seconds: 900 },
      ),
    );
    expect(d.variableType).toBe('name');
    expect(d.samples).toEqual({ first_name: 'Ann' });
    expect(d.header).toEqual({ type: 'video', text: '', mediaSample: 'https://e.com/v.mp4' });
    expect(d.buttons[0]).toMatchObject({ type: 'COPY_CODE', codeExample: 'SAVE20' });
    expect(d.ttl).toBe(900);
    expect(validateDraft(d)).toEqual({});
  });

  it('keeps marketing ttl empty and skips unknown button types', () => {
    const d = fromTemplateDetail(
      detail({ buttons: [{ type: 'OTP' as never, text: 'x' }] }, { category: 'MARKETING', ttl_seconds: 60 }),
    );
    expect(d.ttl).toBeNull();
    expect(d.buttons).toEqual([]);
  });
});
