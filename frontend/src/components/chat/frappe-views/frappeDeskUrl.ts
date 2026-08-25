/**
 * Builds "Open in Desk" links for the frappe-list/form/report artifact
 * views. Safe to do with a plain <a href> (no client-side routing, no
 * SSO/token handoff) because huf's frontend is installed as a Frappe app on
 * the same site/session as Desk in the standard deployment - see
 * Tracks/safwan-erooth.DeskAIArtifactWorkspace/PLAN.md, "Phase 4 finding".
 *
 * No existing doctype -> Desk-route slug helper was found in this repo (nor
 * in the vendored frappe framework we could locate under the time available
 * for this change) to reuse, so this mirrors Frappe's well-known desk
 * router convention (frappe/public/js/frappe/router.js
 * get_doctype_route/slug): lowercase, spaces to dashes. e.g. "Sales
 * Invoice" -> "sales-invoice", "HD Ticket" -> "hd-ticket".
 */

export function doctypeSlug(doctype: string): string {
	return doctype.trim().toLowerCase().replace(/ /g, '-');
}

export function deskListUrl(doctype: string): string {
	return `/app/${doctypeSlug(doctype)}`;
}

export function deskFormUrl(doctype: string, name: string): string {
	return `/app/${doctypeSlug(doctype)}/${encodeURIComponent(name)}`;
}
