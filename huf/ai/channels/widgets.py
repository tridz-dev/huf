"""Opt-in widgets for WhatsApp gateways: click-to-chat link, web widget snippet, ``[ref:...]`` opt-in hook.

No QR library is a dependency of Huf (neither Python nor npm), so ``qr_svg`` is always None here; the
frontend shows the wa.me link. Both whitelisted calls need ``system.integrations.manage``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import frappe
from frappe import _

from huf.ai.channels.pipeline import Decision
from huf.ai.channels.consent_api import _phone, _record, _require_manage, _require_whatsapp_gateway

_REF_RE = re.compile(r"\[ref:([A-Za-z0-9_.\-]{1,64})\]")
SCRIPT_PATH = "/assets/huf/js/huf-wa-widget.js"


def _gateway_number(gateway: str, phone: str | None) -> str:
	number = _phone(phone) if phone else None
	if number is None:
		from huf.ai.whatsapp import token_check

		cached = frappe.cache().get_value(token_check._result_key(gateway)) or {}
		number = _phone(((cached.get("phone") or {}).get("display")))
	if number is None:
		frappe.throw(_("The gateway phone number is not known yet. Run the token check or pass the number."), frappe.ValidationError)
	return number


def _prefill(prefill: str | None, ref: str | None) -> str:
	text = (prefill or "").strip()
	ref = (ref or "").strip()
	if ref:
		if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", ref):
			frappe.throw(_("Ref may only contain letters, digits, dot, dash and underscore (max 64)."), frappe.ValidationError)
		text = f"{text} [ref:{ref}]".strip()
	return text


def build_wa_me_url(number: str, prefill: str | None = None, ref: str | None = None) -> str:
	url = f"https://wa.me/{number}"
	text = _prefill(prefill, ref)
	return f"{url}?text={quote(text, safe='')}" if text else url


@frappe.whitelist()
def get_click_to_chat(gateway: str, prefill: str | None = None, ref: str | None = None, phone: str | None = None) -> dict[str, Any]:
	"""wa.me link for the gateway's number. ``qr_svg`` is None (no QR library available)."""
	_require_manage()
	_require_whatsapp_gateway(gateway)
	number = _gateway_number(gateway, phone)
	return {"wa_me_url": build_wa_me_url(number, prefill, ref), "qr_svg": None}


@frappe.whitelist()
def get_widget_snippet(
	gateway: str, prefill: str | None = None, ref: str | None = None, label: str | None = None,
	position: str | None = None, phone: str | None = None,
) -> dict[str, Any]:
	"""``<script>`` tag that renders the floating Chat on WhatsApp button on any website."""
	_require_manage()
	_require_whatsapp_gateway(gateway)
	from html import escape

	number = _gateway_number(gateway, phone)
	attrs = {"data-number": number, "data-text": (prefill or "").strip(), "data-ref": (ref or "").strip(),
		"data-label": (label or "").strip(), "data-position": "left" if position == "left" else "right"}
	_prefill(None, attrs["data-ref"])  # validates ref
	parts = " ".join(f'{k}="{escape(v, quote=True)}"' for k, v in attrs.items() if v)
	src = frappe.utils.get_url(SCRIPT_PATH)
	return {"snippet": f'<script src="{src}" {parts} async></script>'}


def ref_opt_in_hook(context: dict) -> Decision | None:
	"""Pre-route hook: a first message carrying ``[ref:...]`` records a marketing opt-in (source widget). Never routes."""
	try:
		inner = context.get("context") or {}
		match = _REF_RE.search(str(inner.get("message_text") or ""))
		gateway = context.get("gateway")
		if not match or not gateway:
			return None
		phone = _phone(inner.get("sender_id"))
		if phone and frappe.db.get_value("Gateway", gateway, "provider") == "WhatsApp":
			_record(gateway, phone, "widget", None, f"click-to-chat ref {match.group(1)}")
	except Exception:
		frappe.log_error(title="huf widget ref opt-in failed")
	return None
