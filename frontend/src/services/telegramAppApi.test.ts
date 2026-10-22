import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  TelegramAppError, actConfirm, authenticate, getToken, me, parseEnvelope, resetTelegramAppSession, search,
} from './telegramAppApi';

const json = (status: number, message: unknown) =>
  new Response(JSON.stringify({ message }), { status, headers: { 'Content-Type': 'application/json' } });

const fetchMock = vi.fn();
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); resetTelegramAppSession(); });
afterEach(() => vi.unstubAllGlobals());

describe('parseEnvelope', () => {
  it('returns data on ok', () => {
    expect(parseEnvelope({ message: { ok: true, data: { a: 1 } } }, 200)).toEqual({ a: 1 });
  });
  it('throws a typed error from the envelope', () => {
    try {
      parseEnvelope({ message: { ok: false, error: { code: 'refused', message: 'Nope' } } }, 400);
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(TelegramAppError);
      expect((e as TelegramAppError).code).toBe('refused');
      expect((e as TelegramAppError).message).toBe('Nope');
    }
  });
  it('maps a bare HTTP status when there is no envelope', () => {
    expect(() => parseEnvelope(null, 429)).toThrow(/Request failed/);
  });
});

describe('telegramAppApi', () => {
  it('stores the token in memory only and sends the header', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    fetchMock.mockResolvedValueOnce(json(200, { token: 'tok1', expires_in: 900, role_scope: 'Admin', gateway: 'G' }));
    await authenticate('init', 'G');
    expect(getToken()).toBe('tok1');
    expect(setItem).not.toHaveBeenCalled();
    fetchMock.mockResolvedValueOnce(json(200, { ok: true, data: { full_name: 'A' } }));
    await me();
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toContain('huf.ai.telegram_miniapp_api.me');
    expect(init.headers['X-Huf-Tg-Token']).toBe('tok1');
  });

  it('re-authenticates once on 401 and retries', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { token: 'old', expires_in: 900, role_scope: 'Admin', gateway: 'G' }));
    await authenticate('init', 'G');
    fetchMock
      .mockResolvedValueOnce(json(401, { ok: false, error: { code: 'unauthorized', message: 'expired' } }))
      .mockResolvedValueOnce(json(200, { token: 'new', expires_in: 900, role_scope: 'Admin', gateway: 'G' }))
      .mockResolvedValueOnce(json(200, { ok: true, data: { doctype: 'X', items: [] } }));
    const res = await search('X', 'q');
    expect(res.items).toEqual([]);
    expect(getToken()).toBe('new');
    expect(fetchMock.mock.calls[3][1].headers['X-Huf-Tg-Token']).toBe('new');
    expect(fetchMock.mock.calls[3][0]).toContain('doctype=X');
  });

  it('surfaces non-401 errors without re-auth and POSTs JSON for act_confirm', async () => {
    fetchMock.mockResolvedValueOnce(json(400, { ok: false, error: { code: 'refused', message: 'Expired' } }));
    await expect(actConfirm('n1')).rejects.toMatchObject({ code: 'refused' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ nonce: 'n1' }));
  });

  it('fails cleanly when auth is rejected', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{"exc":"x"}', { status: 401 }));
    await expect(authenticate('bad', 'G')).rejects.toMatchObject({ code: 'unauthorized' });
    expect(getToken()).toBeNull();
  });
});
