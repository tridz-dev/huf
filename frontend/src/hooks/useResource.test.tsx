// @vitest-environment jsdom
import { StrictMode, type ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ResourceCache } from '@/lib/resource-cache';
import { useResource, useResourceMutation } from './useResource';
import { ResourceBoundary } from '@/components/ui/resource-state';

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => ((resolve = a), (reject = b)));
  return { promise, resolve, reject };
};

describe('useResource', () => {
  it('goes loading -> data', async () => {
    const cache = new ResourceCache();
    const { result } = renderHook(() => useResource('k', async () => 5, { cache }));
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe(5));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isValidating).toBe(false);
  });

  it('exposes errors and retries via refetch', async () => {
    const cache = new ResourceCache();
    let fail = true;
    const { result } = renderHook(() =>
      useResource('k', async () => (fail ? Promise.reject(new Error('nope')) : 'ok'), { cache }),
    );
    await waitFor(() => expect(result.current.error?.message).toBe('nope'));
    fail = false;
    await act(async () => {
      await result.current.refetch();
    });
    expect(result.current.data).toBe('ok');
    expect(result.current.error).toBeUndefined();
  });

  it('calls onError once per error', async () => {
    const cache = new ResourceCache();
    const onError = vi.fn();
    renderHook(() => useResource('k', async () => Promise.reject(new Error('x')), { cache, onError }));
    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1));
  });

  it('does not fetch when disabled', () => {
    const cache = new ResourceCache();
    const f = vi.fn(async () => 1);
    const { result } = renderHook(() => useResource('k', f, { cache, enabled: false }));
    expect(f).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
  });

  it('aborts on key change and keeps previous data when asked', async () => {
    const cache = new ResourceCache();
    const signals: AbortSignal[] = [];
    const d2 = deferred<string>();
    const { result, rerender } = renderHook(
      ({ id }: { id: number }) =>
        useResource(
          ['item', id],
          ({ signal }) => {
            signals.push(signal);
            return id === 1 ? Promise.resolve('one') : d2.promise;
          },
          { cache, keepPreviousData: true },
        ),
      { initialProps: { id: 1 } },
    );
    await waitFor(() => expect(result.current.data).toBe('one'));
    rerender({ id: 2 });
    expect(result.current.data).toBe('one');
    expect(result.current.isLoading).toBe(false);
    rerender({ id: 3 });
    await act(async () => {});
    expect(signals[1].aborted).toBe(true);
    d2.resolve('late');
  });

  it('aborts the request on unmount and does not update afterwards', async () => {
    const cache = new ResourceCache();
    const d = deferred<number>();
    let sig!: AbortSignal;
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { unmount } = renderHook(() =>
      useResource('k', ({ signal }) => ((sig = signal), d.promise), { cache }),
    );
    unmount();
    await act(async () => {});
    expect(sig.aborted).toBe(true);
    d.resolve(1);
    await act(async () => {});
    expect(err).not.toHaveBeenCalled();
    err.mockRestore();
  });

  it('issues one request under StrictMode double-invoke', async () => {
    const cache = new ResourceCache();
    const f = vi.fn(async () => 'v');
    const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;
    const { result } = renderHook(() => useResource('k', f, { cache }), { wrapper });
    await waitFor(() => expect(result.current.data).toBe('v'));
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('shares one request between two hooks and reacts to invalidation', async () => {
    const cache = new ResourceCache();
    let n = 0;
    const f = vi.fn(async () => ++n);
    const a = renderHook(() => useResource(['x'], f, { cache }));
    const b = renderHook(() => useResource(['x'], f, { cache }));
    await waitFor(() => expect(a.result.current.data).toBe(1));
    expect(b.result.current.data).toBe(1);
    expect(f).toHaveBeenCalledTimes(1);
    act(() => void cache.invalidate(['x']));
    await waitFor(() => expect(a.result.current.data).toBe(2));
    expect(b.result.current.data).toBe(2);
  });

  it('mutate writes into the cache', async () => {
    const cache = new ResourceCache();
    const { result } = renderHook(() => useResource<number>('k', async () => 1, { cache }));
    await waitFor(() => expect(result.current.data).toBe(1));
    act(() => result.current.mutate((c) => (c ?? 0) + 10));
    expect(result.current.data).toBe(11);
  });
});

describe('useResourceMutation', () => {
  it('invalidates keys and prefixes on success only', async () => {
    const cache = new ResourceCache();
    const list = vi.fn(async () => [1]);
    const view = renderHook(() => useResource(['agents', 'list'], list, { cache }));
    await waitFor(() => expect(view.result.current.data).toEqual([1]));
    const ok = renderHook(() =>
      useResourceMutation(async (n: number) => n * 2, { cache, invalidate: [['agents']] }),
    );
    let out = 0;
    await act(async () => {
      out = await ok.result.current.mutate(2);
    });
    expect(out).toBe(4);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));

    const bad = renderHook(() =>
      useResourceMutation(async () => Promise.reject(new Error('fail')), { cache, invalidate: [['agents']] }),
    );
    await act(async () => {
      await bad.result.current.mutate().catch(() => {});
    });
    expect(bad.result.current.error?.message).toBe('fail');
    expect(list).toHaveBeenCalledTimes(2);
  });

  it('does not set state after unmount', async () => {
    const d = deferred<number>();
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result, unmount } = renderHook(() =>
      useResourceMutation(() => d.promise, { cache: new ResourceCache() }),
    );
    let p!: Promise<number>;
    act(() => {
      p = result.current.mutate();
    });
    unmount();
    d.resolve(1);
    await p;
    expect(err).not.toHaveBeenCalled();
    err.mockRestore();
  });
});

describe('ResourceBoundary', () => {
  const base = { data: undefined, error: undefined, isLoading: false, refetch: async () => {} };
  it('renders loading, error with retry, empty and content', () => {
    const { rerender } = render(
      <ResourceBoundary resource={{ ...base, isLoading: true }}>{() => <p>content</p>}</ResourceBoundary>,
    );
    expect(screen.getByRole('status')).toBeTruthy();
    const refetch = vi.fn(async () => {});
    rerender(
      <ResourceBoundary resource={{ ...base, error: { message: 'bad' }, refetch }}>{() => <p>content</p>}</ResourceBoundary>,
    );
    expect(screen.getByText('bad')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(refetch).toHaveBeenCalled();
    rerender(
      <ResourceBoundary resource={{ ...base, data: [] as number[] }} empty={{ title: 'No items' }}>
        {() => <p>content</p>}
      </ResourceBoundary>,
    );
    expect(screen.getByText('No items')).toBeTruthy();
    rerender(
      <ResourceBoundary resource={{ ...base, data: [1] }}>{(d) => <p>content {d.length}</p>}</ResourceBoundary>,
    );
    expect(screen.getByText('content 1')).toBeTruthy();
  });

  it('keeps showing data when a background revalidate errors', () => {
    render(
      <ResourceBoundary resource={{ ...base, data: [1], error: { message: 'bad' } }}>
        {() => <p>content</p>}
      </ResourceBoundary>,
    );
    expect(screen.getByText('content')).toBeTruthy();
  });
});
