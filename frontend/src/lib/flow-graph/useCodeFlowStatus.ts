/**
 * Execute code in Flows: the status the server reports, loaded once per page load and shared by the palette, the
 * step form, the publish check and the settings screen. `refreshCodeFlowStatus()` re-reads it (after the switch changes).
 */
import { useEffect, useState } from 'react';
import { fetchCodeFlowStatus, type CodeFlowStatus } from '@/services/flow/codeFlowApi';

let cached: CodeFlowStatus | null = null;
let inFlight: Promise<CodeFlowStatus | null> | null = null;
const listeners = new Set<(status: CodeFlowStatus | null) => void>();

function publish(status: CodeFlowStatus | null) {
  cached = status;
  listeners.forEach((fn) => fn(status));
}

/** Load the status (cached for the page load). `force` re-reads it from the server. */
export function loadCodeFlowStatus(force = false): Promise<CodeFlowStatus | null> {
  if (!force && cached) return Promise.resolve(cached);
  if (!force && inFlight) return inFlight;
  const request = fetchCodeFlowStatus()
    .then((status) => {
      publish(status);
      return status;
    })
    .catch(() => {
      // Unknown means "not available": never offer code on a failed lookup.
      if (!cached) publish(null);
      return cached;
    })
    .finally(() => {
      if (inFlight === request) inFlight = null;
    });
  inFlight = request;
  return request;
}

export function refreshCodeFlowStatus(): Promise<CodeFlowStatus | null> {
  return loadCodeFlowStatus(true);
}

/** Forget the cached value (tests). */
export function resetCodeFlowStatus() {
  cached = null;
  inFlight = null;
}

/** The shared status; `loading` until the first answer. */
export function useCodeFlowStatus(): { status: CodeFlowStatus | null; loading: boolean } {
  const [status, setStatus] = useState<CodeFlowStatus | null>(cached);
  const [loading, setLoading] = useState(!cached);
  useEffect(() => {
    const onChange = (next: CodeFlowStatus | null) => setStatus(next);
    listeners.add(onChange);
    let alive = true;
    loadCodeFlowStatus().then((s) => {
      if (!alive) return;
      setStatus(s);
      setLoading(false);
    });
    return () => {
      alive = false;
      listeners.delete(onChange);
    };
  }, []);
  return { status, loading };
}

