"""Human reply API for Channel Conversations: send_reply / list_templates / return_to_ai / close.

Gate: Huf capability ``channels.reply`` or an integrations admin (``system.integrations.manage``).
Every send goes through the gateway's own adapter (WhatsApp bridge, Telegram, Slack, Teams; templates and the 24h window are WhatsApp-only), which call ``outbound_policy`` (site allow-list,
STOP, BSUID) before anything is posted.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from huf.ai.channels import conversation as conv

REPLY_CAPABILITY = "channels.reply"


def _can_reply() -> bool:
	from huf.ai.whatsapp.management import _can_manage_integrations
	from huf.permissions import has_capability

	return bool(_can_manage_integrations() or has_capability(frappe.session.user, REPLY_CAPABILITY))


def _require_reply() -> None:
	if not _can_reply():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _load(conversation: str):
	if not conversation or not frappe.db.exists("Channel Conversation", conversation):
		return None
	return frappe.get_doc("Channel Conversation", conversation)


def _result(status: str, **extra: Any) -> dict[str, Any]:
	return {"status": status, **extra}


def send_free_text(gateway_name: str, handle: str, text: str) -> str:
	"""Send free-form text through the gateway adapter (outbound policy applied); returns the message id."""
	from huf.ai.gateway_adapters.types import GatewayReply
	from huf.ai.gateway_webhook import get_gateway_adapter

	gateway = frappe.get_doc("Gateway", gateway_name)
	delivery = get_gateway_adapter(gateway).send_reply(GatewayReply(conversation_id=handle, text=text))
	return str(delivery.provider_message_id)


def _send_template(gateway_name: str, handle: str, template: str, params: Any) -> str:
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	account = frappe.db.get_value("Gateway", gateway_name, "whatsapp_account")
	res = bridge.send_template(
		account, handle, template, body_params=params or None, trusted=True, gateway_name=gateway_name
	)
	res = res if isinstance(res, dict) else {}
	return str(res.get("wamid") or res.get("message_id") or res.get("id") or res.get("name") or "")


def deliver_reply(conversation, text=None, template=None, params=None, attachments=None) -> dict[str, Any]:
	"""Permission-free core of :func:`send_reply` (callers have already authorised the sender)."""
	doc = conversation if not isinstance(conversation, str) else _load(conversation)
	if doc is None:
		return _result("error", error="not_found")
	if doc.status == "closed":
		return _result("error", error="conversation_closed")
	if attachments:
		return _result("error", error="attachments_unsupported")
	from huf.ai.whatsapp import outbound_policy as policy

	whatsapp = conv.window_applies(doc.get("channel"))
	try:
		if template and not whatsapp:
			return _result("error", error="templates_unsupported")
		if template:
			message_id = _send_template(doc.gateway, doc.contact_handle, template, params)
			preview = f"[template] {template}"
		elif not (text or "").strip():
			return _result("error", error="text_required")
		elif not conv.is_within_24h(doc):
			return _result("needs_template", needs_template=True)
		else:
			message_id = send_free_text(doc.gateway, doc.contact_handle, text)
			preview = text
	except policy.OutboundRefused as exc:
		return _result("refused", error=exc.code, message=str(exc))
	except Exception as exc:
		from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError

		code = exc.payload.get("error") if isinstance(exc, BridgeError) else None
		frappe.logger("huf").warning(f"Channel reply failed for {doc.name}: {code or type(exc).__name__}")
		return _result("failed", error=code or "send_failed", message=str(exc)[:300])
	conv.touch_outbound(doc, preview=preview)
	return _result("sent", message_id=message_id)


@frappe.whitelist(methods=["POST"])
def send_reply(conversation: str, text: str | None = None, template: str | None = None, params: Any = None, attachments: Any = None) -> dict[str, Any]:
	"""Send a human reply. Inside 24h of the customer's last message: free text. Outside: ``needs_template``
	unless ``template`` is given."""
	_require_reply()
	if isinstance(params, str):
		params = frappe.parse_json(params)
	return deliver_reply(conversation, text=text, template=template, params=params, attachments=attachments)


@frappe.whitelist()
def list_templates(gateway: str) -> dict[str, Any]:
	"""Approved templates of the gateway's WhatsApp account, for the reply composer."""
	_require_reply()
	if not gateway or not frappe.db.exists("Gateway", gateway):
		return {"success": False, "error": "not_found"}
	account = frappe.db.get_value("Gateway", gateway, "whatsapp_account")
	if not account:
		return {"success": False, "error": "no_account"}
	rows = frappe.get_all(
		"WhatsApp Templates",
		filters={"whatsapp_account": account, "status": "APPROVED"},
		fields=["name", "template_name", "actual_name", "category", "language_code", "status", "template", "header_type", "header"],
		order_by="modified desc",
		limit_page_length=500,
	)
	return {"success": True, "templates": rows}


@frappe.whitelist(methods=["POST"])
def return_to_ai(conversation: str) -> dict[str, Any]:
	"""Give a handed-off conversation back to the AI (the handoff link is kept for the record)."""
	_require_reply()
	doc = _load(conversation)
	if doc is None:
		return _result("error", error="not_found")
	if doc.status != "handed_off":
		return _result("error", error="not_handed_off")
	doc.db_set("status", "ai")
	return _result("ok", conversation_status="ai")


@frappe.whitelist(methods=["POST"])
def close(conversation: str) -> dict[str, Any]:
	"""Close a conversation; the next inbound opens a fresh one."""
	_require_reply()
	doc = _load(conversation)
	if doc is None:
		return _result("error", error="not_found")
	doc.db_set("status", "closed")
	return _result("ok", conversation_status="closed")
