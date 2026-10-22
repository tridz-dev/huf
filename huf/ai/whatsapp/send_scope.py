# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Who an agent may message over WhatsApp, and how much (WP-10, A-002).

A prompt-injected agent must never be able to reach arbitrary numbers or spam. By default an agent can
send only to the contact of its current conversation. Each Gateway can widen that (an explicit
allow-list, any Approved Access Entry, or any number) and sets per-run and rolling-24h caps. All of it
is read server-side from the run's own Gateway; nothing here is controllable from tool arguments.

Refusals are JSON tool results with a stable ``error`` code (``recipient_not_permitted`` or
``send_cap_exceeded``) and, for caps, ``retry_after`` (seconds; null for the per-run cap, which only a
new run resets). Caps count the durable ``WhatsApp Send Key`` claims (Sent and in-flight); failed,
refused and deduplicated sends never count.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any, Optional

import frappe
from frappe.utils import add_to_date, now_datetime

SCOPES = ("Current contact", "Allow-list", "Approved contacts", "Any number")
DEFAULT_SCOPE = SCOPES[0]
DEFAULT_PER_RUN = 20
DEFAULT_PER_DAY = 200
DAY_SECONDS = 24 * 3600
_KEY_DOCTYPE = "WhatsApp Send Key"
_FIELDS = ["agent_recipient_scope", "agent_recipient_allowlist", "agent_send_cap_per_run", "agent_send_cap_per_day"]


def _normalize(raw: Any) -> str:
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	return bridge.normalize_phone(raw)


def _entries(text: Any) -> list[str]:
	return [part.strip() for part in re.split(r"[,;\n]+", str(text or "")) if part.strip()]


def parse_allowlist(text: Any) -> list[str]:
	"""Normalised, de-duplicated phone numbers of an allow-list field (invalid entries dropped)."""
	seen: list[str] = []
	for entry in _entries(text):
		number = _normalize(entry)
		if number.isdigit() and 7 <= len(number) <= 15 and number not in seen:
			seen.append(number)
	return seen


def invalid_allowlist_entries(text: Any) -> list[str]:
	return [e for e in _entries(text) if _normalize(e) not in parse_allowlist(e)]


def _cap(value: Any, default: int) -> int:
	try:
		return max(int(value), 0) if value not in (None, "") else default
	except (TypeError, ValueError):
		return default


def settings(gateway: str) -> dict:
	"""The gateway's send scope and caps. Fails closed: any error means the narrowest scope and default caps."""
	try:
		row = frappe.db.get_value("Gateway", gateway, _FIELDS, as_dict=True) or {}
	except Exception:
		row = {}
	scope = row.get("agent_recipient_scope") or DEFAULT_SCOPE
	return {
		"scope": scope if scope in SCOPES else DEFAULT_SCOPE,
		"allowlist": parse_allowlist(row.get("agent_recipient_allowlist")),
		"per_run": _cap(row.get("agent_send_cap_per_run"), DEFAULT_PER_RUN),
		"per_day": _cap(row.get("agent_send_cap_per_day"), DEFAULT_PER_DAY),
	}


def current_contact(run_id: Optional[str]) -> str:
	"""The WhatsApp contact (normalised) of the run's conversation, or '' when there is none."""
	if not run_id:
		return ""
	try:
		conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
		external = frappe.db.get_value("Agent Conversation", conversation, "external_id") if conversation else ""
		return _normalize(external)
	except Exception:
		return ""


def _is_approved(gateway: str, number: str) -> bool:
	from huf.ai import gateway_service

	try:
		return bool(gateway_service._has_access_entry(SimpleNamespace(name=gateway, provider="WhatsApp"), "Sender", number))
	except Exception:
		return False


def _refusal(error: str, message: str, **extra: Any) -> str:
	return json.dumps({"success": False, "error": error, "message": message, **extra}, default=str)


def check_recipient(gateway: str, run_id: Optional[str], recipient: str, contact: str = "") -> Optional[str]:
	"""Refusal JSON when ``recipient`` is outside the gateway's scope for this run, else None."""
	number = _normalize(recipient)
	conf = settings(gateway)
	own = current_contact(run_id) or _normalize(contact)  # a flow run's contact is the sender that triggered it
	if own and number == own:
		return None
	scope = conf["scope"] if conf["scope"] in SCOPES else DEFAULT_SCOPE
	allowed = (
		scope == "Any number"
		or (scope == "Allow-list" and number in conf["allowlist"])
		or (scope == "Approved contacts" and bool(number) and _is_approved(gateway, number))
	)
	if allowed:
		return None
	hint = {
		"Current contact": "this gateway lets agents message only the person in the current conversation",
		"Allow-list": "this number is not on the gateway's allowed-recipient list",
		"Approved contacts": "this number is not an Approved sender on the gateway",
	}[scope]
	return _refusal(
		"recipient_not_permitted",
		f"That recipient is not permitted: {hint}. Ask a gateway admin to widen the recipient scope if this is intended.",
		scope=scope,
	)


def check_caps(gateway: str, run_id: Optional[str]) -> Optional[str]:
	"""Refusal JSON when this send (already claimed) pushes the run or the rolling day over its cap."""
	conf = settings(gateway)
	live = {"status": ["in", ["Pending", "Sent"]]}
	if conf["per_run"] and run_id:
		used = frappe.db.count(_KEY_DOCTYPE, {"gateway": gateway, "agent_run": run_id, **live})
		if used > conf["per_run"]:
			return _refusal(
				"send_cap_exceeded",
				f"This run has already sent its limit of {conf['per_run']} WhatsApp messages. No more are sent in this run.",
				cap="run", limit=conf["per_run"], retry_after=None,
			)
	if conf["per_day"]:
		since = add_to_date(now_datetime(), hours=-24)
		rows = frappe.get_all(
			_KEY_DOCTYPE, filters={"gateway": gateway, "claimed_at": [">=", since], **live},
			pluck="claimed_at", order_by="claimed_at asc", limit_page_length=conf["per_day"] + 1,
		)
		if len(rows) > conf["per_day"]:
			oldest = rows[len(rows) - conf["per_day"] - 1] if len(rows) > conf["per_day"] else rows[0]
			retry = int((oldest - since).total_seconds())
			return _refusal(
				"send_cap_exceeded",
				f"This gateway reached its limit of {conf['per_day']} agent WhatsApp messages in 24 hours. Try again later.",
				cap="day", limit=conf["per_day"], retry_after=max(1, min(retry, DAY_SECONDS)),
			)
	return None
