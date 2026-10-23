# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Message Template management API (gateway admins only).

CRUD for the ``Telegram Message Template`` doctype, a no-send preview, and a guarded test send.
Rendering/sending is owned by ``huf.ai.telegram_templates`` (lazy import); a small local renderer is
used only when that module is absent. A test send is refused unless the destination chat is one the
caller paired/approved themselves, or one explicitly marked as a test chat on a Gateway Access Entry.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe
from frappe import _

from huf.ai.telegram_management import (
	TELEGRAM_PROVIDER,
	_can_manage_integrations,
	_error,
	_require_gateway_admin,
)

DOCTYPE = "Telegram Message Template"
PARSE_MODES = ("Plain", "HTML", "MarkdownV2")
MEDIA_TYPES = ("none", "photo", "video", "animation", "document", "audio", "voice", "sticker")
TEST_CHAT_MARKER = "telegram-test"
TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-]{0,79}$")
VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_FIELDS = [
	"name",
	"template_name",
	"gateway",
	"language",
	"parse_mode",
	"media_type",
	"is_active",
	"description",
	"last_used_at",
	"modified",
]
_SAVE_FIELDS = (
	"template_name",
	"gateway",
	"language",
	"parse_mode",
	"body",
	"media_type",
	"media",
	"buttons_json",
	"is_active",
	"description",
)


def _require_manager() -> None:
	if not _can_manage_integrations():
		raise frappe.PermissionError(_("Not permitted to manage Telegram templates"))


def _require_doctype(ptype: str, doc: Any = None) -> None:
	if not frappe.has_permission(DOCTYPE, ptype, doc=doc):
		raise frappe.PermissionError(_("Not permitted to {0} Telegram templates").format(ptype))


def _as_dict(raw: Any) -> dict[str, Any] | None:
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return None
	return raw if isinstance(raw, dict) else None


def detect_variables(*texts: str) -> list[str]:
	"""Variable names used in the given texts, in first-seen order."""
	seen: list[str] = []
	for text in texts:
		for m in VAR_RE.finditer(text or ""):
			if m.group(1) not in seen:
				seen.append(m.group(1))
	return seen


def _problem(field: str, message: str) -> dict[str, str]:
	return {"field": field, "message": message}


def validate_values(values: dict[str, Any]) -> list[dict[str, str]]:
	"""Field-level problems with a template payload. Pure (the buttons check lazy-imports the spec parser)."""
	out: list[dict[str, str]] = []
	name = str(values.get("template_name") or "").strip()
	if not name:
		out.append(_problem("template_name", "Give the template a name."))
	elif not NAME_RE.match(name):
		out.append(
			_problem("template_name", "Use letters, numbers, spaces, dashes and underscores (max 80).")
		)
	mode = values.get("parse_mode") or "HTML"
	if mode not in PARSE_MODES:
		out.append(_problem("parse_mode", "Parse mode must be Plain, HTML or MarkdownV2."))
	media_type = values.get("media_type") or "none"
	if media_type not in MEDIA_TYPES:
		out.append(_problem("media_type", "Unknown media type."))
	body = str(values.get("body") or "")
	has_media = media_type not in ("none", "sticker") and media_type in MEDIA_TYPES
	if media_type != "none" and media_type in MEDIA_TYPES and not values.get("media"):
		out.append(_problem("media", "Attach a file or enter a link for the media."))
	if not body.strip() and media_type in ("none", ""):
		out.append(_problem("body", "Write the message text."))
	if len(body) > TEXT_LIMIT:
		out.append(_problem("body", f"Telegram allows at most {TEXT_LIMIT} characters of text."))
	elif has_media and len(body) > CAPTION_LIMIT:
		out.append(
			_problem("body", f"With media the text is sent as a caption (max {CAPTION_LIMIT} characters).")
		)
	buttons = values.get("buttons_json")
	if buttons and str(buttons).strip():
		from huf.ai.gateway_adapters import telegram_buttons

		# Variables inside button values are substituted at send time, so validate with placeholders swapped.
		probe = VAR_RE.sub("x", buttons if isinstance(buttons, str) else json.dumps(buttons))
		spec, errors = telegram_buttons.validate(probe)
		if spec is None or errors:
			out.append(_problem("buttons_json", "; ".join(errors) or "Invalid buttons."))
	seen: set[str] = set()
	for i, row in enumerate(values.get("variables") or []):
		var = str((row or {}).get("variable") or "").strip()
		if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var):
			out.append(_problem(f"variables.{i}", "Variable names use letters, numbers and underscores."))
		elif var in seen:
			out.append(_problem(f"variables.{i}", f"Variable {var} is listed twice."))
		seen.add(var)
	return out


