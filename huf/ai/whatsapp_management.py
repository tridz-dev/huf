# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Whitelisted WhatsApp management API for the Huf console.

Every function delegates to :mod:`huf.ai.gateway_adapters.whatsapp_bridge`,
the only Huf module that touches frappe_whatsapp doctypes. Expected failures
are returned as ``{"success": False, "error": "<code>", ...}``; bridge errors
raised as :class:`BridgeError` are converted the same way. Permission failures
raise ``frappe.PermissionError`` and are never converted into a success dict.

No function here uses ``ignore_permissions`` or ``set_user``. Mutating calls
are POST-only.
"""

from __future__ import annotations

import base64
import functools
import json
import re
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.rate_limiter import rate_limit

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError

ADMIN_ROLES = ("System Manager", "Huf Admin")
WHATSAPP_PROVIDER = "WhatsApp"
CALLBACK_WARNING = (
	"Meta allows one callback URL per app. Use the webhook URL shown above as the callback, "
	"not the WhatsApp Business app connector's own webhook route. Using the connector's route "
	"bypasses Huf's signature verification."
)
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
# Sends also accept the full record name "<name>-<language_code>" (e.g. huf_x-en_US).
_TEMPLATE_RECORD_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)?$")
_MIN_PHONE_DIGITS = 7
_MAX_PHONE_DIGITS = 15
_MAX_LIMIT = 200


def _bridge_guard(fn):
	"""Convert BridgeError into the standard error dict."""

	@functools.wraps(fn)
	def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
		try:
			return fn(*args, **kwargs)
		except BridgeError as exc:
			return dict(exc.payload, success=False)

	return wrapper


def _has_doctype_permission(doctype: str, ptype: str) -> None:
	if not frappe.has_permission(doctype, ptype):
		raise frappe.PermissionError(_("Not permitted to {0} {1}").format(ptype, doctype))


def _require_admin() -> None:
	roles = set(frappe.get_roles() or [])
	if not roles.intersection(ADMIN_ROLES):
		raise frappe.PermissionError(_("System Manager or Huf Admin role required"))


def _is_admin() -> bool:
	return bool(set(frappe.get_roles() or []).intersection(ADMIN_ROLES))


def _can_manage_integrations() -> bool:
	"""Admin role, or the Huf ``system.integrations.manage`` capability."""
	if _is_admin():
		return True
	try:
		from huf.permissions import has_capability

		return bool(has_capability(frappe.session.user, "system.integrations.manage"))
	except Exception:
		return False


def _gateway_write_allowed(gateway_name: str) -> bool:
	"""Write-level authority on a Gateway: the doctype write permission or integrations management."""
	return _can_manage_integrations() or bool(frappe.has_permission("Gateway", "write", doc=gateway_name))


def _gateway_read_allowed(gateway_name: str) -> bool:
	return _can_manage_integrations() or bool(frappe.has_permission("Gateway", "read", doc=gateway_name))


def _account_readable(account: str) -> bool:
	"""Admins see every account; others only accounts of Gateways they can read."""
	if _can_manage_integrations():
		return True
	rows = frappe.get_list("Gateway", filters={"whatsapp_account": account}, pluck="name", limit_page_length=50)
	return any(_gateway_read_allowed(name) for name in rows or [])


def _error(code: str, message: str = "") -> dict[str, Any]:
	out: dict[str, Any] = {"success": False, "error": code}
	if message:
		out["message"] = message
	return out


def _gateway_required() -> dict[str, Any]:
	return _error(
		"gateway_required",
		"Choose a WhatsApp gateway (or an account you may access). Data is never listed across accounts.",
	)


def _account_from(gateway_name: str | None, account: str | None) -> str | dict[str, Any]:
	"""Account of a Gateway (preferred) or an explicit account; never a default. No permission checks."""
	if gateway_name:
		if not frappe.db.exists("Gateway", gateway_name):
			return _error("not_found", "Gateway not found.")
		linked = _gateway_whatsapp_account(gateway_name)
		if not linked:
			return _error("no_account", "This gateway is not linked to a WhatsApp Account.")
		if account and account != linked:
			return _error("account_mismatch", "That account does not belong to this gateway.")
		return linked
	if account:
		return account
	return _gateway_required()


def _read_account(gateway_name: str | None, account: str | None) -> str | dict[str, Any]:
	"""Account the caller may READ: via a readable Gateway, or an explicit account they can see."""
	if gateway_name:
		if not frappe.db.exists("Gateway", gateway_name):
			return _error("not_found", "Gateway not found.")
		if not _gateway_read_allowed(gateway_name):
			raise frappe.PermissionError(_("Not permitted to read this Gateway"))
		return _account_from(gateway_name, account)
	if account:
		if not _account_readable(account):
			raise frappe.PermissionError(_("Not permitted to read this WhatsApp account"))
		return account
	return _gateway_required()


def _clamp_limit(limit: Any) -> int:
	try:
		value = int(limit)
	except (TypeError, ValueError):
		value = 50
	return max(1, min(value, _MAX_LIMIT))


def _parse_json_arg(value: Any, label: str) -> Any:
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return None
		try:
			return json.loads(value)
		except ValueError as exc:
			raise ValueError(f"{label} must be valid JSON") from exc
	return value


def _validate_recipient(to: Any) -> str | dict[str, Any]:
	"""Return the normalised digits-only number, or an error dict."""
	if not to or not str(to).strip():
		return {"success": False, "error": "invalid_recipient", "message": "Recipient number is required."}
	phone = bridge.normalize_phone(to)
	if not (_MIN_PHONE_DIGITS <= len(phone) <= _MAX_PHONE_DIGITS):
		return {
			"success": False,
			"error": "invalid_recipient",
			"message": "Recipient must be a phone number with 7 to 15 digits.",
		}
	return phone


def _validate_template_name(template_name: Any) -> dict[str, Any] | None:
	if not template_name or not _TEMPLATE_NAME_RE.match(str(template_name)):
		return {
			"success": False,
			"error": "invalid_name",
			"message": "Template name must match ^[a-z0-9_]+$",
		}
	return None


def _resolve_account_name(account: str | None) -> str | dict[str, Any]:
	"""Return the resolved WhatsApp Account name, or an error dict."""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	acct = bridge.resolve_account(account) if account else {"error": "no_account"}
	if not acct or acct.get("error"):
		return {"success": False, "error": "no_account"}
	return acct["name"]


def _gateway_whatsapp_account(gateway_name: str) -> str | None:
	try:
		return frappe.db.get_value("Gateway", gateway_name, "whatsapp_account")
	except Exception:
		return None


def _credential_presence(integration_settings: str | None) -> dict[str, bool]:
	"""Report which credential keys are set, never their values."""
	presence = {"app_secret": False, "webhook_verify_token": False}
	if not integration_settings:
		return presence
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key in presence:
			presence[row.key] = bool(row.get_password("value") or "")
	return presence


def _credential_phone_number_id(integration_settings: str | None) -> str:
	"""The gateway credential's phone_number_id (not a secret; it is in the webhook payload)."""
	if not integration_settings:
		return ""
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key == "phone_number_id":
			return str(row.get_password("value") or "").strip()
	return ""


