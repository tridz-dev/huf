"""Agent tool ``create_lead``: create/find the CRM Lead for the current WhatsApp contact."""

from __future__ import annotations

import json

import frappe


def _err(code: str, message: str = "") -> str:
	return json.dumps({"success": False, "error": code, "message": message}, default=str)


def handle_create_lead(**kwargs) -> str:
	from huf.ai.tools.handoff import _chat_conversation, _run_chat

	if "crm" not in frappe.get_installed_apps():
		return _err("crm_not_installed", "Frappe CRM is not installed on this site")
	gateway, space_key = _run_chat()
	if not gateway:
		return _err("gateway_context_required", "create_lead only works inside a gateway conversation")
	name = _chat_conversation(gateway, space_key)
	if not name:
		return _err("conversation_not_found", "No channel conversation exists for this chat")
	from huf.ai.channels.adapters import crm

	conversation = frappe.get_doc("Channel Conversation", name)
	try:
		lead = crm.find_lead(conversation.contact_handle)
		created = not lead
		if created:
			lead = crm.create_lead(
				conversation.contact_handle,
				str(kwargs.get("name") or conversation.get("contact_name") or ""),
				str(kwargs.get("email") or ""),
				referral=crm.referral_for(conversation),
			)
		note = str(kwargs.get("note") or "").strip()
		if note:
			crm.add_note(lead, "Note from AI agent", f"<p>{frappe.utils.escape_html(note[:2000])}</p>")
		if not conversation.get("lead_name"):
			conversation.db_set({"lead_doctype": crm.LEAD, "lead_name": lead})
	except Exception:
		frappe.log_error(title="create_lead tool failed")
		return _err("create_failed", "Could not create the lead")
	return json.dumps({"success": True, "lead": lead, "created": created}, default=str)
