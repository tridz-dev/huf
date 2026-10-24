/**
 * resource-cache: a small, framework-free keyed cache for SERVER data.
 *
 * Pattern
 *  - Every piece of server data lives under a key (`['agents', 'list', {q}]`).
 *    Keys are serialised stably (object key order does not matter).
 *  - `fetch(key, fetcher)` dedupes: concurrent callers of one key share a
 *    single in-flight promise. Fresh data (younger than `ttlMs`) is returned
 *    without a request; stale data is returned immediately and revalidated in
 *    the background (stale-while-revalidate).
 *  - `invalidate(keyOrPrefix)` marks entries stale; entries that currently
 *    have subscribers refetch right away. A string or array prefix matches
 *    that key and every key beneath it.
 *  - The in-flight request is aborted (via AbortSignal) once every caller
 *    that wanted it has gone away.
 *  - Bounded: least-recently-used entries without subscribers or in-flight
 *    work are evicted past `maxEntries`.
 *
 * Use it through `useResource` (hooks/useResource.ts) in components.
 *
 * Do NOT use it for: streaming/SSE/socket chat state, optimistic editor
 * drafts, form state, or anything that is UI state rather than a copy of
 * server data. Those keep their own local state.
 *
 * Error type: every error surfaced by the cache is an `ApiError` (lib/api).
 * Fetchers may throw anything; `toError` normalises it via `normalizeError`.
 * Aborts (AbortError or ApiError code 'aborted') are never stored as errors.
 */
import { isApiError, normalizeError, type ApiError } from '@/lib/api';

export type ResourceKey = readonly unknown[] | string;
export type ResourceError = ApiError;
export type ResourceFetcher<T> = (ctx: { signal: AbortSignal }) => Promise<T>;

export interface ResourceSnapshot<T = unknown> {
  readonly data: T | undefined;
  readonly error: ResourceError | undefined;
  readonly hasData: boolean;
  /** ms epoch of the last successful write, 0 if never. */
  readonly updatedAt: number;
  /** A request for this key is in flight. */
  readonly isFetching: boolean;
  /** Marked stale by invalidate(); cleared by the next successful write. */
  readonly invalidated: boolean;
}

export interface FetchOptions {
  /** Freshness window. Defaults to the cache default. 0 = always stale. */
  ttlMs?: number;
  /** Skip the freshness check and request now (still shares an in-flight request). */
  force?: boolean;
  /** Return stale data immediately and revalidate in background. Default true. */
  staleWhileRevalidate?: boolean;
  /** Caller's cancellation. Aborting rejects this caller only; the request is aborted once no caller wants it. */
  signal?: AbortSignal;
}

export interface ResourceCacheOptions {
  maxEntries?: number;
  defaultTtlMs?: number;
}

/** Convert anything thrown into an ApiError. Delegates to lib/api `normalizeError`. */
export function toError(value: unknown): ResourceError {
  return normalizeError(value);
}

/** True for an aborted request: a native AbortError, or an ApiError with code 'aborted'. */
export function isAbortError(e: unknown): boolean {
  if (isApiError(e)) return e.code === 'aborted';
  return !!e && typeof e === 'object' && (e as { name?: string }).name === 'AbortError';
}

function abortError(): Error {
  const e = new Error('Aborted');
  e.name = 'AbortError';
  return e;
}

