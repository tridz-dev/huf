# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp integration tools for HUF agents.

Single consolidated tool that performs WhatsApp Cloud API actions via an
`action` parameter.

Actions: send_message, send_media, send_image, send_video, send_audio, send_voice_note, send_document, send_sticker,
send_location, send_contact, send_reaction, send_buttons, send_list, send_cta_url, send_template,
list_messages, get_account_info, list_templates, create_template, get_template_status.

Gateway binding (fail closed)
-----------------------------
The model never chooses the gateway or the WhatsApp account. ``gateway_name`` and
``whatsapp_account`` are not part of the tool schema and any such key supplied in a call is
popped and discarded in ``handle_action``. The gateway is derived server-side from the current
agent run (its conversation channel ``gateway:<name>``). A run that is not bound to an enabled
WhatsApp gateway (a chat run, a flow run, a forged context) is refused with
``gateway_context_required``; there is no fallback to a default account or to the first
Integration Settings row. Sends are authorised for the run's own gateway (the gateway admitted the sender), so its execution
user needs no Gateway write; template creation still requires write authority
(``huf.ai.whatsapp.management._send_authority``); reads require Gateway read authority.

Privilege gating (A8)
---------------------
Three per-gateway flags (Check fields on the run's own Gateway) gate privileged behaviour. They
are off by default and are never read from tool arguments: any ``allow_proactive``,
``allow_whatsapp_management`` or ``auto_submit_templates`` key supplied in a call is popped and
discarded. Any error while reading a flag fails closed (flag off).

* ``agent_allow_proactive``: permits free-form sends to a number with no open 24h
  customer-service window (see below).
* ``agent_allow_template_management``: permits ``create_template`` only. It does NOT permit
  proactive sends. ``create_template`` saves a DRAFT that a human must approve in the console;
  nothing reaches Meta from the agent.
* ``agent_auto_submit_templates``: when also set, ``create_template`` submits to Meta directly
  (still requires ``agent_allow_template_management``).

Credentials (``access_token``, ``phone_number_id``) are never tool parameters: tool arguments
are persisted in Agent Tool Call, so any such keys supplied in a call are popped and discarded.

``send_media`` (image/document/audio/video/sticker by public ``link`` or uploaded ``media_id``)
and every other non-text type (``send_image``/``send_video``/``send_audio``/``send_document``/
``send_sticker`` are ``send_media`` with the kind preset; ``send_location``, ``send_contact``,
``send_reaction``, ``send_buttons``, ``send_list``, ``send_cta_url``) are free-form too and
follow exactly the same proactive logic and flags as ``send_message``. A contact who opted out
(STOP) is refused with ``opted_out`` whatever the flags say.

A free-form send is proactive unless ``bridge.window_state(run_gateway, to)`` reports an open
window. The message is sent from the run gateway's own WhatsApp account (resolved server-side),
so the window checked is always the window of the sending account. ``send_template`` (approved
templates) is deliberately NOT gated by the proactive flag (it still requires the run user's
send authority); it is routed through the bridge when available so a WhatsApp Message row is
written. The tool never switches the session user.
"""

import contextvars
import json
from contextlib import contextmanager
from typing import Any, Optional

import frappe
import requests

from huf.ai import run_delivery
from huf.ai.whatsapp import send_file as send_file
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_messages as wm
from huf.ai.gateway_adapters import whatsapp_templates as wt

META_GRAPH_URL = f"https://graph.facebook.com/{bridge.GRAPH_DEFAULT_VERSION}"

_TRUTHY_STRINGS = {"1", "true", "yes"}


def _error(msg: str, definite: bool = False) -> str:
	"""Tool error JSON. ``definite`` marks a failure that happened before anything reached Meta (safe to retry)."""
	body: dict[str, Any] = {"success": False, "error": msg}
	if definite:
		body["definite"] = True
	return json.dumps(body, default=str)


def _success(data: Any) -> str:
	return json.dumps({"success": True, "data": data}, default=str)


def _refused(code: str, message: str) -> str:
	return json.dumps({"success": False, "error": code, "message": message}, default=str)


_MEDIA_ACTIONS = {
	"send_image": "image",
	"send_video": "video",
	"send_audio": "audio",
	"send_document": "document",
	"send_sticker": "sticker",
}
_INTERACTIVE_ACTIONS = {"send_buttons": "buttons", "send_list": "list", "send_cta_url": "cta_url"}
_PRIVILEGE_FLAGS = ("allow_proactive", "allow_whatsapp_management", "auto_submit_templates")
_CREDENTIAL_KWARGS = ("access_token", "phone_number_id")


def _is_truthy(value: Any) -> bool:
	return str(value or "").strip().lower() in _TRUTHY_STRINGS


_GATEWAY_FLAG_FIELDS = {
	"allow_proactive": "agent_allow_proactive",
	"allow_whatsapp_management": "agent_allow_template_management",
	"auto_submit_templates": "agent_auto_submit_templates",
}
# Keys the model must never control: the gateway and account are bound from the run context.
_BOUND_KWARGS = ("gateway_name", "whatsapp_account")
_SEND_ACTIONS = {
	"send_message", "send_media", "send_voice_note", "send_location", "send_contact", "send_reaction",
	"send_template", "create_template", *_MEDIA_ACTIONS, *_INTERACTIVE_ACTIONS,
}
_LIST_DEFAULT_LIMIT = 20
_LIST_MAX_LIMIT = 50


_trusted_gateway: contextvars.ContextVar = contextvars.ContextVar("huf_whatsapp_trusted_gateway", default="")
_trusted_contact: contextvars.ContextVar = contextvars.ContextVar("huf_whatsapp_trusted_contact", default="")
_trusted_run: contextvars.ContextVar = contextvars.ContextVar("huf_whatsapp_trusted_run", default="")


def _effective_run_id() -> Optional[str]:
	"""The run sends are scoped and capped to: the agent run, else the trusted flow tool-node run."""
	return getattr(frappe.flags, "huf_current_agent_run_id", None) or _trusted_run.get() or None


@contextmanager
def trusted_gateway(gateway_name: str, run_id: str = "", contact: str = ""):
	"""Bind the gateway for a TRUSTED, deterministic caller (the Flow engine's tool.call node).

	Only server code can enter this block; tool arguments never can. The gateway comes from the flow
	run's own gateway event, or from an admin-configured node field, never from the model. The caller
	still gets recipient scope and send caps, keyed to ``run_id`` (the flow's tool-node run).
	"""
	token = _trusted_gateway.set(str(gateway_name or "").strip())
	run_token = _trusted_run.set(str(run_id or "").strip())
	contact_token = _trusted_contact.set(str(contact or "").strip())
	try:
		yield
	finally:
		_trusted_contact.reset(contact_token)
		_trusted_run.reset(run_token)
		_trusted_gateway.reset(token)


def _run_gateway() -> str:
	"""The enabled WhatsApp Gateway the current run belongs to, or '' (fail closed).

	A trusted caller's binding wins; otherwise it is derived from Agent Run -> Agent
	Conversation.channel (``gateway:<name>``). Never from tool args.
	"""
	try:
		bound = _trusted_gateway.get()
		if bound:
			row = frappe.db.get_value("Gateway", bound, ["provider", "is_enabled"], as_dict=True)
			if row and row.get("provider") == "WhatsApp" and row.get("is_enabled"):
				return bound
			return ""
		run_id = getattr(frappe.flags, "huf_current_agent_run_id", None)
		if not run_id:
			return ""
		conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
		channel = str(frappe.db.get_value("Agent Conversation", conversation, "channel") or "") if conversation else ""
		if not channel.startswith("gateway:"):
			return ""
		name = channel[len("gateway:"):].strip()
		row = frappe.db.get_value("Gateway", name, ["provider", "is_enabled"], as_dict=True) if name else None
		if not row or row.get("provider") != "WhatsApp" or not row.get("is_enabled"):
			return ""
		return name
	except Exception:
		return ""


def _server_flag(gateway_name: str, name: str) -> bool:
	"""Read a privilege flag from the run's own Gateway. Fails closed: any error or unknown flag is False."""
	field = _GATEWAY_FLAG_FIELDS.get(name)
	if not field or not gateway_name:
		return False
	try:
		return _is_truthy(frappe.db.get_value("Gateway", gateway_name, field))
	except Exception:
		return False


def _gateway_integration_values(gateway_name: str) -> dict[str, str]:
	"""Credential rows of the named Gateway's own Integration Settings ({} when unavailable)."""
	try:
		settings_name = frappe.db.get_value("Gateway", gateway_name, "integration_settings")
		if not settings_name:
			return {}
		doc = frappe.get_doc("Integration Settings", settings_name)
		return {row.key: str(row.get_password("value") or "") for row in doc.credentials or [] if row.key}
	except Exception:
		return {}


def _graph_root(gateway_name: str = "") -> str:
	"""Versioned Graph root; the optional ``graph_api_url`` credential of the gateway only counts under tests."""
	override = _gateway_integration_values(gateway_name).get("graph_api_url", "") if gateway_name else ""
	return f"{bridge.graph_base_url(override)}/{bridge.GRAPH_DEFAULT_VERSION}"


def _gateway_integration_credentials(gateway_name: str) -> tuple[str, str]:
	"""phone_number_id / access_token of the named Gateway's own Integration Settings."""
	values = _gateway_integration_values(gateway_name)
	return str(values.get("phone_number_id") or "").strip(), str(values.get("access_token") or "").strip()


def _get_whatsapp_credentials(kwargs: dict | None = None) -> tuple[str, str]:
	"""phone_number_id / access_token of the run gateway's own integration; no gateway means no credentials."""
	gateway_name = ((kwargs or {}).get("gateway_name") or "").strip()
	if not gateway_name:
		return "", ""
	return _gateway_integration_credentials(gateway_name)


def _authorize(action: str, gateway_name: str) -> Optional[str]:
	"""Authority of the run over its own gateway.

	Sending is authorised for the run's own gateway: ``gateway_name`` is bound server-side from the run
	(or ``trusted_gateway``), never from the model, and the gateway already admitted the sender, so the
	gateway's execution user needs no Gateway write. Template management (``create_template``) keeps
	requiring real write authority; every other action requires read.
	"""
	from huf.ai.whatsapp import management as mgmt

	try:
		if action == "create_template":
			refused = mgmt._send_authority(gateway_name)
			return json.dumps(refused, default=str) if refused else None
		if action in _SEND_ACTIONS:
			return None
		if not mgmt._gateway_read_allowed(gateway_name):
			raise frappe.PermissionError("Not permitted to read this Gateway")
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to use WhatsApp through this Gateway")
	return None


def _gateway_phone_id(gateway_name: str) -> str:
	try:
		return str(frappe.db.get_value("Gateway", gateway_name, "phone_number_id") or "").strip()
	except Exception:
		return ""


def _disconnect_refusal(gateway_name: str) -> Optional[str]:
	"""The normal JSON refusal when the run gateway's number is Disconnected, else None."""
	from huf.ai.whatsapp import account_events as _ae

	refusal = _ae.send_refusal(_gateway_phone_id(gateway_name))
	return json.dumps(refusal, default=str) if refusal else None


def handle_action(action: str, **kwargs: Any) -> str:
	"""Handle WhatsApp agent tool invocation (bound to the current run's gateway)."""
	action = (action or "").strip().lower()
	# Privilege flags are server-side only: discard anything the LLM supplied.
	for name in _PRIVILEGE_FLAGS:
		kwargs.pop(name, None)
	# Credentials are server-side only (tool args are persisted).
	for name in _CREDENTIAL_KWARGS:
		kwargs.pop(name, None)
	# The gateway / account come from the run context, never from the model.
	for name in _BOUND_KWARGS:
		kwargs.pop(name, None)

	gateway_name = _run_gateway()
	if not gateway_name:
		return _refused(
			"gateway_context_required",
			"WhatsApp can only be used from a run that belongs to an enabled WhatsApp gateway.",
		)
	kwargs["gateway_name"] = gateway_name
	refusal = _authorize(action, gateway_name)
	if refusal:
		return refusal

	if action in _SEND_ACTIONS and action != "create_template":
		refusal = _disconnect_refusal(gateway_name)
		if refusal:
			return refusal
		refusal = _scope_refusal(kwargs, gateway_name)
		if refusal:
			return refusal
		with bridge.run_bound_send():  # the run's own gateway authorised this send
			raw = _idempotent_send(action, kwargs, gateway_name)
		_mark_outreach(gateway_name, kwargs, raw)
		return raw
	return _dispatch(action, kwargs)


def _has_entry(gateway_name: str, recipient: str) -> bool:
	from types import SimpleNamespace

	from huf.ai import gateway_service

	try:
		return bool(gateway_service._has_access_entry(SimpleNamespace(name=gateway_name, provider="WhatsApp"), "Sender", recipient))
	except Exception:
		return False


def _mark_outreach(gateway_name: str, kwargs: dict, raw: str) -> None:
	"""After a successful send to a recipient with no access entry, remember we messaged them first.

	Their STOP is then honoured (a stranger's STOP stays ignored). Never fails the send.
	"""
	try:
		result = json.loads(raw)
		recipient = _recipient(kwargs)
		if not (isinstance(result, dict) and result.get("success") and recipient):
			return
		if _has_entry(gateway_name, recipient):
			return
		from huf.ai.whatsapp import outbound_policy as policy

		policy.record_template_outreach(gateway_name, recipient)
	except Exception:
		frappe.log_error(title="WhatsApp outreach marker not recorded")


def _run_solution(run_id: Optional[str]) -> Optional[str]:
	"""The solution the current Agent Run belongs to (None for a trusted flow run or when unknown)."""
	if not run_id:
		return None
	try:
		return frappe.db.get_value("Agent Run", run_id, "solution") or None
	except Exception:
		return None


def _scope_refusal(kwargs: dict, gateway_name: str) -> Optional[str]:
	"""Recipient scope (WP-10): default recipient is the run's conversation contact; wider scope is gateway config.

	A trusted flow caller is scoped the same way: its args come from agent output / inbound text, so it
	gets no wider reach than the gateway's configured scope. Fills ``to`` with the current contact when
	left out.
	"""
	from huf.ai.whatsapp import send_scope as send_scope

	run_id = _effective_run_id()
	if not _recipient(kwargs):
		contact = send_scope.current_contact(run_id) or send_scope._normalize(_trusted_contact.get())
		if contact:
			kwargs["to"] = contact
	recipient = _recipient(kwargs)
	if not recipient:
		return None  # the send itself reports the missing recipient
	solution = _run_solution(run_id)
	extra = {"solution": solution} if solution else {}
	return send_scope.check_recipient(gateway_name, run_id, recipient, contact=_trusted_contact.get(), **extra)


def _idempotent_send(action: str, kwargs: dict, gateway_name: str) -> str:
	"""Run a send at most once per idempotency key (durable; see ``huf.ai.whatsapp.send_keys``)."""
	from huf.ai.whatsapp import send_keys as send_keys

	try:
		explicit = send_keys.explicit_key(kwargs)
	except send_keys.InvalidKey as e:
		return _refused("invalid_idempotency_key", str(e))
	run_id = _effective_run_id()
	call_id = kwargs.get("call_id")
	if not run_id and not explicit and not call_id:
		call_id = f"norun-{frappe.generate_hash(length=16)}"  # nothing to dedupe on, but the send is still claimed and counted
	key = send_keys.derive_key(gateway_name, run_id, call_id, action, kwargs, explicit)
	return send_keys.run_once(
		gateway_name, key, action, lambda: _capped_dispatch(action, kwargs, gateway_name, run_id),
		run=run_id or "", recipient=_recipient(kwargs),
	)


def _capped_dispatch(action: str, kwargs: dict, gateway_name: str, run_id: Optional[str]) -> str:
	"""Run the send unless it would exceed the gateway's per-run / per-day cap (checked after the claim)."""
	from huf.ai.whatsapp import send_scope as send_scope

	solution = _run_solution(run_id)
	refusal = send_scope.check_caps(gateway_name, run_id, **({"solution": solution} if solution else {}))
	if refusal:
		return refusal
	raw = _dispatch(action, kwargs)
	if action.startswith("send_") and action != "send_reaction":
		try:
			if json.loads(raw).get("success"):
				run_delivery.mark(run_id)
		except Exception:
			pass
	return raw


def _dispatch(action: str, kwargs: dict) -> str:
	if action == "send_message":
		return _send_message(kwargs)
	elif action == "send_media":
		return _send_media(kwargs)
	elif action == "send_voice_note":
		return _send_voice_note(kwargs)
	elif action in _MEDIA_ACTIONS:
		return _send_media({**kwargs, "kind": _MEDIA_ACTIONS[action]})
	elif action == "send_location":
		return _send_location(kwargs)
	elif action == "send_contact":
		return _send_contact(kwargs)
	elif action == "send_reaction":
		return _send_reaction(kwargs)
	elif action in _INTERACTIVE_ACTIONS:
		return _send_interactive(kwargs, _INTERACTIVE_ACTIONS[action])
	elif action == "send_template":
		return _send_template(kwargs)
	elif action == "list_messages":
		return _list_messages(kwargs)
	elif action == "get_account_info":
		return _get_account_info(kwargs)
	elif action == "list_templates":
		return _list_templates(kwargs)
	elif action == "create_template":
		return _create_template(kwargs)
	elif action == "get_template_status":
		return _get_template_status(kwargs)
	else:
		return _error(
			f"Unknown action '{action}'. Supported actions: send_message, send_media, send_image, send_video, "
			"send_audio, send_voice_note, send_document, send_sticker, send_location, send_contact, send_reaction, send_buttons, "
			"send_list, send_cta_url, send_template, list_messages, get_account_info, list_templates, "
			"create_template, get_template_status"
		)


def _bridge_result(result: dict) -> str:
	"""Pass a bridge result dict through as the tool's JSON response."""
	if result.get("success"):
		return _success({k: v for k, v in result.items() if k != "success"})
	return json.dumps(result, default=str)


def _gateway_account_name(gateway_name: str) -> Optional[str]:
	"""Server-side whatsapp_account of a Gateway ('' when unset, None when unknown)."""
	try:
		if not frappe.db.exists("Gateway", gateway_name):
			return None
		return (frappe.db.get_value("Gateway", gateway_name, "whatsapp_account") or "").strip()
	except Exception:
		return None


def _resolve_bridge_account(kwargs: dict) -> Optional[dict]:
	"""Return the run gateway's own WhatsApp Account dict, or None (direct mode / unavailable).

	The account is always the one linked to the run's gateway; there is no default account and no
	caller-supplied account. An unlinked gateway means direct mode with its own integration.
	"""
	if not bridge.is_available():
		return None
	gateway_name = (kwargs.get("gateway_name") or "").strip()
	if not gateway_name:
		return None
	gw_account = _gateway_account_name(gateway_name)
	if not gw_account:
		return None
	acct = bridge.resolve_account(gw_account)
	if not acct or acct.get("error"):
		return None
	return acct


def _is_proactive_send(kwargs: dict, recipient: str) -> bool:
	"""A free-form send is proactive unless the run gateway's window is open (A8)."""
	gateway_name = (kwargs.get("gateway_name") or "").strip()
	if not gateway_name:
		return True
	try:
		state = bridge.window_state(gateway_name, recipient)
	except Exception:
		# Fail closed: an unreadable window is treated as no window.
		return True
	return not state.get("open")


def _send_message(kwargs: dict) -> str:
	recipient = bridge.normalize_phone(kwargs.get("to") or kwargs.get("recipient") or kwargs.get("phone_number") or "")
	message = (kwargs.get("message") or kwargs.get("text") or "").strip()

	if not recipient:
		return _error("Recipient phone number ('to') is required", definite=True)
	if not message:
		return _error("Message text ('message') is required", definite=True)

	refusal = _free_form_refusal(kwargs, recipient, "a free-form message")
	if refusal:
		return refusal

	acct = _resolve_bridge_account(kwargs)
	if acct:
		try:
			res = bridge.send_text(acct["name"], recipient, message)
		except bridge.BridgeError as e:
			return json.dumps(e.payload, default=str)
		except frappe.PermissionError:
			return _refused("permission_denied", "Not permitted to send WhatsApp messages")
		except Exception as e:
			return _error(f"Failed to send WhatsApp message: {str(e)}")
		return _success({"message_id": res.get("message_id"), "recipient": recipient, "status": "sent", "name": res.get("name")})

	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found", definite=True)

	url = f"{_graph_root(kwargs['gateway_name'])}/{phone_number_id}/messages"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Content-Type": "application/json",
	}
	payload = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": recipient,
		"type": "text",
		"text": {"preview_url": False, "body": message},
	}

	try:
		res = requests.post(url, json=payload, headers=headers, timeout=15)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(
				f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}",
				definite=400 <= res.status_code < 500,
			)

		msg_id = data.get("messages", [{}])[0].get("id")

		# Log in frappe_whatsapp if installed
		if frappe.db.exists("DocType", "WhatsApp Message"):
			try:
				frappe.get_doc({
					"doctype": "WhatsApp Message",
					"type": "Outgoing",
					"from": phone_number_id,
					"to": recipient,
					"message": message,
					"message_id": msg_id,
					"status": "Sent",
				}).insert(ignore_permissions=True)
			except Exception:
				pass

		return _success({"message_id": msg_id, "recipient": recipient, "status": "sent"})
	except Exception as e:
		return _error(f"Failed to send WhatsApp message: {str(e)}")


