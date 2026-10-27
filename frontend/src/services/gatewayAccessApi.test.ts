import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
import { call } from '@/lib/frappe-sdk';
import { approveGatewayPairing, listGatewayAccessEntries, revokeGatewayAccessEntry } from './gatewayAccessApi';

const get = vi.mocked(call.get);
const post = vi.mocked(call.post);

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('gatewayAccessApi', () => {
  it('lists the pending queue by default, scoped to the gateway', async () => {
    get.mockResolvedValue({ message: [{ name: 'GAE-1' }] } as never);
    const rows = await listGatewayAccessEntries({ gateway: 'GW-1' });
    expect(rows).toEqual([{ name: 'GAE-1' }]);
    expect(get).toHaveBeenCalledWith('huf.ai.gateway_service.list_gateway_access_entries', { gateway: 'GW-1', state: 'Pending' });
  });

  it('passes an explicit state and tolerates no arguments', async () => {
    get.mockResolvedValue({ message: [] } as never);
    await listGatewayAccessEntries({ gateway: 'GW-1', state: 'Revoked' });
    expect(get).toHaveBeenLastCalledWith(expect.any(String), { gateway: 'GW-1', state: 'Revoked' });
    await listGatewayAccessEntries();
    expect(get).toHaveBeenLastCalledWith(expect.any(String), { gateway: undefined, state: 'Pending' });
  });

  it('returns an empty list when the server sends no message', async () => {
    get.mockResolvedValue({} as never);
    expect(await listGatewayAccessEntries({ gateway: 'GW-1' })).toEqual([]);
  });

  it('approves by code or entry name, with notes', async () => {
    post.mockResolvedValue({ message: { name: 'GAE-1', state: 'Approved', notification_status: 'sent' } } as never);
    const res = await approveGatewayPairing('PAIR-ABCD2345', 'ok');
    expect(res.state).toBe('Approved');
    expect(post).toHaveBeenCalledWith('huf.ai.gateway_service.approve_gateway_pairing', {
      code_or_entry_name: 'PAIR-ABCD2345',
      notes: 'ok',
    });
  });

  it('revokes by entry name', async () => {
    post.mockResolvedValue({ message: { name: 'GAE-1', state: 'Revoked' } } as never);
    expect(await revokeGatewayAccessEntry('GAE-1')).toEqual({ name: 'GAE-1', state: 'Revoked' });
    expect(post).toHaveBeenCalledWith('huf.ai.gateway_service.revoke_gateway_access_entry', { entry_name: 'GAE-1' });
  });

  it('turns transport failures into thrown errors', async () => {
    get.mockRejectedValue(new Error('boom'));
    await expect(listGatewayAccessEntries({ gateway: 'GW-1' })).rejects.toThrow();
    post.mockRejectedValue(new Error('nope'));
    await expect(approveGatewayPairing('X')).rejects.toThrow();
    await expect(revokeGatewayAccessEntry('X')).rejects.toThrow();
  });
});
