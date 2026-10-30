"""Agent tools for channel conversations (Helpdesk FYI ticket). Other adapters add tools_crm.py / tools_erp.py."""

from __future__ import annotations

import json

import frappe

from huf.ai.channels import run_as


def create_ticket(summary: str = "", priority: str = "normal", **_ignored) -> str:
	"""Create an FYI HD Ticket for the current channel conversation (no handoff). Returns JSON; never raises."""
	try:
		summary = " ".join((summary or "").split())[:2000]
		if not summary:
			return json.dumps({"success": False, "error": "Summary is empty."})
		if "helpdesk" not in frappe.get_installed_apps():
			return json.dumps({"success": False, "error": "Helpdesk is not installed."})
		name = run_as.current_conversation()
		if not name:
			return json.dumps({"success": False, "error": "No active channel conversation."})
		if not frappe.has_permission("HD Ticket", "create"):
			return json.dumps({"success": False, "error": "You do not have permission to create tickets."})
		from huf.ai.channels.adapters.helpdesk import create_ticket as _create

		conversation = frappe.get_doc("Channel Conversation", name)
		ticket = _create(conversation, subject_hint=f"WhatsApp FYI: {summary[:80]}", summary=summary, priority=priority)
		return json.dumps({"success": True, "ticket": ticket.name})
	except Exception:
		frappe.log_error(title="create_ticket channel tool failed")
		return json.dumps({"success": False, "error": "Could not create the ticket."})
