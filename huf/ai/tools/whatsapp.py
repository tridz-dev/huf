# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp integration tools for HUF agents.

Single consolidated tool that performs WhatsApp Cloud API actions via an
`action` parameter.

Actions: send_message, send_media, send_template, list_messages,
get_account_info, list_templates, create_template, get_template_status.

Privilege gating (A8)
---------------------
Two flags gate privileged behaviour. They are read server-side from the
active WhatsApp Integration Settings ``credentials`` rows and are off by
default. The LLM controls tool-call kwargs, so any ``allow_proactive`` or
``allow_whatsapp_management`` key supplied in a call is popped and discarded
in ``handle_action``. A setting counts only when its value is truthy: ``1``,
``"1"``, ``"true"`` or ``"yes"`` (case-insensitive). ``"false"``,
``"0"``, ``""`` and missing rows do not count. Any error while reading the
settings fails closed (flag off).

* ``allow_proactive``: permits free-form ``send_message`` to a number with no
  open 24h customer-service window (see below).
* ``allow_whatsapp_management``: permits ``create_template`` (only this
  flag; ``allow_proactive`` does not), and also permits proactive free-form
  sends. ``create_template`` only saves a DRAFT that a human must approve
  in the console; nothing reaches Meta from the agent.
* ``auto_submit_templates``: when also truthy, ``create_template`` submits to
  Meta directly (still requires ``allow_whatsapp_management``).

Credentials (``access_token``, ``phone_number_id``) are never tool
parameters: tool arguments are persisted in Agent Tool Call, so any such
keys supplied in a call are popped and discarded.

``send_media`` (image/document/audio/video by public ``link``) is free-form
too and follows exactly the same proactive logic and flags as ``send_message``.

A free-form ``send_message`` is proactive unless ``gateway_name`` is given
and ``bridge.window_state(gateway_name, to)`` reports an open window. When a
gateway is named, the message is sent from that gateway's own WhatsApp
account (resolved server-side) and a conflicting ``whatsapp_account`` is
ignored, so the window checked is always the window of the sending account.
With no gateway context, every free-form send is treated as proactive.
``send_template`` (approved templates) is deliberately NOT gated by either
flag; it is routed through the bridge when available so a WhatsApp Message
row is written. The tool never uses ``ignore_permissions`` and never
switches the session user.
"""

import json
from typing import Optional, Any

import frappe
import requests

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_templates as wt

META_GRAPH_URL = f"https://graph.facebook.com/{bridge.GRAPH_DEFAULT_VERSION}"

_TRUTHY_STRINGS = {"1", "true", "yes"}


def _error(msg: str) -> str:
	return json.dumps({"success": False, "error": msg}, default=str)


def _success(data: Any) -> str:
	return json.dumps({"success": True, "data": data}, default=str)


def _refused(code: str, message: str) -> str:
	return json.dumps({"success": False, "error": code, "message": message}, default=str)


_PRIVILEGE_FLAGS = ("allow_proactive", "allow_whatsapp_management", "auto_submit_templates")
_CREDENTIAL_KWARGS = ("access_token", "phone_number_id")


def _is_truthy(value: Any) -> bool:
	return str(value or "").strip().lower() in _TRUTHY_STRINGS


def _server_flag(name: str) -> bool:
	"""Read a privilege flag from the active WhatsApp Integration Settings.

	Fails closed: any error, or no active settings row, returns False.
	"""
	try:
		settings_list = frappe.get_all(
			"Integration Settings", filters={"service": "whatsapp", "is_active": 1}, limit=1
		)
		if not settings_list:
			return False
		doc = frappe.get_doc("Integration Settings", settings_list[0].name)
		for row in doc.credentials or []:
			if row.key == name:
				return _is_truthy(row.get_password("value") or row.value or "")
	except Exception:
		return False
	return False


def _graph_root() -> str:
	"""Versioned Graph root; the optional ``graph_api_url`` credential only counts under tests."""
	override = ""
	try:
		settings_list = frappe.get_all("Integration Settings", filters={"service": "whatsapp", "is_active": 1}, limit=1)
		if settings_list:
			doc = frappe.get_doc("Integration Settings", settings_list[0].name)
			for row in doc.credentials or []:
				if row.key == "graph_api_url":
					override = row.get_password("value") or ""
	except Exception:
		override = ""
	return f"{bridge.graph_base_url(override)}/{bridge.GRAPH_DEFAULT_VERSION}"


def _gateway_integration_credentials(gateway_name: str) -> tuple[str, str]:
	"""phone_number_id / access_token of the named Gateway's own Integration Settings."""
	try:
		settings_name = frappe.db.get_value("Gateway", gateway_name, "integration_settings")
		if not settings_name:
			return "", ""
		doc = frappe.get_doc("Integration Settings", settings_name)
		values = {row.key: (row.get_password("value") or "") for row in doc.credentials or [] if row.key}
		return str(values.get("phone_number_id") or "").strip(), str(values.get("access_token") or "").strip()
	except Exception:
		return "", ""