def _account_phone_mismatch(gateway: dict[str, Any]) -> bool:
	"""True when the linked WhatsApp Account's phone_id differs from the credential's phone_number_id."""
	account = gateway.get("whatsapp_account")
	if not account or not bridge.is_available():
		return False
	try:
		account_phone = str(frappe.db.get_value("WhatsApp Account", account, "phone_id") or "").strip()
		credential_phone = _credential_phone_number_id(gateway.get("integration_settings"))
	except Exception:
		return False
	return bool(account_phone and credential_phone and account_phone != credential_phone)


def _webhook_url(gateway_name: str) -> str:
	return (
		f"{frappe.utils.get_url()}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook"
		f"?gateway_name={quote(gateway_name, safe='')}"
	)


def _gateway_status(gateway: dict[str, Any]) -> dict[str, Any]:
	presence = _credential_presence(gateway.get("integration_settings"))
	failing: list[str] = []
	if not presence["app_secret"]:
		failing.append("app_secret_missing")
	if not presence["webhook_verify_token"]:
		failing.append("webhook_verify_token_missing")
	mismatch = _account_phone_mismatch(gateway)
	if mismatch:
		failing.append("account_phone_mismatch")
	return {
		"name": gateway["name"],
		"enabled": bool(gateway.get("is_enabled")),
		"whatsapp_account": gateway.get("whatsapp_account"),
		"phone_number_id": gateway.get("phone_number_id") or "",
		"app_secret_present": presence["app_secret"],
		"app_secret_missing": not presence["app_secret"],
		"verify_token_present": presence["webhook_verify_token"],
		"account_phone_mismatch": mismatch,
		"webhook_url": _webhook_url(gateway["name"]),
		"callback_warning": CALLBACK_WARNING,
		"failing_checks": failing,
	}


@frappe.whitelist()
@_bridge_guard
def get_setup_status(gateway_name: str | None = None) -> dict[str, Any]:
	"""Setup checks for the WhatsApp gateway: bridge, accounts, and per-gateway credentials."""
	_require_admin()
	available = bridge.is_available()
	accounts: list[dict[str, Any]] = []
	if available:
		accounts = frappe.get_all(
			"WhatsApp Account", fields=["name", "phone_id", "status"], limit_page_length=100
		)

	filters: dict[str, Any] = {"provider": WHATSAPP_PROVIDER}
	if gateway_name:
		filters["name"] = gateway_name
	gateways_raw = frappe.get_all(
		"Gateway",
		filters=filters,
		fields=["name", "is_enabled", "integration_settings", "phone_number_id"],
		limit_page_length=100,
	)
	gateways = []
	for row in gateways_raw or []:
		row = dict(row)
		row["whatsapp_account"] = _gateway_whatsapp_account(row["name"])
		gateways.append(_gateway_status(row))

	return {
		"success": True,
		"bridge_available": available,
		"accounts": accounts,
		"gateways": gateways,
		"callback_warning": CALLBACK_WARNING,
	}


