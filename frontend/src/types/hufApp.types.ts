/**
 * Launcher metadata for a registered HUF App, as returned by the
 * `huf.ai.apps_api.get_huf_apps` whitelisted method. Only safe,
 * user-facing fields are exposed to the frontend.
 */
export interface HufApp {
	app_id: string;
	title: string;
	description?: string;
	route: string;
	icon?: string;
	category?: string;
	version?: string;
	/**
	 * Present only for System Managers: 1 = enabled, 0 = disabled. The
	 * frontend treats the mere presence of this field as the signal to
	 * show the enable/disable admin action (no client-side role check).
	 */
	enabled?: 0 | 1;
	/** Comma-separated DocType names the app exposes to the Data page. */
	exposed_tables?: string;
}