def _json_list(value: Any) -> Optional[list]:
	"""A list argument that may arrive as a JSON string; None when it is not a list."""
	if value in (None, ""):
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return None
	if isinstance(value, dict):
		return [value]
	return value if isinstance(value, list) else None


def _recipient(kwargs: dict) -> str:
	return bridge.normalize_phone(kwargs.get("to") or kwargs.get("recipient") or kwargs.get("phone_number") or "")


def _is_opted_out(kwargs: dict, recipient: str) -> bool:
	"""True when the run gateway's contact opted out (STOP); fails closed (no gateway or any error = opted out)."""
	gateway_name = (kwargs.get("gateway_name") or "").strip()
	if not gateway_name:
		return True
	try:
		from huf.ai import gateway_service

		return bool(gateway_service.is_opted_out(gateway_name, recipient))
	except Exception:
		return True  # fail closed


def _allowlist_refusal(recipient: str) -> Optional[str]:
	"""Site allow-list (``wa_outbound_allowlist``) for sends that bypass the outbound policy choke point."""
	from huf.ai.whatsapp import outbound_policy as policy

	try:
		policy.check_allowlist(recipient)
	except policy.OutboundRefused as e:
		return _refused(e.code, str(e))
	return None


def _free_form_refusal(kwargs: dict, recipient: str, what: str) -> Optional[str]:
	"""Server-side gate of every free-form non-text send: allow-list, opt-out, then window / allow_proactive."""
	refusal = _allowlist_refusal(recipient)
	if refusal:
		return refusal
	if _is_opted_out(kwargs, recipient):
		return _refused("opted_out", "This contact opted out (STOP); no messages are sent until they opt back in (START).")
	if _is_proactive_send(kwargs, recipient) and not (
		_server_flag(kwargs.get("gateway_name") or "", "allow_proactive")
	):
		return _refused(
			"proactive_send_not_permitted",
			f"No open 24h window for this number. Enable proactive agent sends on the gateway to send {what}.",
		)
	return None