@frappe.whitelist()
@_bridge_guard
def list_templates(
	gateway_name: str | None = None, account: str | None = None, status: str | None = None
) -> dict[str, Any]:
	"""List one account's WhatsApp Templates (from ``gateway_name``'s account, or an account you may see)."""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	_has_doctype_permission("WhatsApp Templates", "read")
	account_name = _read_account(gateway_name, account)
	if isinstance(account_name, dict):
		return account_name
	templates = bridge.list_templates(account_name, status)
	try:
		buttons = bridge.template_buttons([t["name"] for t in templates])
		if isinstance(buttons, dict):
			for template in templates:
				template["buttons"] = buttons.get(template["name"], [])
	except Exception:
		pass  # buttons are informational for the send dialog; never fail the listing
	business_id = ""
	try:
		acct = bridge.resolve_account(account_name)
		if acct and not acct.get("error"):
			business_id = acct.get("business_id") or ""
	except Exception:
		pass
	return {
		"success": True,
		"templates": templates,
		"manager_url": bridge.manager_url(business_id),
		"business_id": business_id,
	}


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def create_template(
	account: str | None = None, payload: Any = None, gateway_name: str | None = None
) -> dict[str, Any]:
	"""Admin: create a WhatsApp Template; its doctype hook pushes it to Meta."""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	parsed = _parse_json_arg(payload, "payload")
	if not isinstance(parsed, dict):
		return {"success": False, "error": "invalid_payload", "message": "payload must be an object"}
	name_error = _validate_template_name(parsed.get("template_name") or parsed.get("name"))
	if name_error:
		return name_error
	derived = _account_from(gateway_name, account)
	if isinstance(derived, dict):
		return derived
	account_name = _resolve_account_name(derived)
	if isinstance(account_name, dict):
		return account_name
	return bridge.create_template(account_name, parsed)


@frappe.whitelist()
@_bridge_guard
def get_template(name: str | None = None) -> dict[str, Any]:
	"""Full detail of one template: components, review/quality state, edit allowance, WhatsApp Manager link."""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	if not name or not str(name).strip():
		return {"success": False, "error": "invalid_name", "message": "Template name is required."}
	result = bridge.get_template(str(name).strip())
	owner = result.get("whatsapp_account") if result.get("success") else None
	if owner and not _account_readable(owner):
		raise frappe.PermissionError(_("Not permitted to read this WhatsApp account"))
	return result


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def edit_template(name: str | None = None, payload: Any = None) -> dict[str, Any]:
	"""Admin: edit a template on Meta (full components) under Meta's edit rules; it goes back to PENDING review."""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	if not name or not str(name).strip():
		return {"success": False, "error": "invalid_name", "message": "Template name is required."}
	parsed = _parse_json_arg(payload, "payload")
	if not isinstance(parsed, dict):
		return {"success": False, "error": "invalid_payload", "message": "payload must be an object"}
	return bridge.edit_template(str(name).strip(), parsed)