def _get_whatsapp_credentials(kwargs: dict | None = None) -> tuple[str, str]:
	"""Get phone_number_id and access_token from server-side configuration only.

	A named gateway uses its own integration credentials; other WhatsApp accounts are never
	consulted for it. Without a gateway the first WhatsApp Account / active integration is used.
	"""
	gateway_name = ((kwargs or {}).get("gateway_name") or "").strip()
	if gateway_name:
		return _gateway_integration_credentials(gateway_name)
	phone_number_id = ""
	access_token = ""

	# Fallback to Integration Settings or WhatsApp Account DocType
	if frappe.db.exists("DocType", "WhatsApp Account"):
		accounts = frappe.get_all("WhatsApp Account", fields=["name", "phone_id"], limit=1)
		if accounts:
			doc = frappe.get_doc("WhatsApp Account", accounts[0].name)
			phone_number_id = phone_number_id or doc.phone_id or ""
			access_token = access_token or doc.get_password("token") or ""

	if not phone_number_id or not access_token:
		# Check Integration Settings
		settings_list = frappe.get_all("Integration Settings", filters={"service": "whatsapp", "is_active": 1}, limit=1)
		if settings_list:
			doc = frappe.get_doc("Integration Settings", settings_list[0].name)
			phone_number_id = phone_number_id or doc.get("phone_number_id") or ""
			for row in doc.credentials or []:
				if row.key == "access_token":
					access_token = access_token or row.get_password("value") or ""

	return phone_number_id, access_token


def handle_action(action: str, **kwargs: Any) -> str:
	"""Handle WhatsApp agent tool invocation."""
	action = (action or "").strip().lower()
	# Privilege flags are server-side only: discard anything the LLM supplied.
	for name in _PRIVILEGE_FLAGS:
		kwargs.pop(name, None)
	# Credentials are server-side only (tool args are persisted).
	for name in _CREDENTIAL_KWARGS:
		kwargs.pop(name, None)

	if action == "send_message":
		return _send_message(kwargs)
	elif action == "send_media":
		return _send_media(kwargs)
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
			f"Unknown action '{action}'. Supported actions: send_message, send_media, send_template, "
			"list_messages, get_account_info, list_templates, create_template, get_template_status"
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
	"""Return the resolved WhatsApp Account dict, or None when unavailable.

	A named ``gateway_name`` pins the account to that gateway's own account and never
	falls back to a default or caller-supplied one (an unlinked gateway means direct mode).
	A ``whatsapp_account`` argument is only honoured without a gateway, where the
	default account is used when none is given (non-gateway tool use).
	"""
	if not bridge.is_available():
		return None
	gateway_name = (kwargs.get("gateway_name") or "").strip()
	if gateway_name:
		gw_account = _gateway_account_name(gateway_name)
		if not gw_account:
			return None
		acct = bridge.resolve_account(gw_account)
	else:
		account_name = (kwargs.get("whatsapp_account") or "").strip()
		acct = bridge.resolve_account(account_name) if account_name else bridge.resolve_default_account()
	if not acct or acct.get("error"):
		return None
	return acct


