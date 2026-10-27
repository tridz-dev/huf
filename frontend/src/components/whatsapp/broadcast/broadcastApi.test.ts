import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
vi.mock('@/lib/api', async (orig) => {
  const real = await orig<typeof import('@/lib/api')>();
  return {
    ...real,
    // same contract as the real client: unwrap the envelope, throw ApiError for a failure body
    apiCall: async (m: string, a: Record<string, unknown>, o?: { verb?: string }) => {
      const r = (o?.verb === 'GET' ? await call.get(m, a) : await call.post(m, a)) as { message: { success?: boolean; error?: string; message?: string } };
      if (r.message?.success === false) throw new real.ApiError({ code: r.message.error ?? 'error', message: r.message.message ?? 'Request failed.' });
      return r.message;
    },
  };
});
import { call } from '@/lib/frappe-sdk';
import { addBroadcastRecipients, attestBroadcastConsent, getBroadcastTemplateParams, cancelBroadcast, createBroadcast, getBroadcast, listBroadcastRecipients, adaptBroadcast, adaptPreview, adaptAddResult, listBroadcasts, pauseAllBroadcasts, pauseBroadcast, previewBroadcast, resumeBroadcast, startBroadcast } from './broadcastApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
const M = 'huf.ai.whatsapp.broadcast.api';
const R = 'huf.ai.whatsapp.broadcast.api_read';
beforeEach(() => { vi.clearAllMocks(); get.mockResolvedValue({ message: { success: true } }); post.mockResolvedValue({ message: { success: true } }); });

describe('broadcast service', () => {
  it('posts mutating calls to the snake_case methods', async () => {
    await createBroadcast({ gateway: 'G', template: 'T', title: 'x' });
    expect(post).toHaveBeenCalledWith(`${M}.create_broadcast`, expect.objectContaining({ gateway: 'G', template: 'T', title: 'x' }));
    await addBroadcastRecipients('B', { csvText: 'phone\n1' });
    expect(post).toHaveBeenCalledWith(`${M}.add_broadcast_recipients`, { broadcast: 'B', csv_text: 'phone\n1' });
    await attestBroadcastConsent('B', 'web form');
    expect(post).toHaveBeenCalledWith(`${M}.attest_broadcast_consent`, { broadcast: 'B', consent_source: 'web form' });
    await startBroadcast('B', 5);
    expect(post).toHaveBeenCalledWith(`${M}.start_broadcast`, { broadcast: 'B', confirm_count: '5' });
    await pauseBroadcast('B'); await resumeBroadcast('B'); await cancelBroadcast('B'); await pauseAllBroadcasts('G');
    expect(post).toHaveBeenCalledWith(`${M}.pause_broadcast`, { broadcast: 'B' });
    expect(post).toHaveBeenCalledWith(`${M}.resume_broadcast`, { broadcast: 'B' });
    expect(post).toHaveBeenCalledWith(`${M}.cancel_broadcast`, { broadcast: 'B' });
    expect(post).toHaveBeenCalledWith(`${M}.pause_all_broadcasts`, { gateway: 'G' });
  });
  it('gets read calls', async () => {
    get.mockResolvedValue({ message: { success: true, broadcast: { name: 'B' }, broadcasts: [], recipients: [], limits: {} } });
    await previewBroadcast('B'); await getBroadcast('B'); await listBroadcasts({ gateway: 'G' }); await listBroadcastRecipients('B', { status: 'failed' });
    expect(post).toHaveBeenCalledWith(`${M}.preview_broadcast`, { broadcast: 'B' });
    expect(get).toHaveBeenCalledWith(`${R}.get_broadcast`, { broadcast: 'B' });
    expect(get).toHaveBeenCalledWith(`${R}.list_broadcasts`, { gateway: 'G' });
    expect(get).toHaveBeenCalledWith(`${R}.list_broadcast_recipients`, { broadcast: 'B', status: 'failed' });
  });
  it('turns server errors into error results', async () => {
    post.mockResolvedValue({ message: { success: false, error: 'count_mismatch' } });
    const res = await startBroadcast('B', 1);
    expect(res.success).toBe(false);
  });
});

const view = {
  name: 'B1', title: 'T', status: 'Running', gateway: 'G', category: 'MARKETING', started_at: null,
  body_params: ['a'], counts: { total: 7, queued: 2, sending: 1, sent: 3, delivered: 1, read: 0, failed: 0, deferred: 0, unknown: 0, skipped: 0 },
};

