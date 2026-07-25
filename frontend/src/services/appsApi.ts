import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { HufApp } from '@/types/hufApp.types';

/**
 * Fetch the HUF Apps the current user is permitted to open, for the
 * Apps launcher screen. Backed by the whitelisted method
 * `huf.ai.apps_api.get_huf_apps`, whose payload is wrapped in the
 * standard Frappe `{ message: ... }` envelope.
 *
 * Defensive by design: a missing/malformed `apps` key is treated as an
 * empty list (the launcher shows its empty state), while a failed
 * request (e.g. 404 before the backend ships) surfaces as an error.
 */
export async function getHufApps(): Promise<HufApp[]> {
	try {
		const result = await call.get('huf.ai.apps_api.get_huf_apps');
		const apps = result?.message?.apps;
		return Array.isArray(apps) ? (apps as HufApp[]) : [];
	} catch (error) {
		handleFrappeError(error, 'Error fetching HUF apps');
	}
}
