// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('@/lib/frappe-sdk', () => ({ call: { post, get }, file: {} }));

import {
  buildEditPayload,
  buildTemplatePayload,
  createTemplate,
  createTemplateDraft,
  listMessageLog,
  listMessageLogFilters,
  listTemplateDrafts,
  listTemplates,
  sendTemplateMessage,
  syncTemplates,
  templateNameProblem,
  errorText,
  extractPlaceholders,
  isBridgeUnavailable,
  unwrapResult,
  validateMediaSend,
  validateTemplateForm,
} from './whatsappApi';

describe('whatsappApi helpers', () => {
  it('extracts ordered unique placeholders', () => {
    expect(extractPlaceholders('Hi {{1}}, order {{2}} {{1}}')).toEqual([1, 2]);
    expect(extractPlaceholders('none')).toEqual([]);
  });

  it('validates template forms', () => {
    const ok = { name: 'order_update', language: 'en_US', body: 'Hi {{1}}, welcome', samples: ['Ann'] };
    expect(validateTemplateForm(ok)).toBeNull();
    expect(validateTemplateForm({ ...ok, name: 'Bad Name' })).toMatch(/lowercase/);
    expect(validateTemplateForm({ ...ok, body: 'Hi {{2}}' })).toMatch(/Placeholders/);
    expect(validateTemplateForm({ ...ok, samples: [''] })).toMatch(/sample/);
    expect(validateTemplateForm({ ...ok, body: ' ' })).toMatch(/Body/);
    expect(validateTemplateForm({ ...ok, body: '{{1}} is here' })).toMatch(/start with a variable/);
    expect(validateTemplateForm({ ...ok, body: 'Hi {{1}}' })).toMatch(/end with a variable/);
    expect(templateNameProblem('Bad Name')).toMatch(/lowercase/);
    expect(templateNameProblem('order_update')).toBeNull();
  });

  it('builds payload, dropping empty optionals', () => {
    const p = buildTemplatePayload({
      name: 'a_b', category: 'UTILITY', language: 'en_US', body: 'Hi {{1}}, welcome', header: ' ', footer: 'Bye', samples: ['Ann', 'x'],
    });
    expect(p).toEqual({
      template_name: 'a_b', category: 'UTILITY', language_code: 'en_US', template: 'Hi {{1}}, welcome', footer: 'Bye', sample_values: 'Ann',
    });
  });

  it('unwraps results and detects bridge_unavailable', () => {
    const res = unwrapResult({ message: { success: false, error: 'bridge_unavailable' } });
    expect(isBridgeUnavailable(res)).toBe(true);
    expect(unwrapResult({ message: { success: true, templates: [] } }).success).toBe(true);
    expect(unwrapResult(null).success).toBe(false);
    if (!res.success) expect(errorText(res)).toMatch(/frappe_whatsapp/);
  });

  describe('rich templates', () => {
    const base = { name: 'order_update', language: 'en_US', body: 'Hi {{1}}, welcome', samples: ['Ann'] };

    it('validates headers against Meta limits', () => {
      expect(validateTemplateForm({ ...base, headerType: 'TEXT', header: 'Order {{1}}', headerSample: 'A-1' })).toBeNull();
      expect(validateTemplateForm({ ...base, headerType: 'TEXT', header: 'Order {{1}}' })).toMatch(/example/);
      expect(validateTemplateForm({ ...base, headerType: 'TEXT', header: 'x'.repeat(61) })).toMatch(/60/);
      expect(validateTemplateForm({ ...base, headerType: 'TEXT', header: '{{1}} {{2}}' })).toMatch(/one variable/);
      expect(validateTemplateForm({ ...base, headerType: 'IMAGE', headerSample: 'nope' })).toMatch(/link/);
      expect(validateTemplateForm({ ...base, headerType: 'DOCUMENT', headerSample: 'https://x.example/a.pdf' })).toBeNull();
    });

    it('validates footer, body and button limits', () => {
      expect(validateTemplateForm({ ...base, footer: 'f'.repeat(61) })).toMatch(/Footer/);
      expect(validateTemplateForm({ ...base, footer: 'hi {{1}}' })).toMatch(/footer/);
      expect(validateTemplateForm({ ...base, body: 'x'.repeat(1025), samples: [] })).toMatch(/1024/);
      const q = (n: number) => Array.from({ length: n }, (_, i) => ({ type: 'QUICK_REPLY' as const, text: `q${i}` }));
      expect(validateTemplateForm({ ...base, buttons: q(3) })).toBeNull();
      expect(validateTemplateForm({ ...base, buttons: q(4) })).toMatch(/quick-reply/);
      expect(validateTemplateForm({ ...base, buttons: [{ type: 'QUICK_REPLY', text: 'x'.repeat(26) }] })).toMatch(/25/);
      const urls = [1, 2, 3].map((i) => ({ type: 'URL' as const, text: `u${i}`, url: `https://x${i}.example` }));
      expect(validateTemplateForm({ ...base, buttons: urls })).toMatch(/link or phone/);
      expect(
        validateTemplateForm({ ...base, buttons: [{ type: 'URL', text: 'Track', url: 'https://x.example/{{1}}' }] }),
      ).toMatch(/example/);
      expect(
        validateTemplateForm({ ...base, buttons: [{ type: 'PHONE_NUMBER', text: 'Call', phone_number: 'abc' }] }),
      ).toMatch(/phone/);
    });

    it('builds a rich payload', () => {
      const p = buildTemplatePayload({
        ...base,
        category: 'UTILITY',
        headerType: 'TEXT',
        header: ' Order {{1}} ',
        headerSample: 'A-1',
        footer: 'Thanks',
        buttons: [
          { type: 'URL', text: 'Track', url: 'https://x.example/{{1}}', example: 'https://x.example/9' },
          { type: 'PHONE_NUMBER', text: 'Call', phone_number: '+15550001234' },
        ],
      });
      expect(p).toMatchObject({
        header_type: 'TEXT', header: 'Order {{1}}', sample: 'A-1', footer: 'Thanks', sample_values: 'Ann',
        buttons: [
          { type: 'URL', text: 'Track', url: 'https://x.example/{{1}}', example: 'https://x.example/9' },
          { type: 'PHONE_NUMBER', text: 'Call', phone_number: '+15550001234' },
        ],
      });
      const media = buildTemplatePayload({ ...base, category: 'UTILITY', headerType: 'IMAGE', headerSample: 'https://x.example/a.png' });
      expect(media).toMatchObject({ header_type: 'IMAGE', sample: 'https://x.example/a.png' });
      expect(media.header).toBeUndefined();
    });

    it('shows every field error from a structured validation failure', () => {
      const res = unwrapResult({
        message: {
          success: false, error: 'validation_failed', message: 'first',
          errors: [{ field: 'footer', code: 'too_long', message: 'Footer too long.' }, { field: 'body', code: 'required', message: 'Body is required.' }],
        },
      });
      if (!res.success) expect(errorText(res)).toBe('Footer too long. Body is required.');
      else throw new Error('expected failure');
    });
  });

  it('validates outbound media sends', () => {
    expect(validateMediaSend({ kind: 'image' })).toMatch(/file or paste/);
    expect(validateMediaSend({ kind: 'image', link: 'http://x.example/a.png' })).toMatch(/https/);
    expect(validateMediaSend({ kind: 'image', link: 'https://x.example/a.png', caption: 'hi' })).toBeNull();
    expect(validateMediaSend({ kind: 'audio', link: 'https://x.example/a.mp3', caption: 'no' })).toMatch(/caption/);
    expect(validateMediaSend({ kind: 'document', fileUrl: '/files/a.pdf' })).toBeNull();
  });

  it('builds an edit payload that clears removed parts and drops name/language', () => {
    const p = buildEditPayload({ name: 'a_b', category: 'UTILITY', language: 'en_US', body: 'Hi there', samples: [] });
    expect(p).toEqual({ category: 'UTILITY', template: 'Hi there', header_type: '', footer: '', buttons: [], sample_values: '' });
  });

  it('keeps an existing media header when editing without a new sample', () => {
    const f = { name: 'a_b', category: 'UTILITY' as const, language: 'en_US', body: 'Hi there', samples: [], headerType: 'IMAGE' as const, keepExistingMedia: true };
    expect(validateTemplateForm(f)).toBeNull();
    expect('header_type' in buildEditPayload(f)).toBe(false);
    expect(validateTemplateForm({ ...f, keepExistingMedia: false })).toMatch(/sample file/);
  });
});

