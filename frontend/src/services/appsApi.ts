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

/**
 * Enable or disable a registered HUF App (System Manager only). Backed
 * by `huf.ai.apps_api.set_huf_app_enabled`, which returns `{ok: true}`
 * or throws — either way the caller refetches the list afterwards.
 */
export async function setHufAppEnabled(appId: string, enabled: boolean): Promise<void> {
	try {
		await call.post('huf.ai.apps_api.set_huf_app_enabled', {
			app_id: appId,
			enabled: enabled ? 1 : 0,
		});
	} catch (error) {
		handleFrappeError(error, 'Error updating HUF app');
	}
}

/** A DocType an installed HUF App exposes, with its source app. */
export interface ExposedAppTable {
	doctype: string;
	app_id: string;
	app_title: string;
}

/**
 * Flatten the `exposed_tables` (comma-separated DocType names) carried
 * by apps in the `get_huf_apps` response into rows for the Data page's
 * "App Tables" section. Apps without the field contribute nothing.
 */
export async function getExposedAppTables(): Promise<ExposedAppTable[]> {
	try {
		const result = await call.get('huf.ai.apps_api.get_huf_apps');
		const apps = result?.message?.apps;
		if (!Array.isArray(apps)) return [];
		const rows: ExposedAppTable[] = [];
		for (const app of apps as HufApp[]) {
			if (typeof app?.exposed_tables !== 'string' || !app.exposed_tables.trim()) continue;
			for (const raw of app.exposed_tables.split(',')) {
				const doctype = raw.trim();
				if (!doctype) continue;
				rows.push({
					doctype,
					app_id: app.app_id,
					app_title: app.title || app.app_id,
				});
			}
		}
		return rows;
	} catch (error) {
		handleFrappeError(error, 'Error fetching exposed app tables');
	}
}
