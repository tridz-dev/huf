"""Hand a channel conversation to a human: status handed_off + adapter-created linked document."""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.channels import adapters
from huf.ai.channels.reply_api import send_free_text

TARGETS = ("none", "helpdesk", "crm", "erpnext")


def handoff_conversation(
	conversation, target: str | None = None, summary: str = "", priority: str = "normal", message: str | None = None
) -> dict[str, Any]:
	"""Hand ``conversation`` (doc or name) to a human. Idempotent: an already handed-off one is returned as is.

	``target`` defaults to the gateway's ``handoff_target``; ``message`` to its ``handoff_message``
	(sent once, best effort, through the outbound policy). Never raises for a failing adapter or send.
	"""
	doc = frappe.get_doc("Channel Conversation", conversation) if isinstance(conversation, str) else conversation
	if doc.status == "handed_off":
		return {"success": True, "already": True, "doctype": doc.handoff_doctype, "name": doc.handoff_name}
	gateway = frappe.db.get_value("Gateway", doc.gateway, ["handoff_target", "handoff_message"], as_dict=True) or {}
	target = (target or gateway.get("handoff_target") or "none").strip().lower()
	if target not in TARGETS:
		target = "none"
	priority = priority if priority in adapters.PRIORITIES else "normal"
	adapter = adapters.get_adapter(target)
	try:
		doctype, name = adapter.handoff(doc, (summary or "")[:2000], priority)
	except Exception:
		frappe.log_error(title=f"Channel handoff adapter failed: {target}")
		doctype, name = None, None
	doc.db_set({"status": "handed_off", "handoff_doctype": doctype or None, "handoff_name": name or None})
	text = (message if message is not None else gateway.get("handoff_message")) or ""
	if text.strip():
		try:
			send_free_text(doc.gateway, doc.contact_handle, text)
			from huf.ai.channels.conversation import touch_outbound

			touch_outbound(doc, preview=text)
		except Exception as exc:
			frappe.logger("huf").warning(f"Handoff message not delivered for {doc.name}: {type(exc).__name__}")
	return {"success": True, "already": False, "doctype": doctype, "name": name, "target": target}


def handoff_from_decision(gateway_name: str, event_name: str, context: dict, payload: dict) -> None:
	"""Pipeline ``handoff`` Decision: hand the event's conversation over. Never raises."""
	try:
		from huf.ai.channels import conversation as conv

		name = frappe.db.get_value("Gateway Event", event_name, "channel_conversation")
		doc = (
			frappe.get_doc("Channel Conversation", name)
			if name
			else conv.get_or_create_conversation(gateway_name, str(context.get("sender_id") or ""))
		)
		if doc is None:
			return
		handoff_conversation(
			doc,
			target=(payload or {}).get("target"),
			summary=str((payload or {}).get("summary") or context.get("message_text") or ""),
			priority=str((payload or {}).get("priority") or "normal"),
			message=(payload or {}).get("text") or None,
		)
	except Exception:
		frappe.log_error(title="Channel handoff from pipeline failed")
