"""Frappe CRM adapter: find/create a CRM Lead for a WhatsApp contact and hand conversations over as Lead + note.

Built against CRM's schema only (no import of CRM code, no dependency on its WhatsApp doctypes). Every
field is guarded with ``get_meta().has_field`` so schema drift never breaks a handoff.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

from huf.ai.channels.adapters import ChannelAdapter

LEAD = "CRM Lead"
NOTE = "FCRM Note"
SOURCE_DOCTYPE = "CRM Lead Source"
SOURCE_WHATSAPP = "WhatsApp"
SOURCE_AD = "Advertisement"


def normalize_phone(value: str | None) -> str:
	return re.sub(r"\D", "", str(value or ""))


def _has(doctype: str, field: str) -> bool:
	try:
		return bool(frappe.get_meta(doctype).has_field(field))
	except Exception:
		return False


def _only_fields(doctype: str, values: dict[str, Any]) -> dict[str, Any]:
	return {k: v for k, v in values.items() if v not in (None, "") and _has(doctype, k)}


def find_lead(phone: str) -> str | None:
	digits = normalize_phone(phone)
	if not digits:
		return None
	tail = digits[-10:]
	for field in ("mobile_no", "phone"):
		if not _has(LEAD, field):
			continue
		rows = frappe.get_all(LEAD, filters={field: ["like", f"%{tail}"]}, fields=["name", field], order_by="creation desc", limit_page_length=20)
		for row in rows:
			cand = normalize_phone(row.get(field))
			if cand and cand[-10:] == tail:
				return row["name"]
	return None


def _source_exists(source: str) -> bool:
	try:
		return bool(frappe.db.exists(SOURCE_DOCTYPE, source))
	except Exception:
		return False


def referral_for(conversation) -> dict[str, Any]:
	"""CTWA referral (headline/source_url/source_id) of the latest inbound event of the conversation, or {}."""
	try:
		rows = frappe.get_all(
			"Gateway Event",
			filters={"channel_conversation": conversation.name},
			fields=["raw_payload"],
			order_by="creation desc",
			limit_page_length=20,
		)
		for row in rows:
			raw = row.get("raw_payload")
			raw = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
			ref = raw.get("referral") if isinstance(raw, dict) else None
			if isinstance(ref, dict) and ref:
				return {k: str(ref[k])[:300] for k in ("headline", "source_url", "source_id", "source_type") if ref.get(k)}
	except Exception:
		return {}
	return {}


def create_lead(phone: str, name: str | None = None, email: str | None = None, referral: dict | None = None) -> str:
	digits = normalize_phone(phone)
	first = (name or "").strip() or (f"+{digits}" if digits else "WhatsApp contact")
	source = None
	if _has(LEAD, "source"):
		if referral and _source_exists(SOURCE_AD):
			source = SOURCE_AD
		elif _source_exists(SOURCE_WHATSAPP):
			source = SOURCE_WHATSAPP
	values = _only_fields(
		LEAD,
		{"first_name": first, "lead_name": first, "mobile_no": f"+{digits}" if digits else None, "email": (email or "").strip() or None, "source": source},
	)
	if not _has(LEAD, "mobile_no") and digits:
		values.update(_only_fields(LEAD, {"phone": f"+{digits}"}))
	doc = frappe.get_doc({"doctype": LEAD, **values})
	doc.insert(ignore_permissions=True)
	return doc.name


def add_note(lead: str, title: str, content: str) -> str | None:
	"""FCRM Note on the lead, else a Comment. Returns the note name (None for a Comment)."""
	from huf.ai.channels.run_as import channel_inbound

	with channel_inbound():
		return _add_note(lead, title, content)


def _add_note(lead: str, title: str, content: str) -> str | None:
	content = (content or "")[:5000]
	try:
		if frappe.db.exists("DocType", NOTE) and _has(NOTE, "reference_doctype"):
			values = _only_fields(NOTE, {"title": title[:140], "content": content, "reference_doctype": LEAD, "reference_docname": lead})
			doc = frappe.get_doc({"doctype": NOTE, **values})
			doc.insert(ignore_permissions=True)
			return doc.name
	except Exception:
		frappe.log_error(title="CRM adapter: FCRM Note failed, falling back to Comment")
	frappe.get_doc(LEAD, lead).add_comment("Comment", content)
	return None


def _transcript(conversation) -> str:
	preview = conversation.get("last_message_preview") or ""
	return f"Last message: {preview}" if preview else ""


class Adapter(ChannelAdapter):
	name = "crm"

	def lookup_customer(self, phone: str) -> dict[str, Any] | None:
		name = find_lead(phone)
		return {"doctype": LEAD, "name": name} if name else None

	def handoff(self, conversation, summary: str = "", priority: str = "normal") -> tuple[str | None, str | None]:
		existing = conversation.get("handoff_name") if conversation.get("handoff_doctype") == LEAD else None
		referral = referral_for(conversation)
		lead = existing or find_lead(conversation.contact_handle) or create_lead(
			conversation.contact_handle, conversation.get("contact_name"), referral=referral
		)
		parts = [f"<p><b>WhatsApp handoff</b> (priority: {frappe.utils.escape_html(priority)})</p>"]
		if summary:
			parts.append(f"<p><b>AI summary:</b> {frappe.utils.escape_html(summary)}</p>")
		transcript = _transcript(conversation)
		if transcript:
			parts.append(f"<p>{frappe.utils.escape_html(transcript)}</p>")
		if referral:
			parts.append("<p><b>Click-to-WhatsApp ad:</b> " + frappe.utils.escape_html(", ".join(f"{k}={v}" for k, v in referral.items())) + "</p>")
		add_note(lead, "WhatsApp handoff", "".join(parts))
		return LEAD, lead

	def append_inbound(self, conversation, text: str, event: str | None = None) -> None:
		if not text or not conversation.get("handoff_name"):
			return
		add_note(conversation.handoff_name, "WhatsApp message", f"<p>{frappe.utils.escape_html(text)}</p>")

	def on_human_reply(self, doc, conversation) -> bool:
		return False
