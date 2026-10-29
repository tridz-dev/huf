"""Frappe Helpdesk handoff adapter: a handed-off conversation becomes an HD Ticket.

Built against Helpdesk's documented schema (HD Ticket: subject, raised_by, description, priority, status,
customer, contact; Communication linked by reference_doctype/name). Every optional field is guarded with
``frappe.get_meta("HD Ticket").has_field``. Helpdesk is optional: this module never imports it.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

from huf.ai.channels.adapters import ChannelAdapter

DOCTYPE = "HD Ticket"
PRIORITY_MAP = {"low": "Low", "normal": "Medium", "high": "High", "urgent": "Urgent"}
CLOSED_STATUSES = ("Closed", "Resolved")
_MAX_TRANSCRIPT = 50


def _digits(value: str | None) -> str:
	return re.sub(r"\D", "", value or "")


def _has_field(doctype: str, fieldname: str) -> bool:
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


def _transcript(conversation) -> str:
	"""Customer messages of the conversation (oldest first), via the Activity read API with a direct fallback."""
	messages: list[dict[str, Any]] = []
	try:
		from huf.ai.channels.api import get_conversation

		res = get_conversation(conversation.name)
		messages = res.get("messages") or [] if isinstance(res, dict) else []
	except Exception:
		messages = []
	if not messages:
		rows = frappe.get_all(
			"Gateway Event",
			filters={"channel_conversation": conversation.name},
			fields=["message_text"],
			order_by="creation asc, name asc",
			limit_page_length=_MAX_TRANSCRIPT,
		)
		messages = [{"direction": "in", "text": r.get("message_text") or ""} for r in rows]
	lines = []
	for m in messages[-_MAX_TRANSCRIPT:]:
		text = (m.get("text") or "").strip()
		if text:
			lines.append(f"{'Customer' if m.get('direction') == 'in' else 'AI'}: {text}")
	return "\n".join(lines)


def _contact_email(contact: str | None) -> str | None:
	if not contact:
		return None
	try:
		return frappe.db.get_value("Contact", contact, "email_id") or None
	except Exception:
		return None


def _html(text: str) -> str:
	return frappe.utils.escape_html(text).replace("\n", "<br>")


def create_ticket(conversation, subject_hint: str = "", summary: str = "", priority: str = "normal", extra_description: str = ""):
	"""Create an HD Ticket for ``conversation`` (no Communication). Returns the saved doc."""
	label = conversation.get("contact_name") or conversation.get("contact_handle") or ""
	raised_by = _contact_email(conversation.get("contact")) or f"{_digits(conversation.get('contact_handle')) or 'unknown'}@whatsapp.invalid"
	values: dict[str, Any] = {
		"doctype": DOCTYPE,
		"subject": (subject_hint or f"WhatsApp: {label}")[:140],
		"raised_by": raised_by,
		"description": _html(summary or extra_description or f"WhatsApp conversation with {label}"),
	}
	prio = PRIORITY_MAP.get((priority or "normal").lower(), "Medium")
	if _has_field(DOCTYPE, "priority"):
		values["priority"] = prio
	if conversation.get("contact") and _has_field(DOCTYPE, "contact"):
		values["contact"] = conversation.get("contact")
	if _has_field(DOCTYPE, "huf_channel_conversation"):
		values["huf_channel_conversation"] = conversation.name
	return frappe.get_doc(values).insert(ignore_permissions=True)


def _add_communication(ticket_name: str, content: str, sender: str, subject: str = "", sent_or_received: str = "Received"):
	from huf.ai.channels.run_as import channel_inbound

	with channel_inbound():
		return _insert_communication(ticket_name, content, sender, subject, sent_or_received)


def _insert_communication(ticket_name: str, content: str, sender: str, subject: str, sent_or_received: str):
	return frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Chat",
			"sent_or_received": sent_or_received,
			"subject": subject[:140],
			"content": content,
			"sender": sender,
			"reference_doctype": DOCTYPE,
			"reference_name": ticket_name,
		}
	).insert(ignore_permissions=True)


class Adapter(ChannelAdapter):
	name = "helpdesk"

	def handoff(self, conversation, summary: str = "", priority: str = "normal"):
		ticket = create_ticket(conversation, summary=summary, priority=priority)
		parts = []
		if summary:
			parts.append(f"AI summary:\n{summary}")
		transcript = _transcript(conversation)
		if transcript:
			parts.append(f"Transcript:\n{transcript}")
		if parts:
			_add_communication(ticket.name, _html("\n\n".join(parts)), ticket.raised_by, ticket.subject)
		return DOCTYPE, ticket.name

	def lookup_customer(self, phone: str):
		digits = _digits(phone)
		if len(digits) < 6:
			return None
		rows = frappe.get_all(
			"Contact Phone", filters={"phone": ["like", f"%{digits[-10:]}"]}, fields=["parent"], limit_page_length=1
		)
		if not rows:
			return None
		return {"doctype": "Contact", "name": rows[0]["parent"], "email": _contact_email(rows[0]["parent"])}

	def append_inbound(self, conversation, text: str, event: str | None = None) -> None:
		if not (conversation.get("handoff_doctype") == DOCTYPE and conversation.get("handoff_name")):
			return
		sender = frappe.db.get_value(DOCTYPE, conversation.handoff_name, "raised_by") or "unknown@whatsapp.invalid"
		_add_communication(conversation.handoff_name, _html(text), sender, "WhatsApp message")

	def on_human_reply(self, doc, conversation) -> bool:
		return False


def on_ticket_update(doc, method=None) -> None:
	"""doc_events HD Ticket on_update: a Closed/Resolved ticket closes its handed-off conversation."""
	if doc.get("status") not in CLOSED_STATUSES:
		return
	rows = frappe.get_all(
		"Channel Conversation",
		filters={"handoff_doctype": DOCTYPE, "handoff_name": doc.name, "status": "handed_off"},
		pluck="name",
		limit_page_length=5,
	)
	for name in rows:
		frappe.db.set_value("Channel Conversation", name, "status", "closed")
