# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Huf's built-in pre-send steps (H-W2-02), run by :mod:`huf.ai.channels.guard` before any app hook.

Each step takes the request dict and answers ``{"allow": True}`` or ``{"allow": False, "reason": code}``.
They only read. Anything they raise is turned into a ``hook_error`` block by the chain.

Order: recipient, consent, template. ``header`` is not part of the app hook request: the chain adds it for
built-in steps only, from ``guard.evaluate(..., header=)``; None means "use the template's default media".
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import frappe

MEDIA_HOSTS_CONF = (
	"huf_send_media_hosts"  # list or comma string of hosts (``host:port`` for a port other than 443)
)
MEDIA_TYPES = ("image", "video", "document")
BLOCKING_EVENTS = frozenset({"FLAGGED"})
_E164 = re.compile(r"\+[1-9][0-9]{6,14}")
_SEPARATORS = re.compile(r"[ ()\-]")


def _allow() -> dict:
	return {"allow": True}


def _block(reason: str) -> dict:
	return {"allow": False, "reason": reason}


def normalise_recipient(raw: Any) -> str | None:
	"""``+<digits>`` (E.164), or None. A number without ``+`` or ``00`` is ambiguous and rejected."""
	if not isinstance(raw, str):
		return None
	value = _SEPARATORS.sub("", raw)
	if value.startswith("00"):
		value = "+" + value[2:]
	return value if _E164.fullmatch(value) else None


def check_recipient(request: dict) -> dict:
	if request.get("channel") == "email":
		return _allow()  # validated by the consent step
	if request.get("channel") == "whatsapp":
		from huf.ai.gateway_adapters import whatsapp_bridge as bridge

		if bridge.is_bsuid(request.get("recipient")):
			return _block("bsuid_recipient")
	return _allow() if normalise_recipient(request.get("recipient")) else _block("bad_recipient")


def check_consent(request: dict) -> dict:
	"""Huf's own opt-out records. An app's consent rules stay in its ``huf_pre_send_hooks``."""
	channel, recipient = request.get("channel"), request.get("recipient")
	marketing = request.get("category") != "service"
	if channel == "whatsapp":
		from huf.ai.whatsapp import account_events, outbound_policy

		gateway = request.get("gateway")
		if not gateway:
			return _block("blocked_by_hook")
		digits = normalise_recipient(recipient)[1:]
		try:
			outbound_policy.check_recipient(gateway, digits)
		except outbound_policy.OutboundRefused as error:
			return _block(error.code)
		if marketing and not account_events.is_marketing_allowed(gateway, digits):
			return _block("marketing_opted_out")
		return _allow()

	from huf.ai.channels import channel_consent

	allowed, reason = channel_consent.has_consent(channel, recipient, "marketing" if marketing else "utility")
	if allowed:
		return _allow()
	return _block("bad_recipient" if reason == "invalid_recipient" else reason)


def check_template(request: dict) -> dict:
	"""G5: a WhatsApp template is sent only when its row exists and everything known says APPROVED."""
	template, header = request.get("template"), request.get("header")
	if request.get("channel") != "whatsapp" or not template:
		return _block("header_invalid") if header is not None else _allow()

	found = _load_template(request.get("gateway"), template)
	if not found:
		return _block("template_not_approved")
	docname, req = found
	row = req["tpl"]
	if str(row.get("status") or "").upper() != "APPROVED" or _state_blocks(
		row.get("whatsapp_account"), docname
	):
		return _block("template_not_approved")

	if str(row.get("category") or "").upper() == "MARKETING":
		from huf.ai.whatsapp import outbound_policy

		try:
			outbound_policy.check_template(
				request.get("gateway"), normalise_recipient(request.get("recipient"))[1:], row
			)
		except outbound_policy.OutboundRefused as error:
			return _block(error.code)

	if not _params_match(req, request.get("token_names")):
		return _block("template_params_invalid")
	reason = _header_problem(req, header)
	return _block(reason) if reason else _allow()


def _load_template(gateway: str | None, template: str) -> tuple[str, dict] | None:
	"""(docname, send requirements) of ``template`` on the gateway's own account, else None."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.whatsapp.broadcast.checks.template_check import template_requirements

	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account") if gateway else None
	if not account or not frappe.db.exists("DocType", "WhatsApp Templates"):
		return None
	try:
		docname = bridge._template_docname(account, template)
	except bridge.BridgeError:  # several languages share the name: the template is not identified
		return None
	req = template_requirements(docname)
	if not req or req["tpl"].get("whatsapp_account") != account:
		return None
	return docname, req


def _state_blocks(account: str, docname: str) -> bool:
	"""True when the webhook/sync state contradicts APPROVED. A read error raises, so it blocks."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if not frappe.db.exists("DocType", bridge.STATE_DOCTYPE):
		return False
	state = frappe.db.get_value(
		bridge.STATE_DOCTYPE, bridge.state_key(account, docname), ["status", "last_event"], as_dict=True
	)
	if not state:
		return False
	status = str(state.get("status") or "").upper()
	return status not in ("", "APPROVED") or str(state.get("last_event") or "").upper() in BLOCKING_EVENTS


def _params_match(req: dict, token_names: Any) -> bool:
	"""One token per body variable, text header variable and required button. Carousels cannot be checked."""
	if not isinstance(token_names, list) or req["tv"].get("carousel"):
		return False
	header = req.get("header") or {}
	expected = (
		len(req["body"]) + (header.get("type") == "TEXT") + sum(bool(b["required"]) for b in req["buttons"])
	)
	return len(token_names) == expected


def _header_problem(req: dict, header: Any) -> str | None:
	kind = str(req["tv"].get("header_type") or "").lower()
	if kind == "location":
		ok = (
			isinstance(header, dict)
			and header.get("type") == "location"
			and header.get("latitude") is not None
			and header.get("longitude") is not None
		)
		return None if ok else "header_invalid"
	if kind not in MEDIA_TYPES:
		return None if header is None else "header_invalid"
	if header is None:
		# only an image template can fall back to its own sample link (as the bridge does)
		link = req["tpl"].get("sample") if kind == "image" else None
	elif isinstance(header, dict) and header.get("type") == kind:
		link = header.get("link")
	else:
		link = None
	if not isinstance(link, str) or not link:
		return "header_invalid"
	return None if media_host_allowed(link) else "media_host_not_allowed"


def media_host_allowed(link: Any) -> bool:
	"""https, no userinfo, and a host listed in site config ``huf_send_media_hosts``. Nothing listed allows nothing."""
	if not isinstance(link, str) or any(c.isspace() or c == "\\" for c in link):
		return False
	try:
		parts = urlsplit(link)
		port = parts.port
	except ValueError:
		return False
	if parts.scheme != "https" or "@" in parts.netloc or not parts.hostname:
		return False
	host = parts.hostname if port in (None, 443) else f"{parts.hostname}:{port}"
	raw = frappe.conf.get(MEDIA_HOSTS_CONF) or []
	hosts = raw.split(",") if isinstance(raw, str) else raw
	return host in {str(h).strip().lower() for h in hosts}


STEPS = (
	("recipient", check_recipient),
	("consent", check_consent),
	("template", check_template),
)
