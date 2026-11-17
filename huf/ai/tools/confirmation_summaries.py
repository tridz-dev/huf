"""Per-tool confirmation summarizers: ``fn(args, user) -> {action, recipient_count, template, channel, sample}``.

Referenced by ``Agent Tool Function.confirmation_summary_path``. Return ``recipient_count=None`` when the
audience cannot be resolved; for an outbound tool the confirmation gate then refuses to park (fail closed).
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import cint

_SAMPLE_LEN = 200
_WA_SEND_ACTIONS = {
	"send_message", "send_media", "send_image", "send_video", "send_audio", "send_document", "send_sticker",
	"send_location", "send_contact", "send_reaction", "send_buttons", "send_list", "send_cta_url", "send_template",
}


def _sample(args: dict):
	for k in ("message", "text", "body", "caption", "content"):
		if args.get(k) not in (None, ""):
			return str(args[k])[:_SAMPLE_LEN]
	return None


def _listlen(v):
	if isinstance(v, str):
		try:
			v = json.loads(v)
		except ValueError:
			return 1 if v.strip() else None
	if isinstance(v, (list, tuple, set)):
		return len(v)
	return 1 if v else None


def whatsapp(args: dict, user: str | None = None) -> dict:
	"""``whatsapp`` tool: one recipient per send_* action (the conversation contact when ``to`` is omitted)."""
	args = args or {}
	action = str(args.get("action") or "")
	is_send = action in _WA_SEND_ACTIONS
	return {
		"action": action or "whatsapp",
		"recipient_count": 1 if is_send else 0,
		"template": args.get("template_name") if action == "send_template" else None,
		"channel": "whatsapp",
		"sample": _sample(args),
	}


def whatsapp_broadcast(args: dict, user: str | None = None) -> dict:
	"""Broadcast start/create tools: count the queued recipients of the named WhatsApp Broadcast."""
	args = args or {}
	name = args.get("broadcast") or args.get("broadcast_name") or args.get("name")
	count, template = None, args.get("template") or args.get("template_name")
	if name and frappe.db.exists("WhatsApp Broadcast", name):
		count = frappe.db.count(
			"WhatsApp Broadcast Recipient", {"broadcast": name, "status": ("in", ("queued", "deferred"))}
		)
		template = template or frappe.db.get_value("WhatsApp Broadcast", name, "template")
	elif args.get("audience") or args.get("audiences"):
		count = None  # audience size unknown until resolved: caller fails closed
	return {
		"action": str(args.get("action") or "whatsapp broadcast"),
		"recipient_count": count,
		"template": template,
		"channel": "whatsapp",
		"sample": _sample(args),
	}


def single_target(args: dict, user: str | None = None) -> dict:
	"""Channel/thread posts and single-chat sends (Slack, Discord, Google Chat, Telegram, Messenger): one target."""
	args = args or {}
	rec = args.get("recipient")
	count = _listlen(rec) if rec is not None else 1
	if isinstance(rec, str) and rec.strip().startswith("{"):
		try:
			spec = json.loads(rec)
			if "role" in spec:
				count = cint(frappe.db.count("Has Role", {"role": spec["role"], "parenttype": "User"})) or None
		except ValueError:
			count = None
	return {
		"action": str(args.get("action") or "send"),
		"recipient_count": count,
		"template": None,
		"channel": None,
		"sample": _sample(args),
	}


def whatsapp_broadcast_start(args: dict, user: str | None = None) -> dict:
	"""``whatsapp_broadcast_start``: the real queued recipient count, template, channel and audience(s) of the
	named broadcast. ``recipient_count`` stays None (so the gate refuses to park) when the broadcast cannot be
	resolved or the user cannot read it."""
	from huf.ai.whatsapp.broadcast import api as broadcast_api

	args = args or {}
	name = args.get("broadcast")
	scheduled = args.get("scheduled_at")
	out = {
		"action": f"Schedule WhatsApp broadcast for {scheduled}" if scheduled else "Start WhatsApp broadcast",
		"recipient_count": None, "template": None, "channel": "whatsapp", "sample": None,
	}
	try:
		row = broadcast_api._require_broadcast_read(name)
	except frappe.PermissionError:
		return out
	if row.get("error") or row.get("status") not in ("Draft", "Paused"):
		return out
	audiences = frappe.get_all(
		"WhatsApp Broadcast Audience", filters={"parent": name, "exclude": 0}, pluck="audience", limit_page_length=20,
		parent_doctype="WhatsApp Broadcast",
	)
	attested = bool(row.get("consent_attested") and row.get("consent_attested_by"))
	out.update(
		recipient_count=int(broadcast_api._queued_count(name) or 0),
		template=row.get("template_name") or row.get("template"),
		sample=(
			f"{row.get('title')} | audience: {', '.join(audiences) or 'manual list'} | consent "
			+ (f"attested by {row.get('consent_attested_by')}" if attested else "NOT ATTESTED (will be refused)")
		)[:_SAMPLE_LEN],
	)
	return out