def _deliver_typed(kwargs: dict, recipient: str, built: tuple, bridge_call: Any, what: str) -> str:
	"""Validate (no network), gate, then send through the bridge account or, without one, straight to Graph."""
	payload, errors = built
	if errors or payload is None:
		return json.dumps(wt.validation_error(errors), default=str)
	refusal = _free_form_refusal(kwargs, recipient, what)
	if refusal:
		return refusal
	acct = _resolve_bridge_account(kwargs)
	if acct:
		try:
			res = bridge_call(acct["name"])
		except bridge.BridgeError as e:
			return json.dumps(e.payload, default=str)
		except frappe.PermissionError:
			return _refused("permission_denied", "Not permitted to send WhatsApp messages")
		except Exception as e:
			return _error(f"Failed to send WhatsApp {what}: {str(e)}")
		return _success({"message_id": res.get("message_id"), "recipient": recipient, "status": "sent", "name": res.get("name")})

	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found", definite=True)
	try:
		res = requests.post(
			f"{_graph_root(kwargs['gateway_name'])}/{phone_number_id}/messages",
			json=payload,
			headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
			timeout=15,
		)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(
				f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}",
				definite=400 <= res.status_code < 500,
			)
		return _success({"message_id": data.get("messages", [{}])[0].get("id"), "recipient": recipient, "status": "sent"})
	except Exception as e:
		return _error(f"Failed to send WhatsApp {what}: {str(e)}")


