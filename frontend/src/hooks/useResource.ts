/**
 * useResource: read server data through the shared resource cache with one
 * contract for loading / error / data (empty handling lives in
 * components/ui/resource-state.tsx).
 *
 *   const { data, error, isLoading, refetch } = useResource(
 *     ['agents', { q }],
 *     ({ signal }) => agentApi.list(q, { signal }),
 *     { ttlMs: 60_000 },
 *   );
 *
 * Two components using the same key share one request; stale data renders
 * immediately and revalidates; the request is aborted on unmount or key change.
 * After a write, use `useResourceMutation` (or `resourceCache.invalidate`) so
 * affected keys refetch.
 *
 * Do NOT use for: streaming chat/SSE/socket state, form drafts, or UI-only
 * state. Those stay in local state / their existing hooks.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  resourceCache,
  serializeKey,
  isAbortError,
  toError,
  type ResourceCache,
  type ResourceError,
  type ResourceFetcher,
  type ResourceKey,
  type ResourceSnapshot,
} from '@/lib/resource-cache';

export interface UseResourceOptions {
  ttlMs?: number;
  /** Set false to defer fetching (e.g. until a dependency is known). Default true. */
  enabled?: boolean;
  /** Default true. */
  staleWhileRevalidate?: boolean;
  /** Keep showing the previous key's data while the new key loads. */
  keepPreviousData?: boolean;
  onError?: (error: ResourceError) => void;
  /** Override the cache (tests). Defaults to the shared cache. */
  cache?: ResourceCache;
}

export interface UseResourceResult<T> {
  data: T | undefined;
  error: ResourceError | undefined;
  /** No data yet and a request is pending (first load). */
  isLoading: boolean;
  /** A request is in flight (first load or background revalidate). */
  isValidating: boolean;
  /** Force a request now. Resolves with the data; rejects with the error. */
  refetch: () => Promise<T>;
  /** Write data into the cache directly (optimistic/updated value). */
  mutate: (next: T | ((current: T | undefined) => T)) => void;
}

export function useResource<T>(
  key: ResourceKey,
  fetcher: ResourceFetcher<T>,
  opts: UseResourceOptions = {},
): UseResourceResult<T> {
  const cache = opts.cache ?? resourceCache;
  const enabled = opts.enabled ?? true;
  const id = serializeKey(key);

  const keyRef = useRef(key);
  keyRef.current = key;
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const subscribe = useCallback(
    (cb: () => void) => cache.subscribe(keyRef.current, cb),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cache, id],
  );
  const getSnapshot = useCallback(
    () => cache.get<T>(keyRef.current),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cache, id],
  );
  const snap: ResourceSnapshot<T> = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    cache
      .fetch<T>(keyRef.current, (ctx) => fetcherRef.current(ctx), {
        ttlMs: optsRef.current.ttlMs,
        staleWhileRevalidate: optsRef.current.staleWhileRevalidate,
        signal: controller.signal,
      })
      .catch(() => {
        /* recorded on the snapshot */
      });
    return () => controller.abort();
  }, [cache, id, enabled]);

  // onError fires once per distinct error object while mounted.
  const reportedRef = useRef<unknown>(undefined);
  useEffect(() => {
    if (snap.error && reportedRef.current !== snap.error) {
      reportedRef.current = snap.error;
      optsRef.current.onError?.(snap.error);
    }
  }, [snap.error]);

  const previous = useRef<{ id: string; data: T | undefined }>({ id, data: undefined });
  if (snap.hasData) previous.current = { id, data: snap.data };
  const usePrevious = !!opts.keepPreviousData && !snap.hasData && previous.current.data !== undefined;
  const data = usePrevious ? previous.current.data : snap.data;
  const hasData = snap.hasData || usePrevious;

  const refetch = useCallback(
    () =>
      cache.fetch<T>(keyRef.current, (ctx) => fetcherRef.current(ctx), {
        ttlMs: optsRef.current.ttlMs,
        force: true,
      }),
    [cache],
  );
  const mutate = useCallback(
    (next: T | ((current: T | undefined) => T)) => {
      const current = cache.get<T>(keyRef.current).data;
      cache.set(keyRef.current, typeof next === 'function' ? (next as (c: T | undefined) => T)(current) : next);
    },
    [cache],
  );

  return {
    data,
    error: snap.error,
    isLoading: enabled && !hasData && !snap.error,
    isValidating: snap.isFetching,
    refetch,
    mutate,
  };
}

export interface UseResourceMutationOptions<TArgs, TResult> {
  /** Keys or prefixes to invalidate after success. */
  invalidate?: ResourceKey[] | ((result: TResult, args: TArgs) => ResourceKey[]);
  onSuccess?: (result: TResult, args: TArgs) => void;
  onError?: (error: ResourceError, args: TArgs) => void;
  cache?: ResourceCache;
}

export interface UseResourceMutationResult<TArgs, TResult> {
  /** Runs the mutation; resolves with the result, rejects with the error. */
  mutate: (args: TArgs) => Promise<TResult>;
  isPending: boolean;
  error: ResourceError | undefined;
  reset: () => void;
}

export function useResourceMutation<TArgs = void, TResult = void>(
  mutation: (args: TArgs) => Promise<TResult>,
  opts: UseResourceMutationOptions<TArgs, TResult> = {},
): UseResourceMutationResult<TArgs, TResult> {
  const cache = opts.cache ?? resourceCache;
  const [state, setState] = useState<{ isPending: boolean; error: ResourceError | undefined }>({
    isPending: false,
    error: undefined,
  });
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const mutationRef = useRef(mutation);
  mutationRef.current = mutation;
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const mutate = useCallback(
    async (args: TArgs) => {
      if (mounted.current) setState({ isPending: true, error: undefined });
      try {
        const result = await mutationRef.current(args);
        const inv = optsRef.current.invalidate;
        const keys = typeof inv === 'function' ? inv(result, args) : (inv ?? []);
        for (const k of keys) cache.invalidate(k);
        if (mounted.current) setState({ isPending: false, error: undefined });
        optsRef.current.onSuccess?.(result, args);
        return result;
      } catch (e) {
        const error = toError(e);
        if (mounted.current && !isAbortError(e)) setState({ isPending: false, error });
        else if (mounted.current) setState({ isPending: false, error: undefined });
        optsRef.current.onError?.(error, args);
        throw error;
      }
    },
    [cache],
  );
  const reset = useCallback(() => setState({ isPending: false, error: undefined }), []);

  return { mutate, isPending: state.isPending, error: state.error, reset };
}
