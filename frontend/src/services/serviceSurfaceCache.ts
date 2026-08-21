/**
 * Lazy-loaded, in-memory cache for "which UI surface (Integrations vs
 * Gateways) owns this service" lookups, keyed off the Integration Service
 * doctype's `surface` field.
 *
 * The service catalog rarely changes, so a per-session cache avoids
 * re-fetching it for every row rendered in a list. `surface` is not a
 * required field — records created before it existed (or left blank) are
 * treated as `'Integration'`, never `'Gateway'`.
 */

import { getIntegrationServices } from './integrationApi';

export type ServiceSurface = 'Integration' | 'Gateway';

const DEFAULT_SURFACE: ServiceSurface = 'Integration';

let cache: Map<string, ServiceSurface> | null = null;
let inFlight: Promise<Map<string, ServiceSurface>> | null = null;

function buildMap(services: Array<{ service_name: string; surface?: ServiceSurface }>) {
  const map = new Map<string, ServiceSurface>();
  for (const service of services) {
    map.set(service.service_name.toLowerCase(), service.surface || DEFAULT_SURFACE);
  }
  return map;
}

/** Fetch (and cache) the service-name -> surface map. */
export function getServiceSurfaceMap(): Promise<Map<string, ServiceSurface>> {
  if (cache) return Promise.resolve(cache);
  if (inFlight) return inFlight;

  inFlight = getIntegrationServices()
    .then((services) => {
      cache = buildMap(services);
      inFlight = null;
      return cache;
    })
    .catch((error) => {
      inFlight = null;
      throw error;
    });

  return inFlight;
}

/** Synchronously read the surface for a service from cache, defaulting to 'Integration'. */
export function getServiceSurface(serviceName: string | null | undefined): ServiceSurface {
  const normalized = (serviceName || '').trim().toLowerCase();
  return cache?.get(normalized) || DEFAULT_SURFACE;
}

/** Clear the cached map, e.g. after a service is created/edited. */
export function invalidateServiceSurfaceCache(): void {
  cache = null;
  inFlight = null;
}