def _row(doc: Any) -> dict[str, Any]:
	data = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
	out = {k: data.get(k) for k in (*_SAVE_FIELDS, "name", "last_used_at", "modified")}
	out["variables"] = [
		{
			"variable": v.get("variable"),
			"default_value": v.get("default_value") or "",
			"example": v.get("example") or "",
		}
		for v in data.get("variables") or []
	]
	return out


@frappe.whitelist()
def list_templates(gateway: str | None = None) -> dict[str, Any]:
	_require_manager()
	if gateway:
		_require_gateway_admin(gateway)
	_require_doctype("read")
	filters: dict[str, Any] = {}
	or_filters = [{"gateway": gateway}, {"gateway": ["is", "not set"]}] if gateway else None
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		or_filters=or_filters,
		fields=_FIELDS,
		order_by="modified desc",
		limit_page_length=500,
	)
	return {"success": True, "templates": [dict(r) for r in rows or []]}


@frappe.whitelist()
def get_template(name: str | None = None) -> dict[str, Any]:
	_require_manager()
	if not name or not frappe.db.exists(DOCTYPE, name):
		return _error("not_found", "Template not found.")
	doc = frappe.get_doc(DOCTYPE, name)
	_require_doctype("read", doc)
	if doc.get("gateway"):
		_require_gateway_admin(doc.gateway)
	return {"success": True, "template": _row(doc)}


@frappe.whitelist(methods=["POST"])
def save_template(values: Any = None, name: str | None = None) -> dict[str, Any]:
	"""Create (no ``name``) or update a template. Field problems come back as ``{error: invalid, problems}``."""
	_require_manager()
	data = _as_dict(values)
	if data is None:
		return _error("invalid", "Template values must be an object.")
	name = name or data.get("name")
	problems = validate_values(data)
	if problems:
		return {"success": False, "error": "invalid", "message": problems[0]["message"], "problems": problems}
	gateway = data.get("gateway")
	if gateway:
		_require_gateway_admin(gateway)
		if not frappe.db.exists("Gateway", {"name": gateway, "provider": TELEGRAM_PROVIDER}):
			return {
				"success": False,
				"error": "invalid",
				"problems": [_problem("gateway", "Choose a Telegram gateway.")],
			}
	payload = {k: data.get(k) for k in _SAVE_FIELDS if k in data}
	if isinstance(payload.get("buttons_json"), (dict, list)):
		payload["buttons_json"] = json.dumps(payload["buttons_json"])
	payload["variables"] = [
		{
			"variable": v["variable"].strip(),
			"default_value": v.get("default_value") or "",
			"example": v.get("example") or "",
		}
		for v in data.get("variables") or []
	]
	if name:
		if not frappe.db.exists(DOCTYPE, name):
			return _error("not_found", "Template not found.")
		doc = frappe.get_doc(DOCTYPE, name)
		_require_doctype("write", doc)
		doc.update(payload)
	else:
		_require_doctype("create")
		doc = frappe.get_doc({"doctype": DOCTYPE, **payload})
	try:
		doc.save()
	except frappe.DuplicateEntryError:
		return {
			"success": False,
			"error": "invalid",
			"problems": [_problem("template_name", "A template with this name already exists.")],
		}
	except frappe.ValidationError as exc:
		return {
			"success": False,
			"error": "invalid",
			"message": str(exc),
			"problems": [_problem("form", str(exc))],
		}
	return {"success": True, "template": _row(doc)}


@frappe.whitelist(methods=["POST"])
def delete_template(name: str | None = None) -> dict[str, Any]:
	_require_manager()
	if not name or not frappe.db.exists(DOCTYPE, name):
		return _error("not_found", "Template not found.")
	doc = frappe.get_doc(DOCTYPE, name)
	_require_doctype("delete", doc)
	if doc.get("gateway"):
		_require_gateway_admin(doc.gateway)
	frappe.delete_doc(DOCTYPE, name)
	return {"success": True}


# -- preview ---------------------------------------------------------------------------------------


def _escape(mode: str, text: str) -> str:
	from huf.ai.gateway_adapters.telegram_format import escape_html, escape_markdown_v2

	return escape_html(text) if mode == "HTML" else escape_markdown_v2(text) if mode == "MarkdownV2" else text