@frappe.whitelist()
@_bridge_guard
def list_template_drafts(
	gateway_name: str | None = None, account: str | None = None, status: str | None = None
) -> dict[str, Any]:
	"""One account's template drafts awaiting (or past) human approval.

	Sites without frappe_whatsapp have no accounts; their drafts live in one unscoped bucket.
	"""
	_has_doctype_permission(bridge.DRAFT_DOCTYPE, "read")
	if not bridge.is_available():
		return {"success": True, "drafts": bridge.list_drafts(status or None, account="")}
	account_name = _read_account(gateway_name, account)
	if isinstance(account_name, dict):
		return account_name
	return {"success": True, "drafts": bridge.list_drafts(status or None, account=account_name)}


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def create_template_draft(
	account: str | None = None, payload: Any = None, submit_for_review: Any = 1, gateway_name: str | None = None
) -> dict[str, Any]:
	"""Save a template as a draft (same validation as create_template); nothing is sent to Meta.

	The non-admin "request" path: needs the draft doctype's create permission or an admin role.
	"""
	if not _is_admin() and not frappe.has_permission(bridge.DRAFT_DOCTYPE, "create"):
		raise frappe.PermissionError(_("Not permitted to request WhatsApp templates"))
	parsed = _parse_json_arg(payload, "payload")
	if not isinstance(parsed, dict):
		return {"success": False, "error": "invalid_payload", "message": "payload must be an object"}
	name_error = _validate_template_name(parsed.get("template_name") or parsed.get("name"))
	if name_error:
		return name_error
	account_name = ""  # sites without frappe_whatsapp have no accounts: one unscoped bucket
	if bridge.is_available():
		derived = _account_from(gateway_name, account)
		if isinstance(derived, dict):
			return derived
		resolved = bridge.resolve_account(derived)
		if not resolved or resolved.get("error"):
			return {"success": False, "error": "no_account"}
		account_name = resolved["name"]
	review = str(submit_for_review).strip().lower() not in ("0", "false", "no", "")
	return bridge.create_draft(
		parsed, requested_by=frappe.session.user, via="User", account=account_name,
		status="Pending Review" if review else "Draft",
	)


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def approve_template_draft(name: str | None = None, note: str | None = None) -> dict[str, Any]:
	"""Admin: approve a draft and submit it to Meta (exactly once)."""
	_require_admin()
	if not name:
		return {"success": False, "error": "invalid_name", "message": "Draft name is required."}
	return bridge.approve_draft(str(name), note or "")


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def reject_template_draft(name: str | None = None, note: str | None = None) -> dict[str, Any]:
	"""Admin: reject a draft; nothing is sent to Meta."""
	_require_admin()
	if not name:
		return {"success": False, "error": "invalid_name", "message": "Draft name is required."}
	return bridge.reject_draft(str(name), note or "")


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def delete_template(name: str | None = None) -> dict[str, Any]:
	"""Admin: delete a WhatsApp Template by document name."""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	if not name or not str(name).strip():
		return {"success": False, "error": "invalid_name", "message": "Template name is required."}
	return bridge.delete_template(name)


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def sync_templates(account: str | None = None, gateway_name: str | None = None) -> dict[str, Any]:
	"""Admin: sync templates for one WhatsApp Account from Meta: import ones missing in Huf, refresh status/category of existing."""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	derived = _account_from(gateway_name, account)
	if isinstance(derived, dict):
		return derived
	account_name = _resolve_account_name(derived)
	if isinstance(account_name, dict):
		return account_name
	return bridge.sync_templates(account_name)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_template_message(
	to: str | None = None,
	template_name: str | None = None,
	body_params: Any = None,
	header_params: Any = None,
	button_params: Any = None,
	language_code: str | None = None,
	gateway_name: str | None = None,
) -> dict[str, Any]:
	"""Send an approved template to a number from a Gateway. Allowed outside the 24h window.

	``gateway_name`` is required and the caller needs write authority on that Gateway; the
	WhatsApp Account is the Gateway's own, never supplied by the caller.

	``header_params`` is one text value or one ``{"type": "image|document", "link": ...}``
	media object; ``button_params`` is ``[{"index": 0, "sub_type": "url", "text": "<suffix>"}]``
	for dynamic URL buttons. Validation failures return ``validation_failed`` with
	an ``errors`` list.
	"""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	refused = _send_authority(gateway_name)
	if refused:
		return refused
	phone = _validate_recipient(to)
	if isinstance(phone, dict):
		return phone
	if not template_name or not _TEMPLATE_RECORD_RE.match(str(template_name).strip()):
		return {
			"success": False,
			"error": "invalid_name",
			"message": "Template name must be the Meta name (^[a-z0-9_]+$) or '<name>-<language_code>'.",
		}
	template_name = str(template_name).strip()
	try:
		body = _parse_json_arg(body_params, "body_params") or []
		header = _parse_json_arg(header_params, "header_params") or []
		buttons = _parse_json_arg(button_params, "button_params") or []
	except ValueError as exc:
		return {"success": False, "error": "invalid_params", "message": str(exc)}
	if isinstance(header, (str, dict)):
		header = [header]
	if not isinstance(body, list) or not isinstance(header, list) or not isinstance(buttons, list):
		return {"success": False, "error": "invalid_params", "message": "Params must be lists"}
	account_name = _resolve_account_name(_gateway_whatsapp_account(gateway_name))
	if isinstance(account_name, dict):
		return account_name
	return bridge.send_template(
		account_name, phone, template_name, body, header, button_params=buttons, language_code=language_code or None
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_text_message(gateway_name: str | None = None, to: str | None = None, text: str | None = None) -> dict[str, Any]:
	"""Send a free-form text, only while the 24h customer-service window is open."""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	refused = _send_authority(gateway_name)
	if refused:
		return refused
	phone = _validate_recipient(to)
	if isinstance(phone, dict):
		return phone
	if not text or not str(text).strip():
		return {"success": False, "error": "invalid_text", "message": "Message text is required."}

	state = bridge.window_state(gateway_name, phone)
	if not state.get("open"):
		return {
			"success": False,
			"error": "window_closed",
			"message": "The 24-hour customer-service window is closed for this number.",
			"hint": "Send an approved template with send_template_message instead.",
			"expires_at": state.get("expires_at"),
		}

	account_name = _resolve_account_name(_gateway_whatsapp_account(gateway_name))
	if isinstance(account_name, dict):
		return account_name
	return bridge.send_text(account_name, phone, str(text))


def _send_authority(gateway_name: str | None) -> dict[str, Any] | None:
	"""Validate the sending Gateway: required, existing, and WRITE-level authority on it (read is not enough)."""
	if not gateway_name:
		return {"success": False, "error": "invalid_gateway", "message": "gateway_name is required."}
	if not frappe.db.exists("Gateway", gateway_name):
		return {"success": False, "error": "not_found", "message": "Gateway not found."}
	if not _gateway_write_allowed(gateway_name):
		raise frappe.PermissionError(_("Not permitted to send from this Gateway"))
	return None


def _public_file_link(file_url: str) -> str | dict[str, Any]:
	"""Absolute link for an uploaded *public* File (Meta must be able to fetch it), or an error dict."""
	file_url = str(file_url or "").strip()
	if file_url.startswith("/private/") or not file_url.startswith("/files/"):
		return {"success": False, "error": "invalid_file", "message": "Only public uploaded files (/files/...) can be sent."}
	row = frappe.db.get_value("File", {"file_url": file_url}, ["name", "is_private"], as_dict=True)
	if not row or row.get("is_private"):
		return {"success": False, "error": "invalid_file", "message": "Uploaded public file not found."}
	return frappe.utils.get_url() + quote(file_url, safe="/")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_media_message(
	gateway_name: str | None = None,
	to: str | None = None,
	kind: str | None = None,
	link: str | None = None,
	file_url: str | None = None,
	caption: str | None = None,
	filename: str | None = None,
) -> dict[str, Any]:
	"""Send an image/document/audio/video, only while the 24h customer-service window is open.

	Give a public ``link`` (https URL) or the ``file_url`` of a public uploaded File.
	"""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	refused = _send_authority(gateway_name)
	if refused:
		return refused
	phone = _validate_recipient(to)
	if isinstance(phone, dict):
		return phone
	if file_url and not link:
		resolved = _public_file_link(file_url)
		if isinstance(resolved, dict):
			return resolved
		link = resolved
	state = bridge.window_state(gateway_name, phone)
	if not state.get("open"):
		return {
			"success": False,
			"error": "window_closed",
			"message": "The 24-hour customer-service window is closed for this number.",
			"hint": "Send an approved template with send_template_message instead.",
			"expires_at": state.get("expires_at"),
		}
	account_name = _resolve_account_name(_gateway_whatsapp_account(gateway_name))
	if isinstance(account_name, dict):
		return account_name
	return bridge.send_media(account_name, phone, kind or "", link=link, caption=caption, filename=filename)


@frappe.whitelist()
@_bridge_guard
def list_messages(
	gateway_name: str | None = None, phone: str | None = None, limit: int = 50, account: str | None = None
) -> dict[str, Any]:
	"""List recent WhatsApp Messages of one gateway's account, newest first."""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	_has_doctype_permission("WhatsApp Message", "read")
	account_name = _read_account(gateway_name, account)
	if isinstance(account_name, dict):
		return account_name
	return bridge.list_messages(account_name, phone, _clamp_limit(limit))


@frappe.whitelist()
@_bridge_guard
def list_conversations(
	gateway_name: str | None = None, limit: int = 50, account: str | None = None
) -> dict[str, Any]:
	"""Group one gateway's recent WhatsApp Messages by counterparty number."""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	_has_doctype_permission("WhatsApp Message", "read")
	account_name = _read_account(gateway_name, account)
	if isinstance(account_name, dict):
		return account_name
	return bridge.list_conversations(account_name, _clamp_limit(limit))


# --- Message log -------------------------------------------------------------

_LOG_DEFAULT_LIMIT = 50
_LOG_MAX_LIMIT = 100
_LOG_PREVIEW_CHARS = 300
_LOG_FILTER_LIMIT = 100
_DIRECTIONS = ("in", "out")
_TAG_RE = re.compile(r"<[^>]+>")


class _LogError(Exception):
	def __init__(self, payload: dict[str, Any]):
		super().__init__(payload.get("error"))
		self.payload = payload


def _log_limit(limit: Any) -> int:
	try:
		value = int(limit)
	except (TypeError, ValueError):
		value = _LOG_DEFAULT_LIMIT
	return max(1, min(value, _LOG_MAX_LIMIT))


def _encode_cursor(creation: Any, name: str) -> str:
	raw = json.dumps({"c": _iso(creation), "n": name}, separators=(",", ":"))
	return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[Any, str] | None:
	if not cursor:
		return None
	try:
		padded = str(cursor) + "=" * (-len(str(cursor)) % 4)
		data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
		return frappe.utils.get_datetime(data["c"]), str(data["n"])
	except Exception:
		raise _LogError(_error("invalid_cursor", "The cursor is not valid.")) from None


def _iso(value: Any) -> str | None:
	if not value:
		return None
	try:
		return frappe.utils.get_datetime(value).isoformat()
	except Exception:
		return str(value)


def _preview(text: Any) -> str:
	plain = _TAG_RE.sub("", str(text or "")).strip()
	return plain[:_LOG_PREVIEW_CHARS]


def _date_bounds(date_from: Any, date_to: Any) -> tuple[Any, Any]:
	"""(inclusive start, exclusive end); a date-only ``date_to`` includes that whole day."""
	try:
		start = frappe.utils.get_datetime(date_from) if date_from else None
		end = None
		if date_to:
			end = frappe.utils.get_datetime(date_to)
			if len(str(date_to).strip()) <= 10:
				end = end + timedelta(days=1)
			else:
				end = end + timedelta(microseconds=1)
	except Exception:
		raise _LogError(_error("invalid_date", "date_from/date_to must be ISO dates or datetimes.")) from None
	return start, end


def _like(value: str) -> str:
	return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _log_gateway(gateway_name: str | None) -> dict[str, Any]:
	"""Authorise a log read; returns {"gateway", "account", "bridge"} or raises _LogError."""
	if not gateway_name:
		raise _LogError(_gateway_required())
	if not frappe.db.exists("Gateway", gateway_name):
		raise _LogError(_error("not_found", "Gateway not found."))
	if not _gateway_read_allowed(gateway_name):
		raise frappe.PermissionError(_("Not permitted to read this Gateway"))
	if frappe.db.get_value("Gateway", gateway_name, "provider") != WHATSAPP_PROVIDER:
		raise _LogError(_error("not_whatsapp", "This gateway is not a WhatsApp gateway."))
	if not bridge.is_available():
		return {"gateway": gateway_name, "account": None, "bridge": False}
	_has_doctype_permission("WhatsApp Message", "read")
	account = _account_from(gateway_name, None)
	if isinstance(account, dict):
		raise _LogError(account)
	return {"gateway": gateway_name, "account": account, "bridge": True}


def _event_view(event: dict[str, Any] | None, direction: str) -> dict[str, Any]:
	if not event:
		return {"agent": None, "agent_run": None, "event": None, "status": None, "error": None}
	if direction == "out":
		return {
			"agent": event.get("target_agent"),
			"agent_run": event.get("agent_run"),
			"event": event["name"],
			"status": event.get("reply_status") or None,
			"error": event.get("delivery_error") or None,
		}
	return {
		"agent": event.get("target_agent"),
		"agent_run": event.get("agent_run"),
		"event": event["name"],
		"status": event.get("status") or None,
		"error": event.get("error_message") or None,
	}


def _bridge_log(ctx: dict[str, Any], f: dict[str, Any], cursor, limit: int) -> dict[str, Any]:
	from frappe.query_builder import Criterion

	gateway = ctx["gateway"]
	msg = frappe.qb.DocType("WhatsApp Message")
	ev = frappe.qb.DocType("Gateway Event")
	query = (
		frappe.qb.from_(msg)
		.select(
			msg.name, msg.type, msg["to"], msg["from"], msg.message, msg.message_id,
			msg.content_type, msg.status, msg.creation, msg.profile_name, msg.template,
		)
		.where(msg.whatsapp_account == ctx["account"])
		.orderby(msg.creation, order=Order.desc)
		.orderby(msg.name, order=Order.desc)
		.limit(limit + 1)
	)

	def event_ids(column, *extra):
		sub = frappe.qb.from_(ev).select(column).where(ev.gateway == gateway)
		for cond in extra:
			sub = sub.where(cond)
		return sub.where(column.isnotnull())

	if f["direction"]:
		query = query.where(msg.type == ("Incoming" if f["direction"] == "in" else "Outgoing"))
	if f["status"]:
		s = f["status"]
		query = query.where(
			Criterion.any(
				[
					msg.status == s,
					msg.message_id.isin(event_ids(ev.provider_event_id, ev.status == s)),
					msg.message_id.isin(event_ids(ev.reply_message_id, ev.reply_status == s)),
				]
			)
		)
	if f["template"]:
		query = query.where(msg.template == f["template"])
	if f["agent"]:
		query = query.where(
			Criterion.any(
				[
					msg.message_id.isin(event_ids(ev.provider_event_id, ev.target_agent == f["agent"])),
					msg.message_id.isin(event_ids(ev.reply_message_id, ev.target_agent == f["agent"])),
				]
			)
		)
	if f["phone"]:
		p = f["phone"]
		if len(p) >= _MIN_PHONE_DIGITS:
			query = query.where(Criterion.any([msg["from"] == p, msg["to"] == p]))
		else:
			query = query.where(Criterion.any([msg["from"].like(_like(p)), msg["to"].like(_like(p))]))
	if f["q"]:
		pat = _like(f["q"])
		query = query.where(
			Criterion.any(
				[msg.message.like(pat), msg.profile_name.like(pat), msg["from"].like(pat), msg["to"].like(pat)]
			)
		)
	if f["start"]:
		query = query.where(msg.creation >= f["start"])
	if f["end"]:
		query = query.where(msg.creation < f["end"])
	if cursor:
		c, n = cursor
		query = query.where(Criterion.any([msg.creation < c, Criterion.all([msg.creation == c, msg.name < n])]))

	rows = query.run(as_dict=True)
	has_more = len(rows) > limit
	rows = rows[:limit]

	ids = [r["message_id"] for r in rows if r.get("message_id")]
	events: dict[str, dict[str, Any]] = {}
	if ids:
		found = (
			frappe.qb.from_(ev)
			.select(
				ev.name, ev.provider_event_id, ev.reply_message_id, ev.target_agent, ev.agent_run,
				ev.status, ev.error_message, ev.reply_status, ev.delivery_error,
			)
			.where(ev.gateway == gateway)
			.where(Criterion.any([ev.provider_event_id.isin(ids), ev.reply_message_id.isin(ids)]))
			.run(as_dict=True)
		)
		for e in found:
			if e.get("reply_message_id"):
				events[("out", e["reply_message_id"])] = e
			if e.get("provider_event_id"):
				events[("in", e["provider_event_id"])] = e

	items = []
	for r in rows:
		direction = "in" if r.get("type") == "Incoming" else "out"
		view = _event_view(events.get((direction, r.get("message_id"))), direction)
		if direction == "in":
			sent_by = "customer"
			phone = bridge.normalize_phone(r.get("from"))
		else:
			phone = bridge.normalize_phone(r.get("to"))
			sent_by = "agent" if view["event"] else ("template" if r.get("template") else "manual")
		items.append(
			{
				"name": r["name"],
				"message_id": r.get("message_id"),
				"direction": direction,
				"phone": phone,
				"profile_name": r.get("profile_name") or None,
				"content_type": r.get("content_type") or "text",
				"text": _preview(r.get("message")),
				"status": view["status"] or r.get("status") or "",
				"error": view["error"],
				"template": r.get("template") or None,
				"creation": _iso(r["creation"]),
				"gateway": gateway,
				"agent": view["agent"],
				"agent_run": view["agent_run"],
				"event": view["event"],
				"sent_by": sent_by,
			}
		)
	next_cursor = _encode_cursor(rows[-1]["creation"], rows[-1]["name"]) if has_more and rows else None
	return {"success": True, "items": items, "next_cursor": next_cursor, "has_more": has_more}


def _event_rows(e: dict[str, Any], gateway: str) -> list[dict[str, Any]]:
	"""Direct mode: an event is its inbound message plus (when it sent one) the agent reply."""
	rows = []
	common = {
		"creation": _iso(e["creation"]),
		"gateway": gateway,
		"agent": e.get("target_agent"),
		"agent_run": e.get("agent_run"),
		"event": e["name"],
		"profile_name": None,
		"content_type": "text",
		"template": None,
	}
	phone = bridge.normalize_phone(e.get("sender_id"))
	if e.get("reply_message_id"):
		rows.append(
			{
				**common,
				"_key": e["name"] + "~r",
				"name": e["name"] + "~r",
				"message_id": e["reply_message_id"],
				"direction": "out",
				"phone": phone,
				"text": "",
				"status": e.get("reply_status") or "",
				"error": e.get("delivery_error") or None,
				"sent_by": "agent",
			}
		)
	rows.append(
		{
			**common,
			"_key": e["name"],
			"name": e["name"],
			"message_id": e.get("provider_event_id"),
			"direction": "in",
			"phone": phone,
			"text": _preview(e.get("message_text")),
			"status": e.get("status") or "",
			"error": e.get("error_message") or None,
			"sent_by": "customer",
		}
	)
	return rows


def _row_matches(row: dict[str, Any], f: dict[str, Any]) -> bool:
	if f["direction"] and row["direction"] != f["direction"]:
		return False
	if f["status"] and row["status"] != f["status"]:
		return False
	return True


def _direct_log(ctx: dict[str, Any], f: dict[str, Any], cursor, limit: int) -> dict[str, Any]:
	"""Log built from Gateway Events only (no frappe_whatsapp): inbound events plus agent replies."""
	from frappe.query_builder import Criterion

	gateway = ctx["gateway"]
	empty = {"success": True, "items": [], "next_cursor": None, "has_more": False}
	if f["template"]:
		return empty  # events do not carry template names
	ev = frappe.qb.DocType("Gateway Event")
	batch = limit + 2
	bound = None  # (creation, event name, inclusive)
	if cursor:
		c, key = cursor
		if key.endswith("~r"):
			bound = (c, key[:-2], True)
		else:
			bound = (c, key, False)
	matched: list[dict[str, Any]] = []
	exhausted = False
	for _ in range(25):
		q = (
			frappe.qb.from_(ev)
			.select(
				ev.name, ev.creation, ev.provider_event_id, ev.sender_id, ev.message_text, ev.status,
				ev.error_message, ev.target_agent, ev.agent_run, ev.reply_message_id, ev.reply_status,
				ev.delivery_error,
			)
			.where(ev.gateway == gateway)
			.orderby(ev.creation, order=Order.desc)
			.orderby(ev.name, order=Order.desc)
			.limit(batch)
		)
		if f["direction"] == "out":
			q = q.where(ev.reply_message_id.isnotnull()).where(ev.reply_message_id != "")
		if f["agent"]:
			q = q.where(ev.target_agent == f["agent"])
		if f["phone"]:
			q = q.where(ev.sender_id.like(_like(f["phone"])))
		if f["q"]:
			pat = _like(f["q"])
			q = q.where(Criterion.any([ev.message_text.like(pat), ev.sender_id.like(pat)]))
		if f["start"]:
			q = q.where(ev.creation >= f["start"])
		if f["end"]:
			q = q.where(ev.creation < f["end"])
		if bound:
			c, n, inclusive = bound
			name_cond = ev.name <= n if inclusive else ev.name < n
			q = q.where(Criterion.any([ev.creation < c, Criterion.all([ev.creation == c, name_cond])]))
		events = q.run(as_dict=True)
		for e in events:
			for row in _event_rows(e, gateway):
				if bound and bound[2] and e["name"] == bound[1] and row["_key"].endswith("~r"):
					continue  # the cursor sits on this event's reply; resume with its inbound row
				if _row_matches(row, f):
					matched.append(row)
		if len(events) < batch:
			exhausted = True
		if exhausted or len(matched) > limit or not events:
			break
		last = events[-1]
		bound = (last["creation"], last["name"], False)
	has_more = len(matched) > limit
	page = matched[:limit]
	next_cursor = _encode_cursor(page[-1]["creation"], page[-1]["_key"]) if has_more and page else None
	items = [{k: v for k, v in r.items() if k != "_key"} for r in page]
	return {"success": True, "items": items, "next_cursor": next_cursor, "has_more": has_more}


@frappe.whitelist()
def list_message_log(
	gateway_name: str | None = None,
	direction: str | None = None,
	status: str | None = None,
	agent: str | None = None,
	template: str | None = None,
	phone: str | None = None,
	q: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	cursor: str | None = None,
	limit: int = 50,
) -> dict[str, Any]:
	"""Gateway-scoped WhatsApp message log (newest first, keyset paginated).

	Bridge mode reads ``WhatsApp Message`` for the gateway's account and joins Gateway Events;
	without frappe_whatsapp the log is built from Gateway Events alone.
	"""
	try:
		ctx = _log_gateway(gateway_name)
		if direction not in (None, "", "in", "out"):
			return _error("invalid_direction", "direction must be 'in' or 'out'.")
		start, end = _date_bounds(date_from, date_to)
		decoded = _decode_cursor(cursor)
		digits = bridge.normalize_phone(phone) if phone else ""
		if phone and not digits:
			return {"success": True, "items": [], "next_cursor": None, "has_more": False}
		f = {
			"direction": direction or None,
			"status": (status or "").strip() or None,
			"agent": (agent or "").strip() or None,
			"template": (template or "").strip() or None,
			"phone": digits or None,
			"q": (q or "").strip() or None,
			"start": start,
			"end": end,
		}
		runner = _bridge_log if ctx["bridge"] else _direct_log
		return runner(ctx, f, decoded, _log_limit(limit))
	except _LogError as exc:
		return exc.payload
	except BridgeError as exc:
		return dict(exc.payload, success=False)


@frappe.whitelist()
def list_message_log_filters(gateway_name: str | None = None) -> dict[str, Any]:
	"""Dropdown values for the message log filters of one gateway."""
	try:
		ctx = _log_gateway(gateway_name)
	except _LogError as exc:
		return exc.payload
	ev = frappe.qb.DocType("Gateway Event")
	gateway = ctx["gateway"]

	def distinct(column, table=ev, *conds):
		query = frappe.qb.from_(table).select(column).distinct().where(column.isnotnull()).where(column != "")
		for cond in conds:
			query = query.where(cond)
		return [r[0] for r in query.limit(_LOG_FILTER_LIMIT).run()]

	agents = sorted(distinct(ev.target_agent, ev, ev.gateway == gateway))
	statuses = set(distinct(ev.status, ev, ev.gateway == gateway))
	statuses.update(distinct(ev.reply_status, ev, ev.gateway == gateway))
	templates: list[str] = []
	if ctx["bridge"]:
		msg = frappe.qb.DocType("WhatsApp Message")
		statuses.update(distinct(msg.status, msg, msg.whatsapp_account == ctx["account"]))
		templates = sorted(distinct(msg.template, msg, msg.whatsapp_account == ctx["account"]))
	return {
		"success": True,
		"agents": [{"name": a, "title": a} for a in agents],
		"templates": templates,
		"statuses": sorted(statuses)[:_LOG_FILTER_LIMIT],
		"directions": list(_DIRECTIONS),
	}


def can_launch_whatsapp_app(user: str | None = None, app: dict | None = None, **_kwargs: Any) -> bool:
	"""Launcher gate for the WhatsApp tile: an integrations admin AND at least one enabled WhatsApp gateway."""
	try:
		user = user or frappe.session.user
		if not user or user == "Guest":
			return False
		roles = set(frappe.get_roles(user) or [])
		allowed = bool(roles.intersection(ADMIN_ROLES))
		if not allowed:
			from huf.permissions import has_capability

			allowed = bool(has_capability(user, "system.integrations.manage"))
		if not allowed:
			return False
		return bool(frappe.db.exists("Gateway", {"provider": WHATSAPP_PROVIDER, "is_enabled": 1}))
	except Exception:
		return False
