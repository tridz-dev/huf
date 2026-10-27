import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() }, file: { uploadFile: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import {
  addBroadcastRecipients, attestBroadcastConsent, cancelBroadcast, createBroadcast, getBroadcast, listBroadcastRecipients,
  listBroadcasts, pauseAllBroadcasts, pauseBroadcast, previewBroadcast, resumeBroadcast, startBroadcast,
} from './whatsappApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);
const M = 'huf.ai.whatsapp.management';
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
    await previewBroadcast('B'); await getBroadcast('B'); await listBroadcasts({ gateway: 'G' }); await listBroadcastRecipients('B', { status: 'failed' });
    expect(get).toHaveBeenCalledWith(`${M}.preview_broadcast`, { broadcast: 'B' });
    expect(get).toHaveBeenCalledWith(`${M}.get_broadcast`, { broadcast: 'B' });
    expect(get).toHaveBeenCalledWith(`${M}.list_broadcasts`, { gateway: 'G' });
    expect(get).toHaveBeenCalledWith(`${M}.list_broadcast_recipients`, { broadcast: 'B', status: 'failed' });
  });
  it('turns server errors into error results', async () => {
    post.mockResolvedValue({ message: { success: false, error: 'count_mismatch' } });
    const res = await startBroadcast('B', 1);
    expect(res.success).toBe(false);
  });
});
