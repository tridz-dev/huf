/**
 * Lazy-loaded, in-memory cache for "which tools does this Integration Service
 * expose" lookups (huf.ai.tools.integration_utils.get_service_tools).
 *
 * The list rarely changes — only when a tool doc is created or edited — so a
 * per-session cache avoids re-fetching it every time a card, badge, or modal
 * wants the count. Call invalidateServiceTools() (or invalidateAllServiceTools())
 * whenever a tool mutation could affect it; toolApi's create/update calls do
 * this already.
 */

import { getServiceTools } from './integrationApi';
import type { ServiceTool } from '@/types/integration.types';

const cache = new Map<string, ServiceTool[]>();
const inFlight = new Map<string, Promise<ServiceTool[]>>();

/** Fetch a service's tools, serving from cache when available. */
export function getServiceToolsCached(service: string): Promise<ServiceTool[]> {
  const cached = cache.get(service);
  if (cached) return Promise.resolve(cached);

  const pending = inFlight.get(service);
  if (pending) return pending;

  const promise = getServiceTools(service)
    .then((tools) => {
      cache.set(service, tools);
      inFlight.delete(service);
      return tools;
    })
    .catch((error) => {
      inFlight.delete(service);
      throw error;
    });

  inFlight.set(service, promise);
  return promise;
}

/** Synchronously read a cached count without triggering a fetch, or undefined if not yet loaded. */
export function getCachedServiceToolCount(service: string): number | undefined {
  return cache.get(service)?.length;
}

/** Clear the cached tool list for one service (or every service when omitted). */
export function invalidateServiceTools(service?: string): void {
  if (service) {
    cache.delete(service);
    inFlight.delete(service);
  } else {
    cache.clear();
    inFlight.clear();
  }
}
