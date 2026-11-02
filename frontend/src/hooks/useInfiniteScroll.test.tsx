// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useInfiniteScroll } from './useInfiniteScroll';

type Params = { search?: string; status?: string };

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useInfiniteScroll first-page races', () => {
  it('applies a filter set while the first load is still running (reload with ?status=Failed)', async () => {
    const calls: Array<{ status?: string; d: ReturnType<typeof deferred<{ data: string[]; hasMore: boolean; total: number }>> }> = [];
    const fetchFn = (params: Params) => {
      const d = deferred<{ data: string[]; hasMore: boolean; total: number }>();
      calls.push({ status: params.status, d });
      return d.promise;
    };
    const { result } = renderHook(() => useInfiniteScroll<Params, string>({ fetchFn, initialParams: {}, debounceMs: 20 }));
    expect(calls).toHaveLength(1);
    act(() => result.current.setFilter('status', 'Failed'));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].status).toBe('Failed');
    // The slow unfiltered answer arrives last: it must not replace the filtered list.
    await act(async () => {
      calls[1].d.resolve({ data: ['failed-run'], hasMore: false, total: 1 });
    });
    await act(async () => {
      calls[0].d.resolve({ data: ['ok-run-1', 'ok-run-2'], hasMore: false, total: 2 });
    });
    await waitFor(() => expect(result.current.items).toEqual(['failed-run']));
    expect(result.current.initialLoading).toBe(false);
  });

  it('applies a search typed while the first load is running', async () => {
    const seen: Array<string | undefined> = [];
    const fetchFn = async (params: Params) => {
      seen.push(params.search);
      await new Promise((r) => setTimeout(r, 60));
      return { data: [params.search ?? 'all'], hasMore: false, total: 1 };
    };
    const { result } = renderHook(() => useInfiniteScroll<Params, string>({ fetchFn, initialParams: {}, debounceMs: 10 }));
    act(() => result.current.setSearch('uiv-wp5'));
    await waitFor(() => expect(result.current.items).toEqual(['uiv-wp5']));
    expect(seen).toEqual([undefined, 'uiv-wp5']);
  });

  it('settles loading when the newer request fails, and ignores the older answer that arrives afterwards', async () => {
    const calls: Array<{ status?: string; d: ReturnType<typeof deferred<{ data: string[]; hasMore: boolean; total: number }>> }> = [];
    const fetchFn = (params: Params) => {
      const d = deferred<{ data: string[]; hasMore: boolean; total: number }>();
      calls.push({ status: params.status, d });
      return d.promise;
    };
    const { result } = renderHook(() => useInfiniteScroll<Params, string>({ fetchFn, initialParams: {}, debounceMs: 20 }));
    act(() => result.current.setFilter('status', 'Failed'));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(result.current.loading).toBe(true);
    await act(async () => {
      calls[1].d.reject(new Error('boom'));
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.initialLoading).toBe(false);
    expect(result.current.error?.message).toBe('boom');
    await act(async () => {
      calls[0].d.resolve({ data: ['stale'], hasMore: false, total: 1 });
    });
    expect(result.current.items).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});