function stable(v: unknown): string {
  if (v === undefined) return '__undefined__';
  if (v === null || typeof v !== 'object') return JSON.stringify(v) ?? String(v);
  if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`;
  const obj = v as Record<string, unknown>;
  return `{${Object.keys(obj)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${stable(obj[k])}`)
    .join(',')}}`;
}

function keyParts(key: ResourceKey): string[] {
  return (typeof key === 'string' ? [key] : key).map(stable);
}

/** Stable string id for a key (usable as a React dependency). */
export function serializeKey(key: ResourceKey): string {
  return JSON.stringify(keyParts(key));
}

const EMPTY: ResourceSnapshot = Object.freeze({
  data: undefined,
  error: undefined,
  hasData: false,
  updatedAt: 0,
  isFetching: false,
  invalidated: false,
});

interface Inflight {
  controller: AbortController;
  waiters: number;
  background: boolean;
  promise: Promise<unknown>;
}

interface Entry {
  parts: string[];
  snap: ResourceSnapshot;
  listeners: Set<() => void>;
  inflight?: Inflight;
  fetcher?: ResourceFetcher<unknown>;
  ttlMs?: number;
}

export class ResourceCache {
  private entries = new Map<string, Entry>();
  private readonly maxEntries: number;
  private readonly defaultTtlMs: number;

  constructor(opts: ResourceCacheOptions = {}) {
    this.maxEntries = opts.maxEntries ?? 200;
    this.defaultTtlMs = opts.defaultTtlMs ?? 30_000;
  }

  /** Current snapshot. Referentially stable until the entry changes. */
  get<T = unknown>(key: ResourceKey): ResourceSnapshot<T> {
    const e = this.entries.get(serializeKey(key));
    if (!e) return EMPTY as ResourceSnapshot<T>;
    this.touch(serializeKey(key), e);
    return e.snap as ResourceSnapshot<T>;
  }

  /** Write data directly (e.g. after a mutation). Clears error and invalidation. */
  set<T>(key: ResourceKey, data: T): void {
    const id = serializeKey(key);
    const e = this.ensure(id, key);
    this.write(e, { data, hasData: true, error: undefined, updatedAt: Date.now(), invalidated: false });
    this.evict();
  }

  subscribe(key: ResourceKey, cb: () => void): () => void {
    const id = serializeKey(key);
    const e = this.ensure(id, key);
    e.listeners.add(cb);
    return () => {
      e.listeners.delete(cb);
      this.evict();
    };
  }

  /** Mark every entry equal to, or beneath, the key/prefix stale. Subscribed entries refetch. Returns count. */
  invalidate(keyOrPrefix: ResourceKey): number {
    const prefix = keyParts(keyOrPrefix);
    let n = 0;
    for (const e of [...this.entries.values()]) {
      if (prefix.length > e.parts.length || !prefix.every((p, i) => e.parts[i] === p)) continue;
      n++;
      if (e.inflight) {
        e.inflight.controller.abort();
        e.inflight = undefined;
      }
      this.write(e, { invalidated: true, isFetching: false });
      if (e.listeners.size > 0 && e.fetcher) {
        void this.load(e, e.fetcher, { background: true }).catch(() => {});
      }
    }
    return n;
  }

  /** Drop everything (e.g. on logout). In-flight requests are aborted. */
  clear(): void {
    for (const e of this.entries.values()) e.inflight?.controller.abort();
    const withListeners = [...this.entries.values()].filter((e) => e.listeners.size > 0);
    this.entries.clear();
    for (const e of withListeners) {
      e.snap = EMPTY;
      for (const l of [...e.listeners]) l();
    }
  }

  get size(): number {
    return this.entries.size;
  }

  fetch<T>(key: ResourceKey, fetcher: ResourceFetcher<T>, opts: FetchOptions = {}): Promise<T> {
    const id = serializeKey(key);
    const e = this.ensure(id, key);
    this.touch(id, e);
    e.fetcher = fetcher as ResourceFetcher<unknown>;
    const ttl = opts.ttlMs ?? this.defaultTtlMs;
    e.ttlMs = ttl;
    const { snap } = e;
    const fresh = snap.hasData && !snap.invalidated && Date.now() - snap.updatedAt < ttl;
    if (!opts.force && fresh) return Promise.resolve(snap.data as T);
    if (!opts.force && snap.hasData && opts.staleWhileRevalidate !== false) {
      void this.load(e, fetcher as ResourceFetcher<unknown>, { background: true }).catch(() => {});
      return Promise.resolve(snap.data as T);
    }
    return this.load(e, fetcher as ResourceFetcher<unknown>, { signal: opts.signal }) as Promise<T>;
  }

  // ---- internals ----

  private ensure(id: string, key: ResourceKey): Entry {
    let e = this.entries.get(id);
    if (!e) {
      e = { parts: keyParts(key), snap: EMPTY, listeners: new Set() };
      this.entries.set(id, e);
    }
    return e;
  }

  private touch(id: string, e: Entry): void {
    this.entries.delete(id);
    this.entries.set(id, e);
  }

  private write(e: Entry, patch: Partial<Mutable<ResourceSnapshot>>): void {
    e.snap = { ...e.snap, ...patch };
    for (const l of [...e.listeners]) l();
  }

  private evict(): void {
    if (this.entries.size <= this.maxEntries) return;
    for (const [id, e] of this.entries) {
      if (this.entries.size <= this.maxEntries) break;
      if (e.listeners.size === 0 && !e.inflight) this.entries.delete(id);
    }
  }

  private load(
    e: Entry,
    fetcher: ResourceFetcher<unknown>,
    opts: { signal?: AbortSignal; background?: boolean },
  ): Promise<unknown> {
    let inf = e.inflight;
    if (!inf) {
      const controller = new AbortController();
      const created: Inflight = { controller, waiters: 0, background: !!opts.background, promise: undefined as never };
      created.promise = (async () => {
        try {
          const data = await fetcher({ signal: controller.signal });
          if (e.inflight === created) {
            e.inflight = undefined;
            this.write(e, { data, hasData: true, error: undefined, updatedAt: Date.now(), invalidated: false, isFetching: false });
          }
          return data;
        } catch (err) {
          // Aborts are never surfaced as errors, whoever aborted.
          if (controller.signal.aborted || isAbortError(err)) {
            if (e.inflight === created) {
              e.inflight = undefined;
              this.write(e, { isFetching: false });
            }
            throw abortError();
          }
          const error = toError(err);
          if (e.inflight === created) {
            e.inflight = undefined;
            this.write(e, { error, isFetching: false });
          }
          throw error;
        }
      })();
      // Unobserved rejections (background / all callers gone) must not surface.
      created.promise.catch(() => {});
      // A fetcher that ignores the signal must not leave the entry stuck fetching.
      controller.signal.addEventListener('abort', () => {
        if (e.inflight === created) {
          e.inflight = undefined;
          this.write(e, { isFetching: false });
        }
      });
      e.inflight = created;
      inf = created;
      this.write(e, { isFetching: true });
    }
    if (!opts.signal) {
      if (!opts.background) inf.background = false;
      return inf.promise;
    }
    inf.background = false;
    return this.wait(inf, opts.signal);
  }

  private wait(inf: Inflight, signal: AbortSignal): Promise<unknown> {
    inf.waiters++;
    return new Promise((resolve, reject) => {
      let done = false;
      const release = () => {
        if (done) return;
        done = true;
        signal.removeEventListener('abort', onAbort);
        inf.waiters--;
        if (inf.waiters === 0 && !inf.background) {
          // Deferred so a StrictMode remount can rejoin before we cancel.
          queueMicrotask(() => {
            if (inf.waiters === 0 && !inf.background) inf.controller.abort();
          });
        }
      };
      const onAbort = () => {
        release();
        reject(abortError());
      };
      if (signal.aborted) return onAbort();
      signal.addEventListener('abort', onAbort);
      inf.promise.then(
        (v) => (release(), resolve(v)),
        (err) => (release(), reject(err)),
      );
    });
  }
}

type Mutable<T> = { -readonly [K in keyof T]: T[K] };

/** App-wide shared cache. Tests should construct their own `new ResourceCache()`. */
export const resourceCache = new ResourceCache();