def _send_media(kwargs: dict) -> str:
	"""Send an image/video/audio/document/sticker by public link or media id (window / proactive gated like send_message)."""
	recipient = _recipient(kwargs)
	if not recipient:
		return _error("Recipient phone number ('to') is required", definite=True)
	if kwargs.get("file_url") or kwargs.get("file_id"):
		return _send_media_file(kwargs, recipient)
	media, errors = wt.validate_media_request(
		kwargs.get("kind") or kwargs.get("media_type"),
		kwargs.get("link") or kwargs.get("url"),
		kwargs.get("media_id"),
		kwargs.get("caption"),
		kwargs.get("filename"),
		kwargs.get("voice"),
	)
	if errors:
		return json.dumps(wt.validation_error(errors), default=str)
	payload = wt.build_media_payload(recipient, media, (kwargs.get("reply_to") or "").strip() or None)
	return _deliver_typed(
		kwargs, recipient, (payload, []),
		lambda account: bridge.send_media(
			account, recipient, media["kind"], link=media["link"], media_id=media["media_id"],
			caption=media["caption"], filename=media["filename"], voice=media["voice"],
			reply_to=(kwargs.get("reply_to") or "").strip() or None,
		),
		"media",
	)


def _file_error(e: "send_file.FileSendError") -> str:
	return _refused(e.code, e.message)


