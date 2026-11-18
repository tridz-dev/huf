"""Per-channel consent for SMS and Email (HUFCRM-04a). WhatsApp keeps its Gateway Consent model.

``has_consent(channel, recipient, purpose)`` is the single gate failover and senders call. Rules mirror the
WhatsApp audience purposes: ``marketing`` needs an explicit opt-in; ``utility`` (and ``events``) is allowed
without one. A STOP (opt-out scope ``all``) blocks every purpose, a marketing opt-out blocks only marketing,
and the latest row per recipient wins, so a later opt-in lifts an earlier opt-out. Email also honours a
Gateway Access Entry ``Opted out`` on any Email gateway.
"""

from __future__ import annotations

import re
from typing import Any

import frappe
from frappe import _

from huf.ai.channels import consent_api
from huf.ai.gateway_core.constants import ENTRY_STATE_OPTED_OUT

DOCTYPE = "Channel Consent"
CHANNELS = ("sms", "email")
PURPOSES = ("marketing", "utility", "events")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GATEWAY_PROVIDER = {"email": "Email"}


def normalize_recipient(channel: str, raw: Any) -> str | None:
	"""Digits-only phone (sms) or lower-cased address (email); None when unusable."""
	value = str(raw or "").strip()
	if channel == "sms":
		return consent_api._phone(value)
	if channel == "email":
		value = value.lower()
		return value if _EMAIL.match(value) else None
	return None


def _latest(channel: str, recipient: str) -> dict[str, Any] | None:
	filters = {"channel": channel, "recipient": recipient}
	rows = frappe.get_all(
		DOCTYPE, filters=filters, fields=["value", "scope"], order_by="creation desc, name desc", limit_page_length=1
	)
	return rows[0] if rows else None


def _gateway_opted_out(channel: str, recipient: str) -> bool:
	provider = _GATEWAY_PROVIDER.get(channel)
	if not provider:
		return False
	gateways = frappe.get_all("Gateway", filters={"provider": provider}, pluck="name", limit_page_length=0)
	if not gateways:
		return False
	return bool(
		frappe.get_all(
			"Gateway Access Entry",
			filters={
				"gateway": ["in", gateways],
				"entry_type": "Sender",
				"external_id": recipient,
				"state": ENTRY_STATE_OPTED_OUT,
			},
			pluck="name",
			limit_page_length=1,
		)
	)


def has_consent(channel: str, recipient: Any, purpose: str = "marketing") -> tuple[bool, str]:
	"""(allowed, reason). Reasons: ok, invalid_channel, invalid_purpose, invalid_recipient, opted_out,
	marketing_opted_out, no_opt_in."""
	channel = str(channel or "").lower()
	if channel not in CHANNELS:
		return False, "invalid_channel"
	if purpose not in PURPOSES:
		return False, "invalid_purpose"
	key = normalize_recipient(channel, recipient)
	if key is None:
		return False, "invalid_recipient"
	if _gateway_opted_out(channel, key):
		return False, "opted_out"
	latest = _latest(channel, key)
	if latest and latest["value"] == "opt_out":
		if latest["scope"] == "all":
			return False, "opted_out"
		if purpose == "marketing":
			return False, "marketing_opted_out"
	if purpose == "marketing" and not latest:
		return False, "no_opt_in"
	return True, "ok"


def _insert(channel, recipient, value, scope, source, detail, attested_by=None, note=None) -> None:
	frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"channel": channel,
			"recipient": recipient,
			"value": value,
			"scope": scope,
			"source": source,
			"detail": detail,
			"attested_by": attested_by,
			"attestation_note": note,
			"captured_at": frappe.utils.now_datetime(),
		}
	).insert(ignore_permissions=True)


def _check_channel(channel: str) -> str:
	channel = str(channel or "").lower()
	if channel not in CHANNELS:
		frappe.throw(_("Channel must be one of: {0}.").format(", ".join(CHANNELS)), frappe.ValidationError)
	return channel


