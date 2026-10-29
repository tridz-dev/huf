"""Channel Conversation upsert helpers (one open row per gateway + contact handle)."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

WINDOW_HOURS = 24
_PREVIEW_CHARS = 140
_PROVIDER_CHANNEL = {
	"whatsapp": "whatsapp",
	"telegram": "telegram",
	"slack": "slack",
	"microsoft teams": "teams",
}


def channel_for_provider(provider: str | None) -> str | None:
	return _PROVIDER_CHANNEL.get((provider or "").strip().lower())


def _open_name(gateway: str, handle: str) -> str | None:
	rows = frappe.get_all(
		"Channel Conversation",
		filters={"gateway": gateway, "contact_handle": handle, "status": ["!=", "closed"]},
		pluck="name",
		order_by="creation desc",
		limit_page_length=1,
	)
	return rows[0] if rows else None


def get_or_create_conversation(gateway: str, handle: str, channel: str | None = None, contact_name: str | None = None, **fields):
	"""Return the open Channel Conversation for (gateway, handle), creating it when absent."""
	handle = (handle or "").strip()
	if not gateway or not handle:
		return None
	name = _open_name(gateway, handle)
	if name:
		doc = frappe.get_doc("Channel Conversation", name)
		if contact_name and not doc.contact_name:
			doc.db_set("contact_name", contact_name[:255], update_modified=False)
		return doc
	if not channel:
		channel = channel_for_provider(frappe.db.get_value("Gateway", gateway, "provider")) or "whatsapp"
	doc = frappe.get_doc(
		{
			"doctype": "Channel Conversation",
			"gateway": gateway,
			"channel": channel,
			"contact_handle": handle,
			"contact_name": (contact_name or "")[:255],
			"status": "ai",
			**fields,
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:  # concurrent insert won the race
		name = _open_name(gateway, handle)
		if not name:
			raise
		return frappe.get_doc("Channel Conversation", name)
	return doc


def _touch(doc, ts_field: str, when, preview: str | None) -> None:
	when = get_datetime(when) if when else now_datetime()
	values = {ts_field: when, "message_count": (doc.message_count or 0) + 1}
	if preview:
		values["last_message_preview"] = " ".join(str(preview).split())[:_PREVIEW_CHARS]
	doc.db_set(values, update_modified=True)


def touch_inbound(conversation, when=None, preview: str | None = None):
	"""Record an inbound message: stamps last_inbound_at (opens the 24h window)."""
	doc = _as_doc(conversation)
	if doc:
		_touch(doc, "last_inbound_at", when, preview)
	return doc


def touch_outbound(conversation, when=None, preview: str | None = None):
	"""Record an outbound message: stamps last_outbound_at."""
	doc = _as_doc(conversation)
	if doc:
		_touch(doc, "last_outbound_at", when, preview)
	return doc


def _as_doc(conversation):
	if not conversation:
		return None
	if isinstance(conversation, str):
		return frappe.get_doc("Channel Conversation", conversation)
	return conversation


def is_within_24h(conversation, now=None) -> bool:
	"""True when the customer's last inbound message is under 24h old (free-form replies allowed)."""
	doc = _as_doc(conversation)
	last = doc.get("last_inbound_at") if doc else None
	if not last:
		return False
	now = get_datetime(now) if now else now_datetime()
	return get_datetime(last) > add_to_date(now, hours=-WINDOW_HOURS)
