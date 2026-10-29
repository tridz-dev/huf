"""WhatsApp Flows: list/cache the WABA's Flows, send a flow message, record nfm_reply form responses."""

from __future__ import annotations

import json
from typing import Any, Callable

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.channels import run_as
from huf.ai.channels.pipeline import Decision
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_inbound as inbound
from huf.ai.whatsapp import token_check

ADMIN_ROLES = ("System Manager", "Huf Admin")
TOKEN_PREFIX = "huf:"


def _require_admin() -> None:
	if not set(frappe.get_roles() or []).intersection(ADMIN_ROLES):
		raise frappe.PermissionError(_("System Manager or Huf Admin role required"))


def _graph_get(url: str, params=None, headers=None):
	import requests

	return requests.get(url, params=params, headers=headers, timeout=token_check.HTTP_TIMEOUT, allow_redirects=False)


def fetch_flows(gateway: str, http_get: Callable[..., Any] | None = None) -> list[dict]:
	"""Flows of the gateway's WABA from Graph (``/{waba_id}/flows``). Raises frappe.ValidationError (no token in text)."""
	creds = token_check.resolve_credentials(gateway)
	if not creds.get("waba_id"):
		frappe.throw(_("This gateway has no WhatsApp Business Account ID."))
	url = f"{creds['base']}/{creds['waba_id']}/flows"
	rows: list[dict] = []
	params: dict | None = {"fields": "id,name,status,categories", "limit": 100}
	for _page in range(20):
		try:
			status, body = token_check._call(
				http_get or _graph_get, url, params=params, headers={"Authorization": f"Bearer {creds['token']}"}
			)
		except Exception:
			frappe.throw(_("Couldn't reach Meta."))
		err = token_check._error_of(status, body)
		if err:
			frappe.throw(_("Meta refused the Flows request ({0}).").format(err.get("code")))
		rows += [r for r in body.get("data") or [] if isinstance(r, dict) and r.get("id")]
		after = ((body.get("paging") or {}).get("cursors") or {}).get("after")
		if not (body.get("paging") or {}).get("next") or not after:
			break
		params = {"fields": "id,name,status,categories", "limit": 100, "after": after}
	return rows


@frappe.whitelist()
def list_wa_flows(gateway: str, refresh: int | str = 1) -> list[dict]:
	"""Admin: sync the WABA's Flows into the ``WhatsApp Flow`` cache and return them (``refresh=0`` = cache only)."""
	return sync_flows(gateway, refresh)


def sync_flows(gateway: str, refresh: int | str = 1, http_get: Callable[..., Any] | None = None) -> list[dict]:
	_require_admin()
	if not gateway or not frappe.db.exists("Gateway", gateway):
		frappe.throw(_("Gateway not found."))
	if str(refresh) not in ("0", "false", "False"):
		now = now_datetime()
		seen = set()
		for row in fetch_flows(gateway, http_get):
			seen.add(str(row["id"]))
			values = {
				"flow_name": str(row.get("name") or "")[:255],
				"status": str(row.get("status") or "")[:32],
				"categories": ",".join(str(c) for c in (row.get("categories") or [])),
				"last_synced": now,
			}
			name = frappe.db.get_value("WhatsApp Flow", {"gateway": gateway, "flow_id": str(row["id"])})
			if name:
				frappe.db.set_value("WhatsApp Flow", name, values)
			else:
				frappe.get_doc({"doctype": "WhatsApp Flow", "gateway": gateway, "flow_id": str(row["id"]), **values}).insert()
		for name, fid in frappe.get_all("WhatsApp Flow", {"gateway": gateway}, ["name", "flow_id"], as_list=True):
			if fid not in seen:
				frappe.delete_doc("WhatsApp Flow", name)
	return frappe.get_all(
		"WhatsApp Flow", {"gateway": gateway}, ["name", "flow_id", "flow_name", "status", "categories", "last_synced"],
		order_by="flow_name asc",
	)


def _refused(code: str, message: str) -> str:
	return json.dumps({"success": False, "error": code, "message": message})


