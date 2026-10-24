import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ResourceCache, serializeKey } from './resource-cache';

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => ((resolve = a), (reject = b)));
  return { promise, resolve, reject };
};

describe('ResourceCache', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('serialises keys stably regardless of object key order', () => {
    expect(serializeKey(['a', { x: 1, y: 2 }])).toBe(serializeKey(['a', { y: 2, x: 1 }]));
    expect(serializeKey('a')).toBe(serializeKey(['a']));
  });

  it('dedupes concurrent fetches of one key', async () => {
    const c = new ResourceCache();
    const d = deferred<number>();
    const f = vi.fn(() => d.promise);
    const p1 = c.fetch('k', f);
    const p2 = c.fetch('k', f);
    d.resolve(7);
    expect(await p1).toBe(7);
    expect(await p2).toBe(7);
    expect(f).toHaveBeenCalledTimes(1);
    expect(c.get('k').data).toBe(7);
  });

  it('serves fresh data without a request, then stale-while-revalidate after ttl', async () => {
    const c = new ResourceCache();
    let n = 0;
    const f = vi.fn(async () => ++n);
    await c.fetch('k', f, { ttlMs: 1000 });
    expect(await c.fetch('k', f, { ttlMs: 1000 })).toBe(1);
    expect(f).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1500);
    expect(await c.fetch('k', f, { ttlMs: 1000 })).toBe(1); // stale returned immediately
    expect(f).toHaveBeenCalledTimes(2);
    await vi.waitFor(() => expect(c.get('k').data).toBe(2));
  });

  it('waits for fresh data when staleWhileRevalidate is false', async () => {
    const c = new ResourceCache();
    let n = 0;
    const f = async () => ++n;
    await c.fetch('k', f, { ttlMs: 10 });
    vi.advanceTimersByTime(20);
    expect(await c.fetch('k', f, { ttlMs: 10, staleWhileRevalidate: false })).toBe(2);
  });

  it('records errors and keeps previous data', async () => {
    const c = new ResourceCache();
    await c.fetch('k', async () => 1);
    await expect(c.fetch('k', async () => Promise.reject({ message: 'boom', code: 'X' }), { force: true })).rejects.toThrow('boom');
    const s = c.get<number>('k');
    expect(s.data).toBe(1);
    expect(s.error?.code).toBe('X');
  });

  it('invalidates by exact key and by prefix, refetching subscribed entries', async () => {
    const c = new ResourceCache();
    const a = vi.fn(async () => 'a');
    const b = vi.fn(async () => 'b');
    const other = vi.fn(async () => 'o');
    await c.fetch(['agents', 1], a);
    await c.fetch(['agents', 2], b);
    await c.fetch(['models'], other);
    c.subscribe(['agents', 1], () => {});
    expect(c.invalidate(['agents'])).toBe(2);
    expect(c.get(['agents', 2]).invalidated).toBe(true);
    expect(c.get(['models']).invalidated).toBe(false);
    await vi.waitFor(() => expect(a).toHaveBeenCalledTimes(2)); // subscribed -> refetch
    expect(b).toHaveBeenCalledTimes(1); // unsubscribed -> lazy
    expect(c.invalidate(['agents', 2])).toBe(1);
    expect(c.invalidate('agent')).toBe(0); // prefix is element-wise
  });

  it('aborts the request when the only caller aborts, but not while another waits', async () => {
    const c = new ResourceCache();
    let signal!: AbortSignal;
    const d = deferred<number>();
    const f = ({ signal: s }: { signal: AbortSignal }) => ((signal = s), d.promise);
    const c1 = new AbortController();
    const c2 = new AbortController();
    const p1 = c.fetch('k', f, { signal: c1.signal });
    const p2 = c.fetch('k', f, { signal: c2.signal });
    c1.abort();
    await expect(p1).rejects.toMatchObject({ name: 'AbortError' });
    await Promise.resolve();
    expect(signal.aborted).toBe(false);
    c2.abort();
    await expect(p2).rejects.toMatchObject({ name: 'AbortError' });
    await Promise.resolve();
    expect(signal.aborted).toBe(true);
    d.resolve(1);
    expect(c.get('k').error).toBeUndefined();
    expect(c.get('k').isFetching).toBe(false);
  });

  it('evicts least recently used entries without subscribers', async () => {
    const c = new ResourceCache({ maxEntries: 2 });
    c.set('a', 1);
    c.set('b', 2);
    c.get('a'); // a is now most recent
    c.set('c', 3);
    expect(c.size).toBe(2);
    expect(c.get('b').hasData).toBe(false);
    expect(c.get('a').data).toBe(1);
  });

  it('never evicts subscribed entries', () => {
    const c = new ResourceCache({ maxEntries: 1 });
    c.subscribe('a', () => {});
    c.set('a', 1);
    c.set('b', 2);
    expect(c.get('a').data).toBe(1);
  });

  it('notifies subscribers and keeps snapshots stable between changes', () => {
    const c = new ResourceCache();
    const cb = vi.fn();
    const off = c.subscribe('k', cb);
    const s1 = c.get('k');
    expect(c.get('k')).toBe(s1);
    c.set('k', 1);
    expect(cb).toHaveBeenCalled();
    expect(c.get('k')).not.toBe(s1);
    off();
  });
});