describe('gateway-scoped calls', () => {
  beforeEach(() => {
    post.mockReset().mockResolvedValue({ message: { success: true } });
    get.mockReset().mockResolvedValue({ message: { success: true } });
  });

  it('always names the gateway for lists, so the server never lists across accounts', async () => {
    await listMessageLog('GW-A', { phone: '15551234567' });
    await listMessageLogFilters('GW-A');
    await listTemplates('GW-A', 'APPROVED');
    await listTemplateDrafts('GW-A');
    const args = get.mock.calls.map((c) => c[1] as Record<string, unknown>);
    expect(args.map((a) => a.gateway_name)).toEqual(['GW-A', 'GW-A', 'GW-A', 'GW-A']);
    for (const a of args) expect('account' in a).toBe(false);
  });

  it('manages templates for a gateway, not a caller-chosen account', async () => {
    await createTemplate('GW-A', { template_name: 'a_b', category: 'UTILITY', language_code: 'en_US', template: 'Hi' });
    await createTemplateDraft('GW-A', { template_name: 'a_b', category: 'UTILITY', language_code: 'en_US', template: 'Hi' });
    await syncTemplates('GW-A');
    for (const c of post.mock.calls) {
      expect((c[1] as Record<string, unknown>).gateway_name).toBe('GW-A');
      expect('account' in (c[1] as object)).toBe(false);
    }
  });

  it('sends templates from a gateway and no longer passes an account', async () => {
    await sendTemplateMessage({ gateway_name: 'GW-B', to: '15551234567', template_name: 'welcome', body_params: ['Ann'] });
    const [method, args] = post.mock.calls[0] as [string, Record<string, unknown>];
    expect(method).toBe('huf.ai.whatsapp_management.send_template_message');
    expect(args.gateway_name).toBe('GW-B');
    expect('account' in args).toBe(false);
    expect(args.body_params).toBe('["Ann"]');
  });

  it('explains the multi-gateway error codes', () => {
    expect(errorText({ success: false, error: 'gateway_required' })).toMatch(/gateway/i);
    expect(errorText({ success: false, error: 'template_name_taken_by_other_account' })).toMatch(/different name/);
  });
});