def send_flow(gateway: str, to: str, flow_name: str, cta: str, body: str = "", screen: str | None = None,
	data: Any = None, send: Callable[..., Any] | None = None) -> dict[str, Any]:
	"""Send an interactive ``flow`` message from ``gateway`` to ``to`` (opt-out, allow-list and 24h gate apply)."""
	flow = frappe.db.get_value(
		"WhatsApp Flow", {"gateway": gateway, "flow_name": flow_name}, ["name", "flow_id", "status"], as_dict=True
	)
	if not flow:
		return {"success": False, "error": "flow_not_found", "message": f"Unknown flow {flow_name!r}; sync flows first."}
	if (flow.status or "").upper() != "PUBLISHED":
		return {"success": False, "error": "flow_not_sendable", "message": f"Flow status is {flow.status}."}
	from huf.ai.whatsapp import management as mgmt, outbound_policy as policy

	try:
		policy.check_recipient(gateway, to)
	except policy.OutboundRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc)}
	gated = mgmt._free_form_gate(gateway, bridge.normalize_phone(to))
	if gated:
		return gated
	spec = {
		"body": body or cta, "flow_id": flow.flow_id, "flow_cta": cta,
		"flow_token": f"{TOKEN_PREFIX}{flow.flow_id}:{frappe.generate_hash(length=10)}",
		"screen": screen, "flow_data": data if isinstance(data, dict) else None,
		"flow_action": "navigate" if (screen or data) else None,
	}
	account = mgmt._resolve_account_name(mgmt._gateway_whatsapp_account(gateway))
	if isinstance(account, dict):
		return account
	try:
		res = (send or bridge.send_interactive)(account, to, "flow", spec)
	except bridge.BridgeError as exc:
		return dict(exc.payload, success=False)
	return {"success": True, "flow_token": spec["flow_token"], "message_id": (res or {}).get("message_id")}


def handle_send_wa_flow(flow_name: str = "", cta: str = "", screen: str = "", data: Any = None, **_ignored) -> str:
	"""Agent tool: send a Flow form to the current conversation's contact. Returns JSON; never raises."""
	try:
		if isinstance(data, str) and data.strip():
			data = json.loads(data)
		name = run_as.current_conversation()
		if not name:
			return _refused("no_conversation", "No active channel conversation.")
		conv = frappe.db.get_value("Channel Conversation", name, ["gateway", "contact_handle"], as_dict=True)
		if not conv:
			return _refused("no_conversation", "No active channel conversation.")
		if not flow_name or not cta:
			return _refused("invalid_params", "flow_name and cta are required.")
		return json.dumps(send_flow(conv.gateway, conv.contact_handle, flow_name, cta, screen=screen or None, data=data), default=str)
	except Exception:
		frappe.log_error(title="send_wa_flow failed")
		return _refused("send_failed", "Could not send the flow.")


def record_response(gateway: str, nfm: dict, conversation: str | None = None) -> str:
	"""Create a ``WhatsApp Flow Response`` from an nfm_reply dict; returns its name."""
	data = inbound.parse_form_response(nfm)
	token = str(data.get("flow_token") or "")
	flow = None
	if token.startswith(TOKEN_PREFIX):
		fid = token[len(TOKEN_PREFIX):].split(":", 1)[0]
		flow = frappe.db.get_value("WhatsApp Flow", {"gateway": gateway, "flow_id": fid})
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Flow Response", "gateway": gateway, "conversation": conversation, "flow": flow,
			"flow_token": token[:255], "received_at": now_datetime(), "response": json.dumps(data, ensure_ascii=False),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def flow_response_hook(context: dict) -> Decision | None:
	"""Pre-route hook: record nfm_reply form responses. Side effect only; never changes the route."""
	event = context.get("event")
	if not event or not context.get("gateway"):
		return None
	row = frappe.db.get_value("Gateway Event", event, ["raw_payload", "channel_conversation"], as_dict=True)
	if not row or not row.raw_payload:
		return None
	raw = row.raw_payload
	if isinstance(raw, str):
		raw = json.loads(raw)
	interactive = ((raw or {}).get("message") or {}).get("interactive") or {}
	nfm = interactive.get("nfm_reply")
	if interactive.get("type") == "nfm_reply" or nfm:
		record_response(context["gateway"], nfm or {}, row.channel_conversation)
	return None