def _upload_for_send(kwargs: dict, prepared: dict) -> str:
	"""Upload the bytes to Meta (bridge account, else the gateway's own credentials) and return the media id."""
	mime, content, filename = prepared["mime"], prepared["content"], prepared["filename"]
	acct = _resolve_bridge_account(kwargs)
	try:
		if acct:
			res = bridge.upload_media(acct["name"], content, mime, filename, kind=prepared["kind"], voice=prepared["voice"])
			return str(res["media_id"])
		phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
		if not phone_number_id or not access_token:
			raise send_file.FileSendError("credentials_missing", "WhatsApp credentials not found for this gateway.")
		return bridge.post_media_upload(
			_graph_root(kwargs["gateway_name"]), phone_number_id, access_token, content, wm.normalize_mime(mime), filename
		)
	except bridge.BridgeError as e:
		raise send_file.FileSendError(str((e.payload or {}).get("error") or "upload_failed"), str((e.payload or {}).get("message") or "Upload to WhatsApp failed.")) from e
	except frappe.PermissionError as e:
		raise send_file.FileSendError("permission_denied", "Not permitted to send WhatsApp messages") from e


def _send_media_file(kwargs: dict, recipient: str) -> str:
	"""Send a Huf File: ownership check, limits, gates, upload to Meta, then the normal send by media id."""
	if kwargs.get("link") or kwargs.get("url") or kwargs.get("media_id"):
		return json.dumps(wt.validation_error([wm.err("file_url", "one_source", "Provide exactly one of file_url, file_id, link or media_id.")]), default=str)
	if (kwargs.get("file_url") or "") and (kwargs.get("file_id") or ""):
		return json.dumps(wt.validation_error([wm.err("file_url", "one_source", "Provide exactly one of file_url or file_id.")]), default=str)
	refusal = _free_form_refusal(kwargs, recipient, "media")
	if refusal:
		return refusal
	voice = _is_truthy(kwargs.get("voice"))
	try:
		resolved = send_file.resolve_file(kwargs.get("file_url"), kwargs.get("file_id"), _effective_run_id())
		prepared = send_file.prepare_upload(resolved, kwargs.get("kind") or kwargs.get("media_type"), voice)
		first, rest = send_file.split_caption(str(kwargs.get("caption") or ""))
		filename = (kwargs.get("filename") or "").strip() or prepared["filename"]
		_, errors = wm.validate_media_message(prepared["kind"], "", "pending", first, filename, prepared["voice"])
		if errors:
			return json.dumps(wt.validation_error(errors), default=str)
		media_id = _upload_for_send(kwargs, prepared)
	except send_file.FileSendError as e:
		return _file_error(e)
	except Exception as e:
		return _error(f"Failed to prepare WhatsApp media: {str(e)}", definite=True)
	send_kwargs = {k: v for k, v in kwargs.items() if k not in ("file_url", "file_id", "link", "url")}
	raw = _send_media({
		**send_kwargs, "kind": prepared["kind"], "media_id": media_id, "caption": first,
		"filename": filename, "voice": prepared["voice"],
	})
	if rest:
		try:
			ok = json.loads(raw).get("success")
		except ValueError:
			ok = False
		if ok:
			follow = json.loads(_send_message({**send_kwargs, "message": rest}))
			if not follow.get("success"):
				body = json.loads(raw)
				body.setdefault("data", {})["caption_overflow_sent"] = False
				return json.dumps(body, default=str)
	return raw


