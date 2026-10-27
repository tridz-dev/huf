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
import mimetypes
import random
import re
import time
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.rate_limiter import rate_limit

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_calls as wcalls
from huf.ai.gateway_adapters import whatsapp_messages as wm
from huf.ai.gateway_adapters import whatsapp_templates as wt
from huf.ai.gateway_adapters.whatsapp_bridge import BridgeError

ADMIN_ROLES = ("System Manager", "Huf Admin")
WHATSAPP_PROVIDER = "WhatsApp"
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


_PRESENCE_KEYS = ("app_secret", "webhook_verify_token", "access_token", "phone_number_id", "app_id")


def _credential_presence(integration_settings: str | None) -> dict[str, bool]:
	"""Report which credential keys are set, never their values."""
	presence = dict.fromkeys(_PRESENCE_KEYS, False)
	if not integration_settings:
		return presence
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key in presence:
			presence[row.key] = bool(row.get_password("value") or "")
	return presence


def _credential_app_id(integration_settings: str | None) -> str:
	"""Meta app id from an optional ``app_id`` credential (not a secret; used for dashboard links)."""
	if not integration_settings:
		return ""
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key == "app_id":
			return str(row.get_password("value") or "").strip()
	return ""


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


_GATEWAY_FIELDS = [
	"name",
	"is_enabled",
	"integration_settings",
	"phone_number_id",
	"fallback_template",
	"fallback_template_language",
	"direct_policy",
	"room_policy",
	"room_sender_policy",
	"mention_required",
	"default_target_type",
	"default_agent",
	"default_flow",
	"last_event_at",
	"last_error",
]


def _gateway_status(gateway: dict[str, Any], connector_available: bool | None = None) -> dict[str, Any]:
	"""Full per-gateway payload: configuration presence plus health (see ``huf.ai.whatsapp.health``)."""
	from huf.ai.whatsapp import health

	if connector_available is None:
		connector_available = bridge.is_available()
	presence = _credential_presence(gateway.get("integration_settings"))
	mismatch = _account_phone_mismatch(gateway)
	app_id = _credential_app_id(gateway.get("integration_settings"))
	account = gateway.get("whatsapp_account")
	if not app_id and account and connector_available:
		try:
			app_id = str(frappe.db.get_value("WhatsApp Account", account, "app_id") or "").strip()
		except Exception:
			app_id = ""
	payload = {
		"name": gateway["name"],
		"enabled": bool(gateway.get("is_enabled")),
		"whatsapp_account": account,
		"phone_number_id": gateway.get("phone_number_id") or "",
		"account_phone_mismatch": mismatch,
		"webhook_url": _webhook_url(gateway["name"]),
	}
	payload.update(
		health.build_health(
			gateway, presence, connector_available=connector_available, mismatch=mismatch, app_id=app_id
		)
	)
	return payload


@frappe.whitelist()
@_bridge_guard
def get_setup_status(gateway_name: str | None = None) -> dict[str, Any]:
	"""Setup and health for ONE WhatsApp gateway; without a name, a site summary for the switcher.

	With ``gateway_name``: ``{success, connector_available, gateway, accounts}`` where ``accounts``
	holds only that gateway's own linked account. Without: ``{success, connector_available,
	gateways: [{name, health, enabled}]}`` and nothing else.
	"""
	_require_admin()
	available = bridge.is_available()

	if not gateway_name:
		rows = frappe.get_all(
			"Gateway", filters={"provider": WHATSAPP_PROVIDER}, fields=_GATEWAY_FIELDS, limit_page_length=100
		)
		summary = []
		for row in rows or []:
			row = dict(row)
			row["whatsapp_account"] = _gateway_whatsapp_account(row["name"])
			status = _gateway_status(row, available)
			summary.append({"name": status["name"], "health": status["health"], "enabled": status["enabled"]})
		return {"success": True, "connector_available": available, "gateways": summary}

	rows = frappe.get_all(
		"Gateway",
		filters={"provider": WHATSAPP_PROVIDER, "name": gateway_name},
		fields=_GATEWAY_FIELDS,
		limit_page_length=1,
	)
	if not rows:
		return _error("not_found", "Gateway not found.")
	row = dict(rows[0])
	row["whatsapp_account"] = _gateway_whatsapp_account(row["name"])
	accounts: list[dict[str, Any]] = []
	if available and row["whatsapp_account"]:
		accounts = frappe.get_all(
			"WhatsApp Account",
			filters={"name": row["whatsapp_account"]},
			fields=["name", "phone_id", "status"],
			limit_page_length=1,
		)
	return {
		"success": True,
		"connector_available": available,
		"gateway": _gateway_status(row, available),
		"accounts": [dict(a) for a in accounts or []],
	}


def _template_key(row: dict[str, Any]) -> tuple[str, str]:
	return (str(row.get("actual_name") or row.get("template_name") or row.get("name") or ""), str(row.get("language_code") or ""))


def _with_usage(account_name: str, templates: list[dict[str, Any]], solution: str | None) -> list[dict[str, Any]]:
	"""Add used_by/shared/owner to each row (and apply the solution filter). Never fails the listing."""
	try:
		from huf.ai.solutions import template_usage

		usage = template_usage.bulk_usage(account_name, [_template_key(t) for t in templates])
	except Exception:
		if solution:
			return []
		for t in templates:
			t.update({"used_by": [], "shared": False, "owner": None})
		return templates
	out = []
	for t in templates:
		u = usage.get(_template_key(t)) or {"owner": None, "used_by": [], "shared": False}
		t.update({"used_by": u["used_by"], "shared": u["shared"], "owner": u["owner"]})
		if solution and not any(x["solution"] == solution for x in u["used_by"]):
			continue
		out.append(t)
	return out


def _shared_refusal(docname: str, acknowledge_shared: Any) -> dict[str, Any] | None:
	"""``shared_template`` refusal when several solutions use the template and it was not acknowledged."""
	from huf.ai.solutions import template_usage

	identity = template_usage.template_identity(docname)
	if not identity:
		return None
	return template_usage.guard_shared(identity[0], identity[1], identity[2], acknowledge_shared)