def record_opt_out(channel: str, recipient: Any, scope: str = "all", source: str = "inbound", detail: str = "STOP") -> bool:
	"""Internal (inbound STOP handlers): append an opt-out. Not whitelisted. False when the recipient is unusable."""
	channel = _check_channel(channel)
	key = normalize_recipient(channel, recipient)
	if key is None:
		return False
	_insert(channel, key, "opt_out", "all" if scope == "all" else "marketing", source, detail)
	return True


OPT_OUT_KEYWORDS = frozenset({"stop", "stopall", "unsubscribe", "cancel", "end", "quit"})
OPT_IN_KEYWORDS = frozenset({"start", "unstop"})


def handle_keyword(channel: str, sender: Any, text: Any, source: str = "inbound") -> str | None:
	"""Inbound STOP/START handling for a VERIFIED sms/email message. Returns ``opt_out``, ``opt_in`` or None.

	The whole message must be one keyword (case/punctuation-insensitive), so ordinary replies never opt anyone
	out. START/UNSTOP only lifts a prior opt-out. Never raises: a consent write error must not break ingest."""
	word = re.sub(r"[^a-z]", "", str(text or "").strip().lower())
	if word not in OPT_OUT_KEYWORDS and word not in OPT_IN_KEYWORDS:
		return None
	if channel == "email":
		from email.utils import parseaddr

		sender = parseaddr(str(sender or ""))[1] or sender
	try:
		if word in OPT_OUT_KEYWORDS:
			return "opt_out" if record_opt_out(channel, sender, "all", source, word.upper()) else None
		key = normalize_recipient(channel, sender)
		latest = _latest(channel, key) if key else None
		if key and latest and latest["value"] == "opt_out":
			_insert(channel, key, "opt_in", "marketing", source, f"opt-in via {word.upper()}")
			return "opt_in"
	except Exception:  # noqa: BLE001
		frappe.log_error(title="Channel consent keyword failed", message=frappe.get_traceback())
	return None


def _record_opt_in_row(channel: str, key: str, source: str, attester: str, note: str | None) -> str:
	"""created | updated | skipped_opted_out. A standing STOP (any scope) is never overridden by import/API."""
	latest = _latest(channel, key)
	if (latest and latest["value"] == "opt_out") or _gateway_opted_out(channel, key):
		return "skipped_opted_out"
	status = "updated" if latest else "created"
	_insert(channel, key, "opt_in", "marketing", source, f"opt-in via {source}", attester, note)
	return status


@frappe.whitelist(methods=["POST"])
def record_opt_in(channel: str, recipient: str, source: str = "api", note: str | None = None) -> dict[str, Any]:
	"""Record one marketing opt-in for sms/email. Same STOP protection and gating as the WhatsApp API."""
	consent_api._require_manage()
	channel = _check_channel(channel)
	if source not in consent_api.API_SOURCES:
		frappe.throw(_("Source must be one of: {0}.").format(", ".join(consent_api.API_SOURCES)), frappe.ValidationError)
	key = normalize_recipient(channel, recipient)
	if key is None:
		return {"success": False, "channel": channel, "status": "invalid"}
	status = _record_opt_in_row(channel, key, source, frappe.session.user, (note or "").strip() or None)
	return {"success": status != "skipped_opted_out", "channel": channel, "status": status}


@frappe.whitelist(methods=["POST"])
def import_opt_ins(channel: str, rows: Any, attestation_note: str | None = None) -> dict[str, Any]:
	"""Record marketing opt-ins for a list/CSV of phones (sms) or addresses (email), attested by the caller."""
	consent_api._require_manage()
	channel = _check_channel(channel)
	note = (attestation_note or "").strip()
	if not note:
		frappe.throw(_("An attestation note is required: say where and how these opt-ins were collected."), frappe.ValidationError)
	counts = {"created": 0, "updated": 0, "skipped_opted_out": 0, "invalid": 0}
	seen: set[str] = set()
	for raw in consent_api._raw_items(rows):
		key = normalize_recipient(channel, raw)
		if key is None:
			counts["invalid"] += 1
			continue
		if key in seen:
			continue
		seen.add(key)
		counts[_record_opt_in_row(channel, key, "import", frappe.session.user, note)] += 1
	return {"success": True, "channel": channel, **counts}
