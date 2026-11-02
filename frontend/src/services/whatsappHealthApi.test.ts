import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import { checkToken, checklistProgress, getSetupStatus, healthLabel, type ChecklistItem } from './whatsappHealthApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);

beforeEach(() => vi.clearAllMocks());

describe('getSetupStatus', () => {
  it('asks for one gateway and unwraps the message envelope', async () => {
    get.mockResolvedValue({ message: { success: true, connector_available: true } } as never);
    const res = await getSetupStatus('GW-1');
    expect(res).toEqual({ ok: true, data: { success: true, connector_available: true } });
    expect(get).toHaveBeenCalledWith('huf.ai.whatsapp.management.get_setup_status', { gateway_name: 'GW-1' });
  });

  it('asks for the site summary when no gateway is given', async () => {
    get.mockResolvedValue({ message: { success: true } } as never);
    await getSetupStatus();
    expect(get).toHaveBeenCalledWith('huf.ai.whatsapp.management.get_setup_status', {});
  });

  it('accepts an unwrapped body', async () => {
    get.mockResolvedValue({ success: true, connector_available: false } as never);
    expect(await getSetupStatus('GW-1')).toEqual({ ok: true, data: { success: true, connector_available: false } });
  });

  it('turns success:false into an error, preferring the message', async () => {
    get.mockResolvedValue({ message: { success: false, error: 'not_found', message: 'No such gateway' } } as never);
    expect(await getSetupStatus('GW-9')).toEqual({ ok: false, error: 'No such gateway' });
    get.mockResolvedValue({ message: { success: false, error: 'bridge_unavailable' } } as never);
    expect(await getSetupStatus('GW-9')).toEqual({ ok: false, error: 'bridge_unavailable' });
    get.mockResolvedValue({ message: { success: false } } as never);
    expect(await getSetupStatus('GW-9')).toEqual({ ok: false, error: 'Request failed' });
  });

  it('turns thrown errors into an error result', async () => {
    get.mockRejectedValue(new Error('network down'));
    const res = await getSetupStatus('GW-1');
    expect(res.ok).toBe(false);
  });
});

describe('checkToken', () => {
  it('posts the gateway name', async () => {
    post.mockResolvedValue({ message: { success: true, valid: true } } as never);
    expect(await checkToken('GW-1')).toEqual({ ok: true, data: { success: true, valid: true } });
    expect(post).toHaveBeenCalledWith('huf.ai.whatsapp.management.check_token', { gateway_name: 'GW-1' });
  });

  it('reports a rejected check as an error', async () => {
    post.mockResolvedValue({ message: { success: false, error: 'rate_limited', message: 'Try again in a minute' } } as never);
    expect(await checkToken('GW-1')).toEqual({ ok: false, error: 'Try again in a minute' });
  });

  it('turns thrown errors into an error result', async () => {
    post.mockRejectedValue(new Error('boom'));
    expect((await checkToken('GW-1')).ok).toBe(false);
  });
});

describe('helpers', () => {
  it('labels every health state and passes unknown ones through', () => {
    expect(healthLabel('healthy')).toBe('Working');
    expect(healthLabel('degraded')).toBe('Needs attention');
    expect(healthLabel('blocked')).toBe('Blocked');
    expect(healthLabel('not_set_up')).toBe('Not set up yet');
    expect(healthLabel('disabled')).toBe('Turned off');
    expect(healthLabel('weird' as never)).toBe('weird');
  });

  it('counts done checklist items', () => {
    const items: ChecklistItem[] = [
      { code: 'meta_app', state: 'done' },
      { code: 'credentials', state: 'done' },
      { code: 'webhook', state: 'blocked' },
      { code: 'enabled', state: 'todo' },
    ];
    expect(checklistProgress(items)).toEqual({ done: 2, total: 4 });
    expect(checklistProgress([])).toEqual({ done: 0, total: 0 });
  });
});
