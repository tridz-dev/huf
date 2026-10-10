import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { listDesktopHosts, type DesktopHost } from '@/services/desktopHostApi';

/** How often the online dot refreshes while a hosted conversation is on screen. */
export const DESKTOP_HOSTS_POLL_MS = 20_000;

interface HostsState {
  hosts: DesktopHost[];
  loaded: boolean;
  error: boolean;
}

/**
 * One shared store: the rail rows and the chat header all read the same list, so a screen full of
 * hosted conversations costs one request per interval instead of one per row.
 */
let state: HostsState = { hosts: [], loaded: false, error: false };
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight: Promise<void> | null = null;

function emit(next: HostsState) {
  state = next;
  listeners.forEach((l) => l());
}

export function refreshDesktopHosts(): Promise<void> {
  if (inFlight) return inFlight;
  inFlight = listDesktopHosts()
    .then((hosts) => emit({ hosts, loaded: true, error: false }))
    .catch(() => emit({ ...state, loaded: true, error: true }))
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

function tick() {
  // A hidden tab needs no fresh dot; the visibility handler refreshes when it comes back.
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
  void refreshDesktopHosts();
}

function onVisible() {
  if (document.visibilityState === 'visible') void refreshDesktopHosts();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refreshDesktopHosts();
    timer = setInterval(tick, DESKTOP_HOSTS_POLL_MS);
    document.addEventListener('visibilitychange', onVisible);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      if (timer) clearInterval(timer);
      timer = null;
      document.removeEventListener('visibilitychange', onVisible);
    }
  };
}

const getSnapshot = () => state;

/** Test hook: reset the module store between tests. */
export function __resetDesktopHostsForTests() {
  if (timer) clearInterval(timer);
  timer = null;
  inFlight = null;
  listeners.clear();
  state = { hosts: [], loaded: false, error: false };
}

/**
 * The user's desktop devices, polled while at least one component is subscribed.
 * `enabled = false` reads the cache without subscribing (no polling, no request).
 */
export function useDesktopHosts(enabled: boolean = true) {
  const noop = useCallback(() => () => {}, []);
  const snap = useSyncExternalStore(enabled ? subscribe : noop, getSnapshot, getSnapshot);
  const byDevice = useMemo(() => {
    const map = new Map<string, DesktopHost>();
    for (const h of snap.hosts) map.set(h.device_id, h);
    return map;
  }, [snap.hosts]);
  return {
    hosts: snap.hosts,
    byDevice,
    loaded: snap.loaded,
    error: snap.error,
    refresh: refreshDesktopHosts,
  };
}