def _send_voice_note(kwargs: dict) -> str:
	"""Send audio as a voice note (``audio.voice: true``); only Ogg/Opus is accepted."""
	link = kwargs.get("link") or kwargs.get("url")
	if link and not kwargs.get("media_id") and not (kwargs.get("file_url") or kwargs.get("file_id")):
		errors = wm.validate_voice_link(link)
		if errors:
			return json.dumps(wt.validation_error(errors), default=str)
	return _send_media({**kwargs, "kind": "audio", "voice": True})


def _send_location(kwargs: dict) -> str:
	recipient = _recipient(kwargs)
	if not recipient:
		return _error("Recipient phone number ('to') is required", definite=True)
	args = (kwargs.get("latitude"), kwargs.get("longitude"), kwargs.get("name"), kwargs.get("address"))
	reply_to = (kwargs.get("reply_to") or "").strip() or None
	return _deliver_typed(
		kwargs, recipient, wm.build_location_payload(recipient, *args, reply_to),
		lambda account: bridge.send_location(account, recipient, *args[:2], name=args[2], address=args[3], reply_to=reply_to),
		"a location",
	)


def _send_contact(kwargs: dict) -> str:
	recipient = _recipient(kwargs)
	if not recipient:
		return _error("Recipient phone number ('to') is required", definite=True)
	contacts = kwargs.get("contacts")
	if isinstance(contacts, str) and contacts.strip():
		try:
			contacts = json.loads(contacts)
		except ValueError:
			return _error("contacts must be a JSON list of contact objects")
	if not contacts:
		contacts = [
			wm.simple_contact(
				kwargs.get("contact_name"), kwargs.get("contact_phone"), kwargs.get("contact_email"), kwargs.get("contact_org")
			)
		]
	reply_to = (kwargs.get("reply_to") or "").strip() or None
	return _deliver_typed(
		kwargs, recipient, wm.build_contacts_payload(recipient, contacts, reply_to),
		lambda account: bridge.send_contacts(account, recipient, contacts, reply_to=reply_to),
		"a contact",
	)


def _send_reaction(kwargs: dict) -> str:
	recipient = _recipient(kwargs)
	if not recipient:
		return _error("Recipient phone number ('to') is required", definite=True)
	remove = _is_truthy(kwargs.get("remove"))
	emoji = "" if remove else str(kwargs.get("emoji") or "")
	message_id = kwargs.get("message_id")
	return _deliver_typed(
		kwargs, recipient, wm.build_reaction_payload(recipient, message_id, emoji, remove),
		lambda account: bridge.send_reaction(account, recipient, str(message_id or ""), emoji, remove=remove),
		"a reaction",
	)