@frappe.whitelist()
@_bridge_guard
def list_templates(
	gateway_name: str | None = None,
	account: str | None = None,
	status: str | None = None,
	solution: str | None = None,
) -> dict[str, Any]:
	"""List one account's WhatsApp Templates (from ``gateway_name``'s account, or an account you may see).

	Rows gain ``used_by`` / ``shared`` / ``owner`` (Solutions that use the template); ``solution`` keeps only
	that solution's templates. Usage is only read after the account passed the read check.
	"""
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
	templates = _with_usage(account_name, templates, solution)
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
	"""Admin: create a WhatsApp Template; Huf pushes it straight to Meta, then mirrors it locally."""
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
def edit_template(name: str | None = None, payload: Any = None, acknowledge_shared: Any = 0) -> dict[str, Any]:
	"""Admin: edit a template on Meta (full components) under Meta's edit rules; it goes back to PENDING review.

	A template used by several solutions is refused with ``shared_template`` unless ``acknowledge_shared``.
	"""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	if not name or not str(name).strip():
		return {"success": False, "error": "invalid_name", "message": "Template name is required."}
	parsed = _parse_json_arg(payload, "payload")
	if not isinstance(parsed, dict):
		return {"success": False, "error": "invalid_payload", "message": "payload must be an object"}
	refusal = _shared_refusal(str(name).strip(), acknowledge_shared)
	if refusal:
		return refusal
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
def declare_template_usage(
	account: str | None = None, template: str | None = None, language: str | None = None,
	solution: str | None = None, owner: Any = 0,
) -> dict[str, Any]:
	"""Admin: declare that a solution uses (or, with ``owner``, owns) a template of an account."""
	if not _can_manage_integrations():
		raise frappe.PermissionError(_("Not permitted to manage integrations"))
	resolved = _read_account(None, account)
	if isinstance(resolved, dict):
		return resolved
	if not template or not str(template).strip():
		return _error("invalid_name", "Template name is required.")
	if not solution or not frappe.db.exists("Solution", solution):
		return _error("not_found", "Solution not found.")
	from huf.ai.solutions import template_usage

	owner_flag = str(owner).strip().lower() in ("1", "true", "yes")
	usage = template_usage.declare(resolved, str(template).strip(), language or "", solution, owner=owner_flag)
	return {"success": True, "account": resolved, "template": str(template).strip(), "language": language or "", **usage}


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def delete_template(name: str | None = None, acknowledge_shared: Any = 0) -> dict[str, Any]:
	"""Admin: delete a WhatsApp Template by document name (refused with ``shared_template`` when shared, unless acknowledged)."""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	if not name or not str(name).strip():
		return {"success": False, "error": "invalid_name", "message": "Template name is required."}
	refusal = _shared_refusal(str(name).strip(), acknowledge_shared)
	if refusal:
		return refusal
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

	``body_params`` is an ordered list, or a ``{name: value}`` map for a template with named variables;
	``header_params`` is one text value, one ``{"type": "image|document|video", "link": ...}`` media object,
	one ``{"type": "location", "latitude": ..., "longitude": ...}`` object or (named) a one-entry map; ``button_params`` is ``[{"index": 0, "sub_type": "url", "text": "<suffix>"}]``
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
	if isinstance(header, str) or (isinstance(header, dict) and "type" in header):
		header = [header]  # one text value or one media / location object; a dict without "type" is a named text header
	if not isinstance(body, (list, dict)) or not isinstance(header, (list, dict)) or not isinstance(buttons, list):
		return {"success": False, "error": "invalid_params", "message": "Params must be lists (body and header may be {name: value} maps for named-variable templates)"}
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


def _opted_out(gateway_name: str, phone: str) -> bool:
	"""True when ``phone`` sent STOP to this gateway (T2's consent gate). Fails closed on any error."""
	try:
		from huf.ai import gateway_service

		return bool(gateway_service.is_opted_out(gateway_name, phone))
	except Exception:
		return True


def _free_form_gate(gateway_name: str, phone: str) -> dict[str, Any] | None:
	"""Refusal for a free-form (non-template) send: opted-out contact, or a closed 24h customer-service window."""
	if _opted_out(gateway_name, phone):
		return {
			"success": False,
			"error": "opted_out",
			"message": "This contact opted out (STOP); no messages are sent until they opt back in (START).",
		}
	state = bridge.window_state(gateway_name, phone)
	if not state.get("open"):
		return {
			"success": False,
			"error": "window_closed",
			"message": "The 24-hour customer-service window is closed for this number.",
			"hint": "Send an approved template with send_template_message instead.",
			"expires_at": state.get("expires_at"),
		}
	return None


def _typed_send(gateway_name: str | None, to: Any, validate: Any, send: Any) -> dict[str, Any]:
	"""Shared pipeline of every free-form non-text send.

	bridge available -> write authority on the Gateway -> recipient -> payload validation (no network) ->
	opt-out + 24h window -> the Gateway's own account -> ``send(account, phone)``.
	"""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	refused = _send_authority(gateway_name)
	if refused:
		return refused
	phone = _validate_recipient(to)
	if isinstance(phone, dict):
		return phone
	errors = validate(phone)
	if errors:
		return wt.validation_error(errors)
	gated = _free_form_gate(gateway_name, phone)
	if gated:
		return gated
	account_name = _resolve_account_name(_gateway_whatsapp_account(gateway_name))
	if isinstance(account_name, dict):
		return account_name
	return send(account_name, phone)


def _read_uploaded_file(file_url: str) -> tuple[bytes, str, str] | dict[str, Any]:
	"""``(content, file name, mime type)`` of a Frappe File the caller may read (public or private), or an error dict."""
	file_url = str(file_url or "").strip()
	name = frappe.db.get_value("File", {"file_url": file_url}, "name") if file_url else None
	if not name:
		return {"success": False, "error": "invalid_file", "message": "Uploaded file not found."}
	doc = frappe.get_doc("File", name)
	if not frappe.has_permission("File", "read", doc=doc):
		raise frappe.PermissionError(_("Not permitted to read this file"))
	mime = mimetypes.guess_type(doc.file_name or file_url)[0] or ""
	return doc.get_content(), doc.file_name or file_url.rsplit("/", 1)[-1], mime


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
	media_id: str | None = None,
	voice: Any = None,
	reply_to: str | None = None,
) -> dict[str, Any]:
	"""Send an image/video/audio/document/sticker, only while the 24h window is open and the contact has not opted out.

	Give exactly one of: a public ``link`` (https URL), a ``media_id`` from :func:`upload_media_file`, or the
	``file_url`` of an uploaded File (a public ``/files/...`` file is sent by link; a private one is uploaded to
	Meta first and sent by id). ``caption`` is for image/video/document, ``filename`` for documents, ``voice``
	sends audio as a voice note (Ogg/Opus). Limits: image 5 MB jpeg/png, video 16 MB mp4/3gp, audio 16 MB,
	document 100 MB, sticker webp 100 KB (static) / 500 KB (animated).
	"""
	return _send_media_impl(gateway_name, to, kind, link, file_url, caption, filename, media_id, voice, reply_to)