def local_render(values: dict[str, Any], variables: dict[str, Any] | None) -> dict[str, Any]:
	"""Safe fallback renderer: substitutes escaped values; unknown variables are reported, never evaluated."""
	mode = values.get("parse_mode") or "HTML"
	defaults = {
		str(v.get("variable")): str(v.get("default_value") or "") for v in values.get("variables") or []
	}
	given = {str(k): str(v) for k, v in (variables or {}).items() if v not in (None, "")}
	missing: list[str] = []

	def sub(match: re.Match) -> str:
		key = match.group(1)
		val = given.get(key) or defaults.get(key)
		if not val:
			if key not in missing:
				missing.append(key)
			return match.group(0)
		return _escape(mode, val)

	text = VAR_RE.sub(sub, str(values.get("body") or ""))
	markup = None
	errors: list[str] = []
	buttons = values.get("buttons_json")
	if buttons and str(buttons).strip():
		from huf.ai.gateway_adapters import telegram_buttons

		spec, errors = telegram_buttons.validate(
			VAR_RE.sub(lambda m: given.get(m.group(1)) or defaults.get(m.group(1)) or "x", buttons)
		)
		if spec:
			markup = telegram_buttons.build_markup(spec, lambda p: p)
	media = None
	if (values.get("media_type") or "none") != "none" and values.get("media"):
		media = {"type": values["media_type"], "source": "file_url", "value": values["media"]}
	return {
		"text": text,
		"parse_mode": "" if mode == "Plain" else mode,
		"media": media,
		"markup": markup,
		"missing": missing,
		"errors": errors,
	}


@frappe.whitelist(methods=["POST"])
def preview_template(
	name_or_values: Any = None, variables: Any = None, gateway: str | None = None
) -> dict[str, Any]:
	"""No-send preview of a saved template (by name) or unsaved editor values (object)."""
	_require_manager()
	vars_ = _as_dict(variables) or {}
	values = _as_dict(name_or_values)
	if values is None:
		name = str(name_or_values or "")
		if not name or not frappe.db.exists(DOCTYPE, name):
			return _error("not_found", "Template not found.")
		_require_doctype("read", frappe.get_doc(DOCTYPE, name))
		try:
			from huf.ai import telegram_templates
		except ImportError:
			telegram_templates = None
		if telegram_templates is not None:
			return {"success": True, "preview": telegram_templates.preview_template(name, vars_, gateway)}
		values = _row(frappe.get_doc(DOCTYPE, name))
	return {"success": True, "preview": local_render(values, vars_)}


# -- test send -------------------------------------------------------------------------------------


def is_allowed_test_chat(gateway: str, chat_id: str, user: str) -> bool:
	"""True for an approved access entry on this gateway that the caller approved, or that is marked as a test chat."""
	rows = frappe.get_all(
		"Gateway Access Entry",
		filters={"gateway": gateway, "external_id": str(chat_id), "state": "Approved"},
		fields=["approved_by", "notes"],
		limit_page_length=20,
	)
	for r in rows or []:
		if r.get("approved_by") == user or TEST_CHAT_MARKER in (r.get("notes") or "").lower():
			return True
	return False


@frappe.whitelist(methods=["POST"])
def send_test_template(
	gateway: str | None = None,
	chat_id: str | None = None,
	name: str | None = None,
	variables: Any = None,
	confirm: Any = None,
) -> dict[str, Any]:
	if not gateway:
		return _error("gateway_required", "Choose a Telegram gateway.")
	_require_manager()
	_require_gateway_admin(gateway)
	if str(confirm).lower() not in ("1", "true", "yes"):
		return _error("confirm_required", "Confirm that you want to send this test message.")
	chat = str(chat_id or "").strip()
	if not re.fullmatch(r"-?\d{1,20}", chat):
		return _error("invalid_chat", "Enter a numeric Telegram chat id.")
	if not frappe.db.exists("Gateway", {"name": gateway, "provider": TELEGRAM_PROVIDER}):
		return _error("not_found", "Gateway not found.")
	if not is_allowed_test_chat(gateway, chat, frappe.session.user):
		return _error(
			"chat_not_allowed",
			"Test messages can only go to a chat you paired yourself, or one marked '"
			+ TEST_CHAT_MARKER
			+ "' in its access notes.",
		)
	if not name or not frappe.db.exists(DOCTYPE, name):
		return _error("not_found", "Template not found.")
	_require_doctype("read", frappe.get_doc(DOCTYPE, name))
	try:
		from huf.ai import telegram_templates
	except ImportError:
		return _error("unavailable", "Template sending is not available on this site yet.")
	try:
		result = telegram_templates.send_template(
			frappe.get_doc("Gateway", gateway), chat, name, _as_dict(variables) or {}
		)
	except Exception as exc:
		return _error("send_failed", str(exc)[:300])
	return {"success": True, "result": result}