describe('broadcast response adapters', () => {
  it('flattens nested counts and keeps doc fields', () => {
    const b = adaptBroadcast(view);
    expect(b).toMatchObject({ name: 'B1', status: 'Running', total: 7, queued: 2, sent: 3, body_params: ['a'] });
    expect((b as unknown as Record<string, unknown>).counts).toBeUndefined();
    expect(adaptBroadcast({ name: 'x' }).total).toBe(0);
  });
  it('list/get adapt real shapes', async () => {
    get.mockResolvedValueOnce({ message: { success: true, broadcasts: [view] } });
    const l = await listBroadcasts({ gateway: 'G' });
    expect(l.success && l.broadcasts[0].total).toBe(7);
    get.mockResolvedValueOnce({ message: { success: true, broadcast: view } });
    const g = await getBroadcast('B1');
    expect(g.success && g.broadcast.sent).toBe(3);
  });
  it('recipients come back under `recipients`', async () => {
    get.mockResolvedValueOnce({ message: { success: true, recipients: [{ name: 'r', recipient: '1', status: 'sent' }] } });
    const r = await listBroadcastRecipients('B1');
    expect(r.success && r.recipients).toHaveLength(1);
  });
  it('create returns the name string', async () => {
    post.mockResolvedValueOnce({ message: { success: true, broadcast: 'BC-1', status: 'Draft', category: 'MARKETING' } });
    const r = await createBroadcast({ gateway: 'G', template: 'T', title: 'x', body_params: ['a'] });
    expect(r.success && r.broadcast).toBe('BC-1');
    expect(post).toHaveBeenLastCalledWith(`${M}.create_broadcast`, expect.objectContaining({ body_params: '["a"]' }));
  });
  it('create passes send_via; adaptBroadcast defaults and keeps it', async () => {
    post.mockResolvedValueOnce({ message: { success: true, broadcast: 'BC-1', status: 'Draft' } });
    await createBroadcast({ gateway: 'G', template: 'T', title: 'x', send_via: 'marketing_messages' });
    expect(post).toHaveBeenLastCalledWith(`${M}.create_broadcast`, expect.objectContaining({ send_via: 'marketing_messages' }));
    expect(adaptBroadcast({ name: 'x' }).send_via).toBe('messages');
    expect(adaptBroadcast({ name: 'x', send_via: 'marketing_messages' }).send_via).toBe('marketing_messages');
  });
  it('adaptPreview pulls limits, queued and cost', () => {
    const p = adaptPreview({
      status: 'Draft', consent_attested: 1, confirm_required: true, queued: 4,
      limits: { recipients: 5, queued: 4, skipped: 1, category: 'MARKETING', template_status: 'APPROVED', within_limit: true, remaining_24h: 90, warnings: ['w'], blocking: ['b'] },
      cost: { currency: 'USD', total: null, by_country: {}, warnings: ['rate_unavailable:marketing:XX'] },
    });
    expect(p).toMatchObject({ recipients: 5, queued: 4, skipped: 1, within_limit: true, remaining_24h: 90, warnings: ['w'], blocking: ['b'], consent_attested: true });
    expect(p.cost?.warnings).toEqual(['rate_unavailable:marketing:XX']);
    expect(adaptPreview({}).blocking).toEqual([]);
  });
  it('previewBroadcast wraps the adapted preview', async () => {
    post.mockResolvedValueOnce({ message: { success: true, queued: 3, limits: { recipients: 3, blocking: [] }, cost: null } });
    const r = await previewBroadcast('B');
    expect(r.success && r.preview.queued).toBe(3);
  });
  it('adaptAddResult keeps skipped/invalid objects and tolerates strings', () => {
    expect(adaptAddResult({ added: 1, skipped: [{ recipient: '1', reason: 'duplicate' }], invalid: [{ recipient: 'x', reason: 'invalid_number' }, 'y'] }))
      .toEqual({ added: 1, skipped: [{ recipient: '1', reason: 'duplicate' }], invalid: [{ recipient: 'x', reason: 'invalid_number' }, { recipient: 'y' }], skippedTotal: 1, invalidTotal: 2 });
  });
  it('adaptAddResult prefers server totals over truncated lists', () => {
    const r = adaptAddResult({ added: 0, skipped: [{ recipient: '1', reason: 'duplicate' }], invalid: [], skipped_total: 700, invalid_total: 12 });
    expect([r.skippedTotal, r.invalidTotal, r.skipped.length]).toEqual([700, 12, 1]);
  });
  it('encodes recipients as a JSON string', async () => {
    post.mockResolvedValueOnce({ message: { success: true, added: 1, skipped: [], invalid: [] } });
    await addBroadcastRecipients('B', { recipients: [{ recipient: '1' }] });
    expect(post).toHaveBeenLastCalledWith(`${M}.add_broadcast_recipients`, { broadcast: 'B', recipients: '[{"recipient":"1"}]' });
  });
  it('getBroadcastTemplateParams gets and normalises', async () => {
    get.mockResolvedValueOnce({ message: { success: true, parameter_format: 'NAMED', body: [{ name: 'first_name' }], header: null } });
    const r = await getBroadcastTemplateParams('G', 'T');
    expect(get).toHaveBeenLastCalledWith(`${R}.get_broadcast_template_params`, { gateway: 'G', template: 'T' });
    expect(r.success && [r.parameter_format, r.body, r.buttons]).toEqual(['NAMED', [{ name: 'first_name' }], []]);
  });
});
