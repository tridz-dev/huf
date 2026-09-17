"""Server-side boot + permission gate for the `meeting_recorder` Desk page.

Phase 4 of the HufAppDeskPortalDelivery track: this page proves the classic
Desk-page delivery pattern (frappe.ui.Page, per-page frappe.call() boot,
frappe.has_permission() gate) for a HUF App that is *also* still reachable
via the `/huf` SPA launcher tile (see huf/page/meeting_recorder/meeting_recorder.js
for the coexistence rationale). It is deliberately scoped to the one app
("meeting-recorder") this track was asked to prove the pattern against --
it is not a generic per-app Desk-page generator; a follow-up track would be
needed to templatize this for other apps' `delivery: "desk"` declarations.
"""

import frappe
from frappe import _

PAGE_NAME = "meeting_recorder"
HUF_APP_ID = "meeting-recorder"


@frappe.whitelist()
def get_boot():
	"""Return the boot context the page.js needs to mount the chat core.

	Two independent gates, both required, mirroring the guest-portal
	renderer's belt-and-suspenders style (huf.ai.app_public_renderer):

	1. frappe.has_permission("Page", ...) -- the Desk-page-level gate
	   (per the phase 4 spec: "a Desk page needs its own [boot], + a
	   frappe.has_permission('Page', ...) check before rendering the chat
	   UI"). The Page doctype's own `roles` (see meeting_recorder.json,
	   currently ["All"]) is what this actually checks against.
	2. The underlying `HUF App` record must still be `enabled=1` -- an
	   admin disabling the app (e.g. via the manual-override carve-out in
	   apps_loader.upsert_huf_app) should also pull the rug out from under
	   this Desk page, not just the SPA tile/portal renderer.
	"""
	if not frappe.has_permission(doctype="Page", doc=PAGE_NAME, ptype="read"):
		frappe.throw(_("You do not have permission to access this page."), frappe.PermissionError)

	app = frappe.db.get_value(
		"HUF App",
		HUF_APP_ID,
		["name", "title", "agent", "enabled"],
		as_dict=True,
	)
	if not app or not app.enabled:
		frappe.throw(_("This HUF App is not available."), frappe.PermissionError)

	if not app.agent:
		frappe.throw(_("This HUF App has no Agent configured."), frappe.ValidationError)

	return {
		"app_id": app.name,
		"title": app.title,
		"agent": app.agent,
		"csrf_token": frappe.sessions.get_csrf_token(),
	}