def _is_proactive_send(kwargs: dict, recipient: str) -> bool:
	"""A free-form send is proactive unless the gateway window is open (A8)."""
	gateway_name = (kwargs.get("gateway_name") or "").strip()
	if not gateway_name or _gateway_account_name(gateway_name) is None:
		return True  # no (or unknown) gateway: nothing to evaluate a window against
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
		return _error("Recipient phone number ('to') is required")
	if not message:
		return _error("Message text ('message') is required")

	if _is_proactive_send(kwargs, recipient) and not (
		_server_flag("allow_proactive") or _server_flag("allow_whatsapp_management")
	):
		return _refused(
			"proactive_send_not_permitted",
			"No open 24h window for this number. Enable allow_proactive to send a free-form message.",
		)

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
		return _error("WhatsApp credentials not found")

	url = f"{_graph_root()}/{phone_number_id}/messages"
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
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")

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


def _send_media(kwargs: dict) -> str:
	"""Send an image/document/audio/video by public link (window / proactive gated like send_message)."""
	recipient = bridge.normalize_phone(kwargs.get("to") or kwargs.get("recipient") or kwargs.get("phone_number") or "")
	if not recipient:
		return _error("Recipient phone number ('to') is required")
	media, errors = wt.validate_media_request(
		kwargs.get("kind") or kwargs.get("media_type"),
		kwargs.get("link") or kwargs.get("url"),
		kwargs.get("media_id"),
		kwargs.get("caption"),
		kwargs.get("filename"),
	)
	if errors:
		return json.dumps(wt.validation_error(errors), default=str)

	if _is_proactive_send(kwargs, recipient) and not (
		_server_flag("allow_proactive") or _server_flag("allow_whatsapp_management")
	):
		return _refused(
			"proactive_send_not_permitted",
			"No open 24h window for this number. Enable allow_proactive to send free-form media.",
		)

	acct = _resolve_bridge_account(kwargs)
	if acct:
		try:
			res = bridge.send_media(
				acct["name"], recipient, media["kind"], link=media["link"], media_id=media["media_id"],
				caption=media["caption"], filename=media["filename"],
			)
		except bridge.BridgeError as e:
			return json.dumps(e.payload, default=str)
		except frappe.PermissionError:
			return _refused("permission_denied", "Not permitted to send WhatsApp messages")
		except Exception as e:
			return _error(f"Failed to send WhatsApp media: {str(e)}")
		return _success({"message_id": res.get("message_id"), "recipient": recipient, "status": "sent", "name": res.get("name")})

	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found")
	try:
		res = requests.post(
			f"{_graph_root()}/{phone_number_id}/messages",
			json=wt.build_media_payload(recipient, media),
			headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
			timeout=15,
		)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")
		return _success({"message_id": data.get("messages", [{}])[0].get("id"), "recipient": recipient, "status": "sent"})
	except Exception as e:
		return _error(f"Failed to send WhatsApp media: {str(e)}")


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
	if not isinstance(parameters, list):
		return _error("'parameters' must be a list of strings")
	if header_params is None or button_params is None:
		return _error("'header_params' and 'button_params' must be lists (or JSON lists)")

	acct = _resolve_bridge_account(kwargs)
	if acct:
		try:
			extra: dict[str, Any] = {}
			if header_params:
				extra["header_params"] = header_params
			if button_params:
				extra["button_params"] = button_params
			if kwargs.get("language_code"):
				extra["language_code"] = language_code
			res = bridge.send_template(acct["name"], recipient, template_name, [str(p) for p in parameters], **extra)
		except bridge.BridgeError as e:
			return json.dumps(e.payload, default=str)
		except frappe.PermissionError:
			return _refused("permission_denied", "Not permitted to send WhatsApp messages")
		except Exception as e:
			return _error(f"Failed to send WhatsApp template: {str(e)}")
		return _success({"message_id": res.get("message_id"), "recipient": recipient, "status": "sent", "name": res.get("name")})

	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found")

	url = f"{_graph_root()}/{phone_number_id}/messages"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Content-Type": "application/json",
	}
	errors: list[dict[str, str]] = []
	body_n = [wt.validate_param_text(f"parameters[{i}]", p, errors) for i, p in enumerate(parameters)]
	headers_n, herr = wt.normalize_header_params(header_params)
	buttons_n, berr = wt.normalize_button_params(button_params)
	errors += herr + berr
	if any(isinstance(h, dict) and not h.get("type") for h in headers_n):
		errors.append(wt._e("header_params", "invalid_type", "Media header needs a type (image, document or video)."))
	if errors:
		return json.dumps(wt.validation_error(errors), default=str)
	template: dict[str, Any] = {
		"name": template_name,
		"language": {"code": language_code},
	}
	components = wt.build_template_components(body_n, headers_n, buttons_n)
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
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")

		return _success(data)
	except Exception as e:
		return _error(f"Failed to send WhatsApp template: {str(e)}")