def _send_interactive(kwargs: dict, kind: str) -> str:
	"""send_buttons / send_list / send_cta_url (``body``, ``header``, ``footer`` plus the kind's own fields)."""
	recipient = _recipient(kwargs)
	if not recipient:
		return _error("Recipient phone number ('to') is required", definite=True)
	buttons = _json_list(kwargs.get("buttons"))
	sections = _json_list(kwargs.get("sections"))
	if buttons is None or sections is None:
		return _error("buttons and sections must be JSON lists")
	header = kwargs.get("header")
	if isinstance(header, str) and header.strip().startswith("{"):
		try:
			header = json.loads(header)
		except ValueError:
			return _error("header must be text or a JSON object")
	spec = {
		"body": kwargs.get("body") or kwargs.get("message") or kwargs.get("text"),
		"header": header,
		"footer": kwargs.get("footer"),
		"buttons": buttons,
		"button_text": kwargs.get("button_text"),
		"sections": sections,
		"display_text": kwargs.get("display_text"),
		"url": kwargs.get("url") or kwargs.get("link"),
	}
	reply_to = (kwargs.get("reply_to") or "").strip() or None
	return _deliver_typed(
		kwargs, recipient, wm.build_interactive_payload(recipient, kind, spec, reply_to),
		lambda account: bridge.send_interactive(account, recipient, kind, spec, reply_to=reply_to),
		"an interactive message",
	)


def _body_values(parameters: Any) -> Any:
	"""Body parameters as the bridge takes them: strings in a list, or a ``{name: value}`` map."""
	if isinstance(parameters, dict):
		return {str(k): str(v) for k, v in parameters.items()}
	return [p if isinstance(p, dict) else str(p) for p in parameters]


def _send_template(kwargs: dict) -> str:
	"""Send a pre-approved WhatsApp template message.

	``parameters``, when supplied, is a plain list of strings that fill the
	template's body placeholders in order (``{{1}}``, ``{{2}}``, ...) -- the
	shape the GW-36 template-selection UI builds from its structured
	parameter rows, rather than requiring a caller to hand-construct Meta's
	full ``components`` array.
	"""
	recipient = bridge.normalize_phone(kwargs.get("to") or kwargs.get("recipient") or "")
	template_name = (kwargs.get("template_name") or "").strip()
	language_code = (kwargs.get("language_code") or "en").strip()
	parameters = kwargs.get("parameters") or []
	header_params = _json_list(kwargs.get("header_params"))
	button_params = _json_list(kwargs.get("button_params"))

	if not recipient or not template_name:
		return _error("Recipient ('to') and 'template_name' are required")
	if not isinstance(parameters, (list, dict)):
		return _error("'parameters' must be a list of strings (or a {name: value} map for a named-variable template)")
	if header_params is None or button_params is None:
		return _error("'header_params' and 'button_params' must be lists (or JSON lists)")

	refusal = _allowlist_refusal(recipient)
	if refusal:
		return refusal
	if _is_opted_out(kwargs, recipient):
		return _refused("opted_out", "This contact opted out (STOP); no messages are sent until they opt back in (START).")
	if bridge.is_bsuid(recipient):
		return _refused("bsuid_recipient", "A BSUID cannot be used as a recipient; send to the contact's phone number.")

	acct = _resolve_bridge_account(kwargs)
	if acct:
		try:
			extra: dict[str, Any] = {"gateway_name": kwargs.get("gateway_name")}
			if header_params:
				extra["header_params"] = header_params
			if button_params:
				extra["button_params"] = button_params
			if kwargs.get("language_code"):
				extra["language_code"] = language_code
			run_id = _effective_run_id()
			if run_id:
				extra["run_id"] = run_id
			res = bridge.send_template(acct["name"], recipient, template_name, _body_values(parameters), **extra)
		except bridge.BridgeError as e:
			return json.dumps(e.payload, default=str)
		except frappe.PermissionError:
			return _refused("permission_denied", "Not permitted to send WhatsApp messages")
		except Exception as e:
			return _error(f"Failed to send WhatsApp template: {str(e)}")
		return _success({"message_id": res.get("message_id"), "recipient": recipient, "status": "sent", "name": res.get("name")})

	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found", definite=True)

	url = f"{_graph_root(kwargs['gateway_name'])}/{phone_number_id}/messages"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Content-Type": "application/json",
	}
	components, errors = bridge.direct_send_components(_body_values(parameters), header_params, button_params)
	if errors:
		return json.dumps(bridge.send_error(errors), default=str)
	template: dict[str, Any] = {
		"name": template_name,
		"language": {"code": language_code},
	}
	if components:
		template["components"] = components
	payload = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": recipient,
		"type": "template",
		"template": template,
	}

	try:
		res = requests.post(url, json=payload, headers=headers, timeout=15)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(
				f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}",
				definite=400 <= res.status_code < 500,
			)

		return _success(data)
	except Exception as e:
		return _error(f"Failed to send WhatsApp template: {str(e)}")


def _clamp_limit(value: Any) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		number = _LIST_DEFAULT_LIMIT
	return max(1, min(number, _LIST_MAX_LIMIT))


def _list_messages(kwargs: dict) -> str:
	"""Messages exchanged with ONE contact through the run's own gateway (newest first, cursor paged).

	Built on ``list_message_log`` so it is gateway scoped and permission checked for the run user;
	each item carries the wamid in ``message_id``.
	"""
	contact = bridge.normalize_phone(kwargs.get("to") or kwargs.get("recipient") or kwargs.get("phone_number") or "")
	if not contact:
		return _refused("contact_required", "Name the contact ('to') whose messages should be listed.")
	from huf.ai.whatsapp import management as mgmt

	try:
		result = mgmt.list_message_log(
			gateway_name=kwargs["gateway_name"],
			phone=contact,
			cursor=(kwargs.get("cursor") or "").strip() or None,
			limit=_clamp_limit(kwargs.get("limit")),
		)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to read WhatsApp messages")
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp messages: {str(e)}")
	if not result.get("success"):
		return json.dumps(result, default=str)
	return _success(
		{"items": result.get("items") or [], "next_cursor": result.get("next_cursor"), "has_more": bool(result.get("has_more"))}
	)


