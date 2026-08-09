import frappe
from frappe import _

from .automation_runner import run_automation
from .automation_runtime_flag import automation_runtime_is_new


@frappe.whitelist()
def trigger_app_event(app_name: str, event_name: str, payload: dict | None = None) -> dict:
	"""Fire every enabled App Event Automation Trigger matching (app_name, event_name).

	Net-new: the legacy "App Event" Agent Trigger type has no runtime
	implementation anywhere in this codebase (schema field only) — there is
	no legacy behavior to preserve or fall back to. Intended for internal
	callers (other huf modules, external apps with a real Frappe session)
	that want to fan out an app-level event to any matching Automations —
	not for untrusted/unauthenticated callers (no allow_guest, unlike the
	Webhook trigger type which is specifically for that).
	"""
	if not automation_runtime_is_new():
		return {"triggered": 0, "skipped": "legacy_runtime"}

	if not frappe.has_permission("Automation", "read"):
		frappe.throw(_("You do not have permission to trigger app events."), frappe.PermissionError)

	if not app_name or not event_name:
		frappe.throw(_("app_name and event_name are required."))

	triggers = frappe.get_all(
		"Automation Trigger",
		filters={
			"trigger_type": "App Event",
			"app_name": app_name,
			"event_name": event_name,
			"disabled": 0,
		},
		fields=["name", "automation"],
	)

	triggered_automations = []
	for t in triggers:
		try:
			run_automation(
				t["automation"],
				trigger_name=t["name"],
				trigger_context={
					"type": "app_event",
					"app_name": app_name,
					"event_name": event_name,
					"payload": payload or {},
				},
			)
			triggered_automations.append(t["automation"])
		except Exception:
			frappe.log_error(
				title=f"App Event Automation Error: {t['name']}",
				message=frappe.get_traceback(),
			)

	return {"triggered": len(triggered_automations), "automation_names": triggered_automations}