def _list_messages(kwargs: dict) -> str:
	if not frappe.db.exists("DocType", "WhatsApp Message"):
		return _error("frappe_whatsapp app is not installed or enabled")

	limit = int(kwargs.get("limit") or 20)
	filters = {}
	if kwargs.get("to"):
		filters["to"] = kwargs["to"]
	if kwargs.get("from"):
		filters["from"] = kwargs["from"]

	try:
		messages = frappe.get_all(
			"WhatsApp Message",
			filters=filters,
			fields=["name", "type", "from", "to", "message", "status", "creation"],
			order_by="creation desc",
			limit=limit,
		)
		return _success(messages)
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp messages: {str(e)}")


def _get_account_info(kwargs: dict) -> str:
	phone_number_id, access_token = _get_whatsapp_credentials()
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found")

	url = f"{_graph_root()}/{phone_number_id}"
	headers = {"Authorization": f"Bearer {access_token}"}

	try:
		res = requests.get(url, headers=headers, timeout=10)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")
		return _success(data)
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp account info: {str(e)}")


def _list_templates(kwargs: dict) -> str:
	"""List WhatsApp Templates via the bridge (read-only)."""
	if not bridge.is_available():
		return _error("bridge_unavailable")
	acct = _resolve_bridge_account(kwargs)
	if not acct:
		return _refused("gateway_required", "Name a gateway (or a WhatsApp account); templates are never listed across accounts.")
	status = (kwargs.get("status") or "").strip() or None
	try:
		rows = bridge.list_templates(acct["name"], status)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to read WhatsApp Templates")
	except Exception as e:
		return _error(f"Failed to list WhatsApp templates: {str(e)}")
	return _success(rows)


def _create_template_draft(acct: dict, payload: dict) -> str:
	"""Save the template as a draft awaiting human approval; Meta is never contacted."""
	try:
		result = bridge.create_draft(
			payload,
			requested_by=frappe.session.user,
			via="Agent run",
			agent_run=getattr(frappe.flags, "huf_current_agent_run_id", None) or "",
			account=acct["name"],
			trusted=True,  # gated by the server-side allow_whatsapp_management flag
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

	Requires ``allow_whatsapp_management`` enabled in
	the server-side Integration Settings. By default this only saves a draft for human
	approval; with the server-side ``auto_submit_templates`` credential it submits directly. Accepted fields: ``template_name``,
	``category`` (MARKETING/UTILITY), ``language_code``, ``body`` (+ ``sample_values``),
	optional ``header_type``/``header``/``sample``, ``footer`` and ``buttons``
	(QUICK_REPLY, URL, PHONE_NUMBER). Validation errors are returned structured.
	"""
	if not _server_flag("allow_whatsapp_management"):
		return _refused(
			"management_not_permitted",
			"Template creation is disabled. Enable allow_whatsapp_management in the tool config.",
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
	if not _server_flag("auto_submit_templates"):
		return _create_template_draft(acct, payload)
	try:
		result = bridge.create_template(acct["name"], payload)
	except bridge.BridgeError as e:
		return json.dumps(e.payload, default=str)
	except frappe.PermissionError:
		return _refused("permission_denied", "Not permitted to create WhatsApp Templates")
	except Exception as e:
		return _error(f"Failed to create WhatsApp template: {str(e)}")
	return _bridge_result(result)
