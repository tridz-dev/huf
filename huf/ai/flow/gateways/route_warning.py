"""Q11: a route (gateway default or binding) that points at a flow which is not Active is saved, with a warning.

Never refuses: the flow may be switched on later. At dispatch the message falls through (see ``_start_flow_for_event``).
"""

from __future__ import annotations

import frappe
from frappe import _


def not_live_message(flow_id) -> str | None:
	"""Plain warning when ``flow_id`` exists but is not Active (or does not exist); None when it is live or blank."""
	if not flow_id:
		return None
	status = frappe.db.get_value("Flow Definition", flow_id, "status")
	if status is None:
		return _("The flow {0} was not found, so messages sent to this route will not start anything.").format(flow_id)
	if status == "Active":
		return None
	return _("The flow {0} is not published yet ({1}). Messages sent to this route will not start it until it is.").format(flow_id, status)


def warn_if_flow_not_live(flow_id) -> str | None:
	"""Show the warning (orange note) and return it; the save always goes on."""
	try:
		message = not_live_message(flow_id)
	except Exception:
		return None
	if message and not getattr(frappe.flags, "in_install", False) and not getattr(frappe.flags, "in_import", False):
		frappe.msgprint(message, title=_("Check this route"), indicator="orange")
	return message