def _get_account_info(kwargs: dict) -> str:
	"""Phone number info of the run gateway's own number."""
	gateway_name = kwargs["gateway_name"]
	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		acct = _resolve_bridge_account(kwargs)
		if acct:
			phone_number_id = phone_number_id or str(acct.get("phone_id") or "")
			access_token = access_token or str(acct.get("token") or "")
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found", definite=True)

	url = f"{_graph_root(gateway_name)}/{phone_number_id}"
	headers = {"Authorization": f"Bearer {access_token}"}

	try:
		res = requests.get(url, headers=headers, timeout=10)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(
				f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}",
				definite=400 <= res.status_code < 500,
			)
		return _success(data)
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp account info: {str(e)}")


def _list_templates(kwargs: dict) -> str:
	"""List WhatsApp Templates via the bridge (read-only)."""
	if not bridge.is_available():
		return _error("bridge_unavailable")
	acct = _resolve_bridge_account(kwargs)
	if not acct:
		return _refused("no_account", "This gateway is not linked to a WhatsApp Account.")
	status = (kwargs.get("status") or "").strip() or None
	try:
		rows = bridge.list_templates(acct["name"], status)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to read WhatsApp Templates")
	except Exception as e:
		return _error(f"Failed to list WhatsApp templates: {str(e)}")
	return _success(rows)


def _create_template_draft(acct: dict, payload: dict, gateway_name: str) -> str:
	"""Save the template as a draft awaiting human approval; Meta is never contacted.

	``trusted=True`` skips the Template Draft doctype permission, so the run user's write authority
	on the run gateway is re-checked here, right at the bypass.
	"""
	try:
		from huf.ai.whatsapp import management as mgmt

		refused = mgmt._send_authority(gateway_name)
		if refused:
			return json.dumps(refused, default=str)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to create WhatsApp templates through this Gateway")
	try:
		result = bridge.create_draft(
			payload,
			requested_by=frappe.session.user,
			via="Agent run",
			agent_run=getattr(frappe.flags, "huf_current_agent_run_id", None) or "",
			account=acct["name"],
			trusted=True,  # gated by the gateway flag and _send_authority above
		)
	except Exception as e:
		return _error(f"Failed to save WhatsApp template draft: {str(e)}")
	if not result.get("success"):
		return json.dumps(result, default=str)
	return _success(
		{
			"status": "pending_review",
			"draft": result["name"],
			"message": (
				"The template was saved as a draft and has NOT been sent to Meta. A human must approve it "
				"in the WhatsApp console before it is submitted. Do not retry; use get_template_status "
				f"with template_name '{result['name']}' to check the outcome."
			),
		}
	)


def _get_template_status(kwargs: dict) -> str:
	"""Review status of a template or draft: Meta status, rejection reason, quality, draft state (read-only)."""
	ref = (kwargs.get("template_name") or kwargs.get("draft") or "").strip()
	if not ref:
		return _error("'template_name' (a template name or a draft name) is required")
	try:
		acct = _resolve_bridge_account(kwargs) if bridge.is_available() else None
		result = bridge.get_draft_or_state(ref, (acct or {}).get("name"))
	except Exception as e:
		return _error(f"Failed to read template status: {str(e)}")
	return _bridge_result(result)


def _create_template(kwargs: dict) -> str:
	"""Create a WhatsApp template via the bridge (management; A8 gated).

	Requires the run gateway's ``agent_allow_template_management`` flag and the run user's write
	authority on that gateway. By default this only saves a draft for human approval; with the
	gateway's ``agent_auto_submit_templates`` flag it submits directly. Accepted fields: ``template_name``,
	``category`` (MARKETING/UTILITY), ``language_code``, ``body`` (+ ``sample_values``),
	optional ``header_type``/``header``/``sample``, ``footer`` and ``buttons``
	(QUICK_REPLY, URL, PHONE_NUMBER). Validation errors are returned structured.
	"""
	if not _server_flag(kwargs["gateway_name"], "allow_whatsapp_management"):
		return _refused(
			"management_not_permitted",
			"Template creation is disabled. Enable agent template management on the gateway.",
		)
	if not bridge.is_available():
		return _error("bridge_unavailable")
	acct = _resolve_bridge_account(kwargs)
	if not acct:
		return _error("no_account")

	payload = {
		key: kwargs[key]
		for key in (
			"template_name", "category", "language_code", "body", "template", "sample_values",
			"header", "header_type", "sample", "footer", "buttons",
		)
		if kwargs.get(key) is not None
	}
	if isinstance(payload.get("buttons"), str):
		try:
			payload["buttons"] = json.loads(payload["buttons"])
		except ValueError:
			return _error("'buttons' must be a list (or JSON list)")
	if not _server_flag(kwargs["gateway_name"], "auto_submit_templates"):
		return _create_template_draft(acct, payload, kwargs["gateway_name"])
	try:
		result = bridge.create_template(acct["name"], payload)
	except bridge.BridgeError as e:
		return json.dumps(e.payload, default=str)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to create WhatsApp Templates")
	except Exception as e:
		return _error(f"Failed to create WhatsApp template: {str(e)}")
	return _bridge_result(result)