def _send_media_impl(gateway_name, to, kind, link, file_url, caption, filename, media_id, voice, reply_to) -> dict[str, Any]:
	from_file = False
	if file_url and not link and not media_id:
		file_url = str(file_url).strip()
		if file_url.startswith("/files/"):
			resolved = _public_file_link(file_url)
			if isinstance(resolved, dict):
				return resolved
			link = resolved
		elif file_url.startswith("/private/files/"):
			from_file = True  # uploaded to Meta after the gates pass; sent by id
		else:
			return {"success": False, "error": "invalid_file", "message": "Only uploaded files (/files/... or /private/files/...) can be sent."}

	def validate(_phone: str) -> list[dict[str, str]]:
		probe = "https://pending-upload.invalid/file" if from_file else link
		return wt.validate_media_request(kind, probe, media_id, caption, filename, voice)[1]

	def send(account_name: str, phone: str) -> dict[str, Any]:
		use_id, use_name = media_id, filename
		if from_file:
			loaded = _read_uploaded_file(file_url)
			if isinstance(loaded, dict):
				return loaded
			content, fname, mime = loaded
			k = (kind or "").strip().lower()
			use_id = bridge.upload_media(account_name, content, mime, fname, kind=k or None, voice=bool(voice))["media_id"]
			use_name = filename or (fname if k == "document" else None)
		return bridge.send_media(
			account_name, phone, kind or "", link=link, media_id=use_id, caption=caption, filename=use_name,
			reply_to=reply_to, voice=voice,
		)

	return _typed_send(gateway_name, to, validate, send)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_voice_note(
	gateway_name: str | None = None,
	to: str | None = None,
	link: str | None = None,
	file_url: str | None = None,
	media_id: str | None = None,
	reply_to: str | None = None,
) -> dict[str, Any]:
	"""Send an audio message as a WhatsApp voice note (``audio.voice: true``); Ogg/Opus mono only, <= 16 MB.

	Non-Ogg/Opus input is rejected client-side: a ``link`` must end in .ogg/.opus and an uploaded ``file_url``
	must be audio/ogg (checked again against its real mime type on upload).
	"""
	if link and not media_id:
		errors = wm.validate_voice_link(link)
		if errors:
			return wt.validation_error(errors)
	if file_url and not link and not media_id and not str(file_url).lower().endswith(wm.VOICE_LINK_EXTENSIONS):
		return wt.validation_error([wm.err("file_url", "voice_needs_ogg_opus", "A voice note must be an Ogg file with the Opus codec.")])
	return _send_media_impl(gateway_name, to, "audio", link, file_url, None, None, media_id, True, reply_to)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def upload_media_file(
	gateway_name: str | None = None, file_url: str | None = None, kind: str | None = None, voice: Any = None
) -> dict[str, Any]:
	"""Upload an uploaded Frappe File to Meta (``POST /{phone_id}/media``); returns ``media_id`` (valid 30 days).

	Not window-gated (nothing is sent to a contact). The file must pass the per-kind mime and size caps.
	"""
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	refused = _send_authority(gateway_name)
	if refused:
		return refused
	loaded = _read_uploaded_file(file_url or "")
	if isinstance(loaded, dict):
		return loaded
	account_name = _resolve_account_name(_gateway_whatsapp_account(gateway_name))
	if isinstance(account_name, dict):
		return account_name
	content, fname, mime = loaded
	return bridge.upload_media(account_name, content, mime, fname, kind=(kind or "").strip().lower() or None, voice=bool(voice))


