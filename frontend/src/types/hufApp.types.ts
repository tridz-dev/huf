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
}
