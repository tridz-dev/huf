/**
 * API service for HUF App Agent Discovery
 */

import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface AppDiscoveryStatus {
  app: string;
  has_huf_dir: boolean;
  definition_counts: Record<string, number>;
  last_sync: string | null;
  files: string[];
}

export interface DiscoverResult {
  synced_apps: string[];
  total_definitions: number;
  by_type: Record<string, number>;
  errors: string[];
  error_count: number;
  warnings: string[];
  warning_count: number;
}

export async function getAppDiscoveryStatus(): Promise<AppDiscoveryStatus[]> {
  try {
    const response = await call.post('huf.ai.app_registry.discovery.get_app_discovery_status', {});
    return (response?.message ?? []) as AppDiscoveryStatus[];
  } catch (e) {
    handleFrappeError(e, 'Failed to fetch app discovery status');
    throw e;
  }
}

export async function discoverAppDefinitions(
  appName?: string | null,
  useCache = false
): Promise<DiscoverResult> {
  try {
    const response = await call.post('huf.ai.app_registry.discovery.discover_app_definitions_api', {
      app_name: appName || undefined,
      use_cache: useCache,
    });
    return (response?.message ?? {}) as DiscoverResult;
  } catch (e) {
    handleFrappeError(e, 'Failed to sync app definitions');
    throw e;
  }
}

export async function rebuildAppDefinitions(): Promise<DiscoverResult> {
  try {
    const response = await call.post('huf.ai.app_registry.discovery.rebuild_app_definitions');
    return (response?.message ?? {}) as DiscoverResult;
  } catch (e) {
    handleFrappeError(e, 'Failed to rebuild app definitions');
    throw e;
  }
}
