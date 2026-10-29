"""Hooks for handed-off conversations: skip the AI inbound, and relay human replies outbound."""

from __future__ import annotations

import frappe

from huf.ai.channels.pipeline import Decision


def _conversation_for(context: dict):
	event = context.get("event")
	name = frappe.db.get_value("Gateway Event", event, "channel_conversation") if event else None
	if name:
		return frappe.get_doc("Channel Conversation", name)
	inner = context.get("context") or {}
	if not context.get("gateway") or not inner.get("sender_id"):
		return None
	rows = frappe.get_all(
		"Channel Conversation",
		filters={"gateway": context.get("gateway"), "contact_handle": str(inner.get("sender_id") or ""), "status": ["!=", "closed"]},
		pluck="name",
		limit_page_length=1,
	)
	return frappe.get_doc("Channel Conversation", rows[0]) if rows else None


def handed_off_hook(context: dict) -> Decision | None:
	"""Pre-route hook: a handed-off conversation never reaches the AI; its inbound goes to the linked doc."""
	doc = _conversation_for(context)
	if doc is None or doc.status != "handed_off":
		return None
	text = str((context.get("context") or {}).get("message_text") or "")
	if text and doc.handoff_doctype and doc.handoff_name:
		try:
			from huf.ai.channels import adapters

			adapters.adapter_for_conversation(doc).append_inbound(doc, text, context.get("event"))
		except Exception:
			frappe.log_error(title="Channel handoff append_inbound failed")
	return Decision(action="drop", payload={"reason": "handed_off", "conversation": doc.name})


def _comment(doc_type: str, doc_name: str, text: str) -> None:
	try:
		frappe.get_doc(doc_type, doc_name).add_comment("Comment", text)
	except Exception:
		frappe.log_error(title="Channel reply: could not record failure comment")


def communication_after_insert(doc, method=None) -> None:
	"""A Sent Communication on the linked doc of a handed-off conversation is relayed to the customer."""
	if doc.get("sent_or_received") != "Sent" or not doc.get("reference_doctype") or not doc.get("reference_name"):
		return
	rows = frappe.get_all(
		"Channel Conversation",
		filters={"handoff_doctype": doc.reference_doctype, "handoff_name": doc.reference_name, "status": "handed_off"},
		pluck="name",
		limit_page_length=1,
	)
	if not rows:
		return
	conversation = frappe.get_doc("Channel Conversation", rows[0])
	try:
		from huf.ai.channels import adapters, reply_api

		if adapters.adapter_for_conversation(conversation).on_human_reply(doc, conversation):
			return
		text = frappe.utils.strip_html_tags(doc.get("content") or "").strip()
		if not text:
			return
		res = reply_api.deliver_reply(conversation, text=text)
	except Exception as exc:
		res = {"status": "failed", "error": type(exc).__name__}
	if res.get("status") != "sent":
		reason = "the 24-hour window is closed; send an approved template" if res.get("needs_template") else res.get("error") or "unknown error"
		_comment(doc.reference_doctype, doc.reference_name, f"WhatsApp reply not delivered: {reason}")