def _json_or_error(value: Any, label: str) -> Any:
	"""Parsed JSON argument; raises ``ValueError`` (caught by callers) on bad JSON."""
	return _parse_json_arg(value, label)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_sticker_message(
	gateway_name: str | None = None, to: str | None = None, link: str | None = None,
	media_id: str | None = None, file_url: str | None = None, reply_to: str | None = None,
) -> dict[str, Any]:
	"""Send a webp sticker (static <= 100 KB, animated <= 500 KB) by ``link``, ``media_id`` or uploaded ``file_url``."""
	return _send_media_impl(gateway_name, to, "sticker", link, file_url, None, None, media_id, None, reply_to)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_location_message(
	gateway_name: str | None = None, to: str | None = None, latitude: Any = None, longitude: Any = None,
	name: str | None = None, address: str | None = None, reply_to: str | None = None,
) -> dict[str, Any]:
	"""Send a map pin (latitude -90..90, longitude -180..180, optional name and address)."""
	return _typed_send(
		gateway_name,
		to,
		lambda p: wm.build_location_payload(p, latitude, longitude, name, address, reply_to)[1],
		lambda acct, p: bridge.send_location(acct, p, latitude, longitude, name=name, address=address, reply_to=reply_to),
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_contacts_message(
	gateway_name: str | None = None, to: str | None = None, contacts: Any = None, reply_to: str | None = None
) -> dict[str, Any]:
	"""Send contact card(s). ``contacts``: a list (or JSON) of ``{name: {formatted_name, ...}, phones, emails, urls, org, ...}``."""
	try:
		parsed = _json_or_error(contacts, "contacts")
	except ValueError as exc:
		return {"success": False, "error": "invalid_params", "message": str(exc)}
	return _typed_send(
		gateway_name,
		to,
		lambda p: wm.build_contacts_payload(p, parsed, reply_to)[1],
		lambda acct, p: bridge.send_contacts(acct, p, parsed, reply_to=reply_to),
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_reaction_message(
	gateway_name: str | None = None, to: str | None = None, message_id: str | None = None,
	emoji: str | None = None, remove: Any = None,
) -> dict[str, Any]:
	"""React to an inbound message with one emoji; an empty ``emoji`` (or ``remove``) removes the reaction.

	Meta delivers a reaction only for a message at most 30 days old that was not deleted and is not itself a reaction.
	"""
	rm = str(remove).strip().lower() in ("1", "true", "yes")
	return _typed_send(
		gateway_name,
		to,
		lambda p: wm.build_reaction_payload(p, message_id, emoji or "", rm)[1],
		lambda acct, p: bridge.send_reaction(acct, p, message_id or "", emoji or "", remove=rm),
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def send_interactive_message(
	gateway_name: str | None = None,
	to: str | None = None,
	kind: str | None = None,
	body: str | None = None,
	header: Any = None,
	footer: str | None = None,
	buttons: Any = None,
	button_text: str | None = None,
	sections: Any = None,
	display_text: str | None = None,
	url: str | None = None,
	flow_id: str | None = None,
	flow_name: str | None = None,
	flow_cta: str | None = None,
	flow_token: str | None = None,
	flow_action: str | None = None,
	screen: str | None = None,
	flow_data: Any = None,
	mode: str | None = None,
	reply_to: str | None = None,
) -> dict[str, Any]:
	"""Send an interactive message; ``kind`` is buttons | list | cta_url | location_request | flow.

	* buttons: ``body`` (<= 1024), ``buttons`` = 1-3 of ``{id (<= 256), title (<= 20)}``.
	* list: ``body`` (<= 4096), ``button_text`` (<= 20), ``sections`` = ``[{title (<= 24), rows: [{id, title (<= 24),
	  description (<= 72)}]}]`` (<= 10 rows in total).
	* cta_url: ``body`` (<= 1024), ``display_text`` (<= 20), ``url`` (https).
	* location_request: ``body`` (<= 1024); the contact answers with a location.
	* flow: UNTESTED; needs ``flow_id`` (or ``flow_name``) and ``flow_cta`` or it fails with ``flow_id_required``.

	``header`` is a text (<= 60) or ``{type: image|video|document, link | media_id}`` (text only for lists),
	``footer`` <= 60.
	"""
	try:
		spec = {
			"body": body, "footer": footer, "button_text": button_text, "display_text": display_text, "url": url,
			"header": _json_or_error(header, "header") if isinstance(header, str) and header.strip().startswith("{") else header,
			"buttons": _json_or_error(buttons, "buttons"), "sections": _json_or_error(sections, "sections"),
			"flow_id": flow_id, "flow_name": flow_name, "flow_cta": flow_cta, "flow_token": flow_token,
			"flow_action": flow_action, "screen": screen, "flow_data": _json_or_error(flow_data, "flow_data"), "mode": mode,
		}
	except ValueError as exc:
		return {"success": False, "error": "invalid_params", "message": str(exc)}
	return _typed_send(
		gateway_name,
		to,
		lambda p: wm.build_interactive_payload(p, kind, spec, reply_to)[1],
		lambda acct, p: bridge.send_interactive(acct, p, kind or "", spec, reply_to=reply_to),
	)


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
		return {"agent": None, "agent_run": None, "event": None, "status": None, "error": None, "solution": None}
	if direction == "out":
		return {
			"agent": event.get("target_agent"),
			"agent_run": event.get("agent_run"),
			"event": event["name"],
			"status": event.get("reply_status") or None,
			"error": event.get("delivery_error") or None,
			"solution": event.get("solution") or None,
		}
	return {
		"agent": event.get("target_agent"),
		"agent_run": event.get("agent_run"),
		"event": event["name"],
		"status": event.get("status") or None,
		"error": event.get("error_message") or None,
		"solution": event.get("solution") or None,
	}


def _solution_refs(names) -> dict[str, dict[str, str]]:
	"""{solution name: {"name", "title"}} for the given names (unknown names are left out)."""
	names = sorted({n for n in names if n})
	if not names:
		return {}
	rows = frappe.get_all("Solution", filters={"name": ["in", names]}, fields=["name", "title"])
	return {r["name"]: {"name": r["name"], "title": r.get("title") or r["name"]} for r in rows}


def _run_solutions(run_ids) -> dict[str, str]:
	run_ids = sorted({r for r in run_ids if r})
	if not run_ids:
		return {}
	rows = frappe.get_all("Agent Run", filters={"name": ["in", run_ids]}, fields=["name", "solution"])
	return {r["name"]: r["solution"] for r in rows if r.get("solution")}


def _solution_filter_ids(column, gateway: str, solution: str):
	"""Subquery of ``column`` (an event id column) for events of ``gateway`` that belong to ``solution``,
	directly (Gateway Event.solution) or through their Agent Run."""
	from frappe.query_builder import Criterion

	ev = frappe.qb.DocType("Gateway Event")
	run = frappe.qb.DocType("Agent Run")
	runs = frappe.qb.from_(run).select(run.name).where(run.solution == solution)
	return (
		frappe.qb.from_(ev)
		.select(column)
		.where(ev.gateway == gateway)
		.where(Criterion.any([ev.solution == solution, ev.agent_run.isin(runs)]))
		.where(column.isnotnull())
	)


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
	if f.get("solution"):
		sk = frappe.qb.DocType("WhatsApp Send Key")
		by_key = (
			frappe.qb.from_(sk).select(sk.message_id).where(sk.gateway == gateway)
			.where(sk.solution == f["solution"]).where(sk.message_id.isnotnull())
		)
		query = query.where(
			Criterion.any(
				[
					msg.message_id.isin(by_key),
					msg.message_id.isin(_solution_filter_ids(ev.provider_event_id, gateway, f["solution"])),
					msg.message_id.isin(_solution_filter_ids(ev.reply_message_id, gateway, f["solution"])),
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
				ev.status, ev.error_message, ev.reply_status, ev.delivery_error, ev.solution,
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

	key_solution: dict[str, str] = {}
	if ids:
		for k in frappe.get_all(
			"WhatsApp Send Key", filters={"gateway": gateway, "message_id": ["in", ids]},
			fields=["message_id", "solution", "agent_run"],
		):
			if k.get("solution"):
				key_solution[k["message_id"]] = k["solution"]
	run_solution = _run_solutions(e.get("agent_run") for e in events.values())
	solution_refs = _solution_refs(
		list(key_solution.values()) + list(run_solution.values()) + [e.get("solution") for e in events.values()]
	)

	items = []
	for r in rows:
		direction = "in" if r.get("type") == "Incoming" else "out"
		view = _event_view(events.get((direction, r.get("message_id"))), direction)
		sol_name = None
		if direction == "out":
			sol_name = key_solution.get(r.get("message_id")) or run_solution.get(view["agent_run"])
		sol_name = sol_name or view["solution"] or run_solution.get(view["agent_run"])
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
				"solution": solution_refs.get(sol_name),
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
		"_solution": e.get("solution") or None,
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
				ev.delivery_error, ev.solution,
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
		if f.get("solution"):
			_run = frappe.qb.DocType("Agent Run")
			q = q.where(
				Criterion.any(
					[
						ev.solution == f["solution"],
						ev.agent_run.isin(frappe.qb.from_(_run).select(_run.name).where(_run.solution == f["solution"])),
					]
				)
			)
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
	run_solution = _run_solutions(r.get("agent_run") for r in page)
	refs = _solution_refs([r.get("_solution") for r in page] + list(run_solution.values()))
	items = []
	for r in page:
		item = {k: v for k, v in r.items() if k not in ("_key", "_solution")}
		item["solution"] = refs.get(r.get("_solution") or run_solution.get(r.get("agent_run")))
		items.append(item)
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
	solution: str | None = None,
) -> dict[str, Any]:
	"""Gateway-scoped WhatsApp message log (newest first, keyset paginated).

	Each row carries ``solution`` (``{name, title}`` or None), derived from Huf-owned rows only (WhatsApp
	Send Key, Gateway Event, Agent Run); ``solution`` filters to one solution's messages.

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
			"solution": (solution or "").strip() or None,
			"start": start,
			"end": end,
		}
		runner = _bridge_log if ctx["bridge"] else _direct_log
		return runner(ctx, f, decoded, _log_limit(limit))
	except _LogError as exc:
		return exc.payload
	except BridgeError as exc:
		return dict(exc.payload, success=False)


def _gateway_solutions(gateway: str) -> list[dict[str, str]]:
	"""Solutions seen on this gateway: routed events, send keys and bindings (sorted by title)."""
	names: set[str] = set()
	for doctype, field in (("Gateway Event", "solution"), ("WhatsApp Send Key", "solution"), ("Gateway Binding", "solution")):
		names.update(
			n for n in frappe.get_all(
				doctype, filters={"gateway": gateway, field: ["is", "set"]}, pluck=field, distinct=True,
				limit_page_length=_LOG_FILTER_LIMIT,
			) if n
		)
	return sorted(_solution_refs(names).values(), key=lambda r: (r["title"].lower(), r["name"]))


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
		"solutions": _gateway_solutions(gateway),
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


@frappe.whitelist(methods=["POST"])
def check_token(gateway_name: str | None = None, force: Any = None) -> dict[str, Any]:
	"""Is this gateway's Meta access token still good? Admin only; 1 call/10 s per gateway, cached 10 min."""
	_require_admin()
	from huf.ai.whatsapp import token_check

	return token_check.check_token_for_gateway(
		gateway_name or "", force=str(force or "").lower() in ("1", "true", "yes")
	)


# --- WhatsApp Calling (EXPERIMENTAL; thin Graph wrappers, never invoked unless an admin calls them) ---


def _calls_graph(gateway_name: str | None) -> "wcalls.CallsGraph | dict[str, Any]":
	"""CallsGraph for the Gateway's own account (admin + write authority), or an error dict."""
	_require_admin()
	if not bridge.is_available():
		return {"success": False, "error": "bridge_unavailable"}
	refused = _send_authority(gateway_name)
	if refused:
		return refused
	account_name = _resolve_account_name(_gateway_whatsapp_account(gateway_name))
	if isinstance(account_name, dict):
		return account_name
	account = bridge.resolve_account(account_name)
	if not account or account.get("error"):
		return {"success": False, "error": "no_account", "message": "WhatsApp Account not found."}
	return wcalls.CallsGraph(account)


def _calling_gate(gateway_name: str | None) -> dict[str, Any] | None:
	"""Calling can only be switched on / driven when the Gateway itself has calling enabled."""
	enabled = False
	try:
		enabled = bool(frappe.db.get_value("Gateway", gateway_name, "calling_enabled")) if gateway_name else False
	except Exception:
		enabled = False
	if enabled:
		return None
	return {
		"success": False,
		"error": "calling_disabled",
		"message": "Enable calling on this Gateway before using WhatsApp Calling.",
	}


def _value_error(exc: ValueError) -> dict[str, Any]:
	return {"success": False, "error": "invalid_request", "message": str(exc)}


@frappe.whitelist()
@rate_limit(limit=30, seconds=60)
@_bridge_guard
def get_calling_settings(gateway_name: str | None = None) -> dict[str, Any]:
	"""Read the number's Calling settings from Graph (``GET /<PHONE_ID>/settings``)."""
	graph = _calls_graph(gateway_name)
	if isinstance(graph, dict):
		return graph
	return {"success": True, "settings": graph.get_settings()}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
@_bridge_guard
def set_calling_settings(
	gateway_name: str | None = None,
	calls_status: str | None = None,
	call_icon_visibility: str | None = None,
	greeting_media_id: str | None = None,
	callback_permission_status: str | None = None,
) -> dict[str, Any]:
	"""Change Calling settings. ``calls_status`` ENABLED|DISABLED, ``call_icon_visibility`` DEFAULT|DISABLE_ALL.

	``greeting_media_id`` is the id of an uploaded ``call_voicemail_announcement`` media (Opus, < 60 s).
	"""
	graph = _calls_graph(gateway_name)
	if isinstance(graph, dict):
		return graph
	if str(calls_status or "").upper() == "ENABLED":
		gated = _calling_gate(gateway_name)
		if gated:
			return gated
	try:
		payload = wcalls.calling_settings_payload(
			calls_status, call_icon_visibility, greeting_media_id, callback_permission_status
		)
	except ValueError as exc:
		return _value_error(exc)
	return {"success": True, "result": graph.set_settings(payload)}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
@_bridge_guard
def call_action(
	gateway_name: str | None = None, call_id: str | None = None, action: str | None = None, sdp: str | None = None
) -> dict[str, Any]:
	"""pre_accept | accept | reject | terminate a call. pre_accept/accept need the SDP answer."""
	graph = _calls_graph(gateway_name)
	if isinstance(graph, dict):
		return graph
	gated = _calling_gate(gateway_name)
	if gated:
		return gated
	try:
		return {"success": True, "result": graph.action(call_id or "", action or "", sdp)}
	except ValueError as exc:
		return _value_error(exc)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
@_bridge_guard
def send_call_permission_request(
	gateway_name: str | None = None, to: str | None = None, text: str | None = None
) -> dict[str, Any]:
	"""Send a ``call_permission_request`` interactive message (free-form: needs an open 24h window)."""
	graph = _calls_graph(gateway_name)
	if isinstance(graph, dict):
		return graph
	phone = _validate_recipient(to)
	if isinstance(phone, dict):
		return phone
	try:
		wcalls.permission_request_payload(phone, text or "")
	except ValueError as exc:
		return _value_error(exc)
	gated = _free_form_gate(gateway_name, phone)
	if gated:
		return gated
	return {"success": True, "result": graph.send_permission_request(phone, text or "")}


# --- Broadcast (WP-7) ----------------------------------------------------------------------------
# Thin API over broadcast_recipients / broadcast_limits / broadcast_cost / broadcast_runner. Those
# modules are imported lazily inside each function so that a problem there never breaks this module.
#
# Per-recipient retry of failed rows is deliberately NOT offered (no ``retry_failed_broadcast_recipients``):
# a ``failed`` row is a permanent Meta verdict (invalid number, user stopped marketing, template or quality
# problem) and ``unknown`` rows may already have been delivered, so re-sending either risks a duplicate or a
# repeat spam signal. A second attempt is a new, separately attested broadcast to a corrected list.

_PREPARE_RETRIES = 3
_BROADCAST = "WhatsApp Broadcast"
_BROADCAST_RECIPIENT = "WhatsApp Broadcast Recipient"
_BROADCAST_LOG = "huf.whatsapp.broadcast"
_BROADCAST_COUNT_FIELDS = (
	"total", "queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped",
)
_BROADCAST_FIELDS = (
	"name", "title", "status", "pause_reason", "gateway", "whatsapp_account", "template", "template_name",
	"language_code", "category", "body_params", "header_params", "button_params", "consent_source",
	"consent_attested", "consent_attested_by", "consent_attested_at", "max_recipients", "mps", "send_via",
	"started_by", "started_at", "finished_at", "creation", "modified", *_BROADCAST_COUNT_FIELDS,
)


def _broadcast_row(broadcast: Any) -> dict[str, Any] | dict[str, str]:
	"""The Broadcast's fields as a dict, or an error dict when it does not exist."""
	if not broadcast or not frappe.db.exists(_BROADCAST, broadcast):
		return _error("not_found", "Broadcast not found.")
	return frappe.db.get_value(_BROADCAST, broadcast, list(_BROADCAST_FIELDS), as_dict=True) or _error(
		"not_found", "Broadcast not found."
	)


def _broadcast_for_write(broadcast: Any) -> dict[str, Any]:
	"""Broadcast row after proving WRITE authority on ITS gateway (never trust a caller-supplied gateway)."""
	row = _broadcast_row(broadcast)
	if row.get("error"):
		return row
	if not _gateway_write_allowed(row.get("gateway")):
		raise frappe.PermissionError(_("Not permitted to manage broadcasts on this Gateway"))
	return row


def _broadcast_for_read(broadcast: Any) -> dict[str, Any]:
	row = _broadcast_row(broadcast)
	if row.get("error"):
		return row
	if not _gateway_read_allowed(row.get("gateway")):
		raise frappe.PermissionError(_("Not permitted to read broadcasts on this Gateway"))
	return row


def _broadcast_audit(broadcast: str, action: str, **details: Any) -> None:
	"""Audit every mutation: structured log line plus a Comment on the Broadcast."""
	user = getattr(frappe.session, "user", None)
	extra = ", ".join(f"{k}={v}" for k, v in details.items() if v not in (None, ""))
	frappe.logger(_BROADCAST_LOG).info(f"broadcast={broadcast} action={action} user={user} {extra}".strip())
	try:
		frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", f"{action} by {user}" + (f": {extra}" if extra else ""))
	except Exception:
		frappe.logger(_BROADCAST_LOG).warning(f"broadcast={broadcast} action={action}: audit comment failed")


def _broadcast_view(row: dict[str, Any]) -> dict[str, Any]:
	out = {k: row.get(k) for k in _BROADCAST_FIELDS if k not in _BROADCAST_COUNT_FIELDS}
	out["counts"] = {k: int(row.get(k) or 0) for k in _BROADCAST_COUNT_FIELDS}
	for key in ("body_params", "header_params", "button_params"):
		value = out.get(key)
		if isinstance(value, str) and value:
			try:
				out[key] = json.loads(value)
			except ValueError:
				pass
	for key in ("creation", "modified", "started_at", "finished_at", "consent_attested_at"):
		out[key] = _iso(out.get(key))
	return out


def _queued_count(broadcast: str) -> int:
	"""Recipients still to send (queued + deferred): same set as broadcast_cost.confirm_token and the runner."""
	return int(frappe.db.count(_BROADCAST_RECIPIENT, {"broadcast": broadcast, "status": ["in", ["queued", "deferred"]]}) or 0)


def _mask_phone(value: Any) -> Any:
	text = str(value or "")
	return ("*" * max(len(text) - 4, 0) + text[-4:]) if text else value


_LONG_DIGITS_RE = re.compile(r"\d{7,}")


def _mask_digits(text: Any) -> Any:
	return _LONG_DIGITS_RE.sub(lambda m: _mask_phone(m.group(0)), text) if isinstance(text, str) else text


def _json_param(value: Any, label: str) -> Any:
	parsed = _parse_json_arg(value, label)
	return parsed if parsed not in ("", None) else None


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def create_broadcast(
	gateway: str | None = None,
	template: str | None = None,
	title: str | None = None,
	language_code: str | None = None,
	body_params: Any = None,
	header_params: Any = None,
	button_params: Any = None,
	consent_source: str | None = None,
	max_recipients: Any = None,
	mps: Any = None,
	send_via: str | None = None,
) -> dict[str, Any]:
	"""Create a Draft broadcast on a Gateway. The template must be an APPROVED template of the Gateway's own account.

	Category, template name and account are snapshotted here; ``start`` re-checks them. Needs write authority on the Gateway.
	"""
	refused = _send_authority(gateway)
	if refused:
		return refused
	account = _gateway_whatsapp_account(gateway)
	if not account:
		return _error("no_account", "This gateway is not linked to a WhatsApp Account.")
	if not template or not _TEMPLATE_RECORD_RE.match(str(template).strip()):
		return _error("invalid_name", "Template must be the Meta name or '<name>-<language_code>'.")
	if not title or not str(title).strip():
		return _error("invalid_title", "A title is required.")
	from huf.ai.whatsapp import broadcast_recipients as br

	docname = bridge._template_docname(account, str(template).strip(), language_code or None)
	tpl = None
	if docname and frappe.db.exists("WhatsApp Templates", docname):
		tpl = frappe.db.get_value(
			"WhatsApp Templates",
			docname,
			["name", "whatsapp_account", "status", "category", "actual_name", "template_name", "language_code"],
			as_dict=True,
		)
	if not tpl or tpl.get("whatsapp_account") != account:
		return _error("template_not_found", "Template not found on this gateway's WhatsApp account.")
	if str(tpl.get("status") or "").upper() != "APPROVED":
		return _error("template_not_approved", f"Template status is {tpl.get('status') or 'unknown'}; only APPROVED templates can be broadcast.")
	send_via = (send_via or "messages").strip()
	if send_via not in ("messages", "marketing_messages"):
		return _error("invalid_send_via", "send_via must be 'messages' or 'marketing_messages'.")
	if send_via == "marketing_messages" and str(tpl.get("category") or "").upper() != "MARKETING":
		return _error("mm_requires_marketing_template", "The Marketing Messages API only accepts MARKETING templates.")
	try:
		body = _json_param(body_params, "body_params")
		header = _json_param(header_params, "header_params")
		buttons = _json_param(button_params, "button_params")
		cap = int(max_recipients) if max_recipients not in (None, "") else None
		if cap is not None and not 1 <= cap <= br.MAX_RECIPIENTS_CEILING:
			return _error("invalid_max_recipients", f"max_recipients must be between 1 and {br.MAX_RECIPIENTS_CEILING}.")
		rate = int(mps) if mps not in (None, "") else None
	except (TypeError, ValueError) as exc:
		return _error("invalid_params", str(exc))
	frappe.flags.in_broadcast_api = True
	doc = frappe.get_doc(
		{
			"doctype": _BROADCAST,
			"title": str(title).strip(),
			"status": "Draft",
			"gateway": gateway,
			"whatsapp_account": account,
			"template": tpl.get("name"),
			"template_name": tpl.get("actual_name") or tpl.get("template_name") or tpl.get("name"),
			"language_code": language_code or tpl.get("language_code"),
			"category": tpl.get("category"),
			"body_params": json.dumps(body) if body is not None else None,
			"header_params": json.dumps(header) if header is not None else None,
			"button_params": json.dumps(buttons) if buttons is not None else None,
			"consent_source": (consent_source or "").strip() or None,
			"consent_attested": 0,
			"max_recipients": cap,
			"mps": rate,
			"send_via": send_via,
		}
	).insert(ignore_permissions=True)  # authority was proven by _send_authority above
	_broadcast_audit(doc.name, "created", gateway=gateway, template=tpl.get("name"), category=tpl.get("category"))
	return {"success": True, "broadcast": doc.name, "status": "Draft", "category": tpl.get("category")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def add_broadcast_recipients(broadcast: str | None = None, recipients: Any = None, csv_text: str | None = None) -> dict[str, Any]:
	"""Add recipients to a Draft broadcast, from a list (``["+1555..", {"recipient":..,"params":..}]``) or CSV text."""
	row = _broadcast_for_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") != "Draft":
		return _error("not_draft", "Recipients can only be added while the broadcast is a Draft.")
	from huf.ai.whatsapp import broadcast_recipients as br

	if csv_text and len(str(csv_text).encode("utf-8")) > br.MAX_CSV_BYTES:
		return _error("csv_too_large", f"csv_text is limited to {br.MAX_CSV_BYTES // (1024 * 1024)} MB.")
	try:
		items = _parse_json_arg(recipients, "recipients") or []
		if isinstance(items, list) and len(items) > br.MAX_ROWS_PER_REQUEST:
			return _error("too_many_recipients", f"At most {br.MAX_ROWS_PER_REQUEST} recipients per request.")
		if csv_text and str(csv_text).strip():
			items = list(items) + list(br.parse_csv(str(csv_text)))
	except ValueError as exc:
		return _error("invalid_params", str(exc))
	if not isinstance(items, list) or not items:
		return _error("no_recipients", "Provide recipients or csv_text.")
	if len(items) > br.MAX_ROWS_PER_REQUEST:
		return _error("too_many_recipients", f"At most {br.MAX_ROWS_PER_REQUEST} recipients per request.")
	rows = [{"recipient": str(i)} if not isinstance(i, dict) else i for i in items]
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True  # recipient rows are insert-guarded; prepare() is the only writer
	result = None
	try:
		for attempt in range(_PREPARE_RETRIES):
			try:
				result = br.prepare(broadcast, rows)
				break
			except frappe.QueryDeadlockError:
				frappe.db.rollback()  # the whole prepare is idempotent (duplicates are skipped), so redo it
				if attempt < _PREPARE_RETRIES - 1:
					time.sleep(random.uniform(0.05, 0.25))
	finally:
		frappe.flags.in_broadcast_api = prev
	if result is None:
		return _error("busy_retry", "Another request is updating this broadcast; retry in a moment.")
	if row.get("consent_attested"):
		# the attestation covered a different list; the owner must re-attest
		frappe.flags.in_broadcast_api = True
		try:
			frappe.db.set_value(_BROADCAST, broadcast, {
				"consent_attested": 0, "consent_attested_by": None, "consent_attested_at": None,
			})
		finally:
			frappe.flags.in_broadcast_api = prev
		frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", "attestation reset: recipients changed")
	_broadcast_audit(
		broadcast, "recipients_added",
		added=result.get("added"), skipped=result.get("skipped_total"), invalid=result.get("invalid_total"),
	)
	return {"success": True, **result}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def attest_broadcast_consent(broadcast: str | None = None, consent_source: str | None = None) -> dict[str, Any]:
	"""Record that the caller attests recipients opted in to this kind of message (source of the opt-in is required)."""
	row = _broadcast_for_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") not in ("Draft", "Paused"):
		return _error("invalid_state", "Consent can only be attested on a Draft or Paused broadcast.")
	source = (consent_source or "").strip()
	if not source:
		return _error("consent_source_required", "State where the recipients' opt-in was collected.")
	now = frappe.utils.now_datetime()
	frappe.flags.in_broadcast_api = True
	frappe.db.set_value(
		_BROADCAST,
		broadcast,
		{
			"consent_attested": 1,
			"consent_attested_by": frappe.session.user,
			"consent_attested_at": now,
			"consent_source": source,
		},
	)
	_broadcast_audit(broadcast, "consent_attested", consent_source=source)
	return {"success": True, "broadcast": broadcast, "consent_attested": True, "consent_source": source}


@frappe.whitelist()
@_bridge_guard
def preview_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Pre-flight: limits and warnings, cost estimate and the count the operator must type to start. Read-only."""
	row = _broadcast_for_write(broadcast)  # preview feeds the start decision, so it needs write authority too
	if row.get("error"):
		return row
	from huf.ai.whatsapp import broadcast_cost, broadcast_limits

	limits = broadcast_limits.preview(broadcast)
	cost = broadcast_cost.estimate(broadcast)
	token = broadcast_cost.confirm_token(broadcast)
	frappe.db.set_value(_BROADCAST, broadcast, "cost_estimate", json.dumps(cost, default=str), update_modified=False)
	return {
		"success": True,
		"broadcast": broadcast,
		"status": row.get("status"),
		"consent_attested": bool(row.get("consent_attested")),
		"limits": limits,
		"cost": cost,
		"confirm_required": int(token or 0) > 0,
		"queued": _queued_count(broadcast),
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
@_bridge_guard
def start_broadcast(broadcast: str | None = None, confirm_count: Any = None) -> dict[str, Any]:
	"""Start (or restart a Draft) broadcast. Requires attested consent and the typed count to equal the queued recipients."""
	row = _broadcast_for_write(broadcast)
	if row.get("error"):
		return row
	if not row.get("consent_attested"):
		return _error("consent_not_attested", "Attest that recipients opted in before starting.")
	queued = _queued_count(broadcast)
	if queued <= 0:
		return _error("no_recipients", "There are no queued recipients.")
	if str(confirm_count if confirm_count is not None else "").strip() != str(queued):
		return _error("confirm_mismatch", f"Type the number of queued recipients ({queued}) to confirm.")
	from huf.ai.whatsapp import broadcast_runner

	result = broadcast_runner.start(broadcast, user=frappe.session.user)
	_broadcast_audit(broadcast, "started", queued=queued)
	return {"success": True, "broadcast": broadcast, "queued": queued, **(result if isinstance(result, dict) else {})}


def _runner_action(broadcast: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
	row = _broadcast_for_write(broadcast)
	if row.get("error"):
		return row
	from huf.ai.whatsapp import broadcast_runner

	result = getattr(broadcast_runner, action)(broadcast, **kwargs)
	_broadcast_audit(broadcast, action, **kwargs)
	status = frappe.db.get_value(_BROADCAST, broadcast, "status")
	return {"success": True, "broadcast": broadcast, "status": status, **(result if isinstance(result, dict) else {})}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def pause_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Pause a running broadcast; queued rows stay queued."""
	return _runner_action(broadcast, "pause", reason="manual")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def resume_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Resume a paused broadcast."""
	return _runner_action(broadcast, "resume")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@_bridge_guard
def cancel_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Cancel a broadcast: queued rows become skipped (cancelled); already sent messages are unaffected."""
	return _runner_action(broadcast, "cancel")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
@_bridge_guard
def pause_all_broadcasts(gateway: str | None = None) -> dict[str, Any]:
	"""Kill switch: pause every running broadcast of a Gateway."""
	refused = _send_authority(gateway)
	if refused:
		return refused
	running = frappe.get_all(_BROADCAST, filters={"gateway": gateway, "status": "Running"}, pluck="name") or []
	from huf.ai.whatsapp import broadcast_runner

	result = broadcast_runner.pause_all(gateway, "kill_switch")
	for name in running:
		_broadcast_audit(name, "pause_all", gateway=gateway)
	frappe.logger(_BROADCAST_LOG).info(f"gateway={gateway} action=pause_all user={frappe.session.user} paused={len(running)}")
	return {"success": True, "gateway": gateway, "paused": running, **(result if isinstance(result, dict) else {})}


@frappe.whitelist()
@_bridge_guard
def list_broadcasts(gateway: str | None = None, status: str | None = None, limit: Any = 50, offset: Any = 0) -> dict[str, Any]:
	"""List broadcasts (newest first) with counts. A non-admin must name a Gateway they can read."""
	filters: dict[str, Any] = {}
	if gateway:
		if not frappe.db.exists("Gateway", gateway):
			return _error("not_found", "Gateway not found.")
		if not _gateway_read_allowed(gateway):
			raise frappe.PermissionError(_("Not permitted to read this Gateway"))
		filters["gateway"] = gateway
	elif not _can_manage_integrations():
		return _gateway_required()
	if status:
		filters["status"] = status
	try:
		skip = max(0, int(offset))
	except (TypeError, ValueError):
		skip = 0
	rows = frappe.get_all(
		_BROADCAST, filters=filters, fields=list(_BROADCAST_FIELDS), order_by="creation desc",
		limit_start=skip, limit_page_length=_clamp_limit(limit),
	)
	return {"success": True, "broadcasts": [_broadcast_view(r) for r in rows or []]}


@frappe.whitelist()
@_bridge_guard
def get_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""One broadcast with its status counters."""
	row = _broadcast_for_read(broadcast)
	if row.get("error"):
		return row
	return {"success": True, "broadcast": _broadcast_view(row)}


@frappe.whitelist()
@_bridge_guard
def list_broadcast_recipients(broadcast: str | None = None, status: str | None = None, limit: Any = 100, offset: Any = 0) -> dict[str, Any]:
	"""Recipient rows of a broadcast, optionally filtered by status."""
	row = _broadcast_for_read(broadcast)
	if row.get("error"):
		return row
	filters: dict[str, Any] = {"broadcast": broadcast}
	if status:
		filters["status"] = status
	try:
		skip = max(0, int(offset))
	except (TypeError, ValueError):
		skip = 0
	masked = not _gateway_write_allowed(row.get("gateway"))
	rows = frappe.get_all(
		_BROADCAST_RECIPIENT, filters=filters,
		fields=["name", "recipient", "status", "skip_reason", "wamid", "message_status", "attempts", "next_attempt_at",
			"error_code", "error_message", "sent_at", "delivered_at", "read_at", "failed_at"],
		order_by="creation asc", limit_start=skip, limit_page_length=_clamp_limit(limit),
	)
	out = [dict(r, **{k: _iso(r.get(k)) for k in ("next_attempt_at", "sent_at", "delivered_at", "read_at", "failed_at")}) for r in rows or []]
	if masked:  # read-only Gateway users must not see the full phone list (L5)
		for r in out:
			r["recipient"] = _mask_phone(r.get("recipient"))
			r["error_message"] = _mask_digits(r.get("error_message"))
			r["name"] = _mask_digits(r.get("name"))
	return {"success": True, "recipients": out}
