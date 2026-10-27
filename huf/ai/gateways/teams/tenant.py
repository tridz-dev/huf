"""Microsoft Teams tenant allowlist (T5).

``Teams Gateway Settings.allowed_tenants`` holds one Entra tenant GUID per line. When it
is empty only the bot's home tenant (credential ``tenant_id``) is accepted. The
``pre_ingest_filter`` handler drops any event whose tenant is missing or not allowed.
"""

from __future__ import annotations

import re
import time
from types import SimpleNamespace
from typing import Any

import frappe
from frappe import _

from huf.ai.gateways import hooks
from huf.ai.gateways.teams.contract import (
	HOOK_PRIORITY_TENANT,
	PROVIDER_LABEL,
	REASON_TENANT_NOT_ALLOWED,
)

SETTINGS_DOCTYPE = "Teams Gateway Settings"
POLICIES = ("Always private", "Private when records touched", "Channel")
DEFAULT_POLICY = "Private when records touched"
CACHE_TTL_SECONDS = 30
_FIELDS = ("allowed_tenants", "bot_handle", "app_package_version", "private_output_policy", "help_text_override")
_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

_CACHE: dict[str, tuple[float, dict]] = {}


# ---- GUID helpers -------------------------------------------------------------
def normalize_guid(value: Any) -> str:
	"""Return the lowercase GUID, or "" when ``value`` is not a plain GUID (no braces, no domains)."""
	text = str(value).strip().lower() if isinstance(value, str) else ""
	return text if _GUID_RE.match(text) else ""


def parse_tenant_text(text: Any, *, strict: bool = False) -> list[str]:
	"""Split newline/comma separated text into unique lowercase GUIDs (order kept).

	With ``strict`` any non-GUID entry raises ValidationError instead of being skipped.
	"""
	out: list[str] = []
	for raw in re.split(r"[\n\r,;]+", text or ""):
		raw = raw.strip()
		if not raw:
			continue
		guid = normalize_guid(raw)
		if not guid:
			if strict:
				frappe.throw(_("Not a valid tenant ID (GUID): {0}").format(raw), frappe.ValidationError)
			continue
		if guid not in out:
			out.append(guid)
	return out


def normalize_tenant_text(text: Any) -> str:
	return "\n".join(parse_tenant_text(text, strict=True))


# ---- settings -----------------------------------------------------------------
def clear_cache(gateway: str | None = None) -> None:
	if gateway:
		_CACHE.pop(gateway, None)
	else:
		_CACHE.clear()


def _defaults(gateway: str) -> dict:
	return {
		"gateway": gateway,
		"allowed_tenants": "",
		"bot_handle": "",
		"app_package_version": "",
		"private_output_policy": DEFAULT_POLICY,
		"help_text_override": "",
	}


def get_settings(gateway: str) -> dict:
	"""Settings for ``gateway`` (cached ~30s; defaults when no record exists)."""
	now = time.monotonic()
	hit = _CACHE.get(gateway)
	if hit and hit[0] > now:
		return dict(hit[1])
	row = frappe.db.get_value(SETTINGS_DOCTYPE, gateway, list(_FIELDS), as_dict=True) if gateway else None
	data = _defaults(gateway)
	if row:
		for key in _FIELDS:
			value = row.get(key)
			if value:
				data[key] = value
	_CACHE[gateway] = (now + CACHE_TTL_SECONDS, data)
	return dict(data)


def get_allowed_tenants(gateway: str) -> list[str]:
	return parse_tenant_text(get_settings(gateway)["allowed_tenants"])


def get_gateway_credential(gateway, key: str) -> str:
	"""Same logic as ``slack_context.get_gateway_credential`` (kept local to avoid a Slack import)."""
	name = getattr(gateway, "integration_settings", None)
	if not name:
		return ""
	settings = frappe.get_doc("Integration Settings", name)
	for row in settings.credentials or []:
		if row.key == key:
			return row.get_password("value") or ""
	return ""


def get_home_tenant(gateway) -> str:
	return normalize_guid(get_gateway_credential(gateway, "tenant_id"))


def is_tenant_allowed(gateway, tenant_id: Any) -> bool:
	"""``gateway`` is a Gateway doc/object. Empty allowlist means the home tenant only."""
	guid = normalize_guid(tenant_id)
	if not guid:
		return False
	allowed = get_allowed_tenants(gateway.name)
	if allowed:
		return guid in allowed
	home = get_home_tenant(gateway)
	return bool(home) and guid == home


# ---- pre_ingest_filter --------------------------------------------------------
def tenants_in_context(context: Any) -> list[Any]:
	"""Every tenant claim found (channelData.tenant.id, conversation.tenantId, context tenant_id)."""
	if not isinstance(context, dict):
		return []
	found: list[Any] = []
	raw = context.get("raw_payload")
	if isinstance(raw, dict):
		tenant = (raw.get("channelData") or {}).get("tenant") if isinstance(raw.get("channelData"), dict) else None
		if isinstance(tenant, dict) and tenant.get("id"):
			found.append(tenant["id"])
		conv = raw.get("conversation")
		if isinstance(conv, dict) and conv.get("tenantId"):
			found.append(conv["tenantId"])
	if context.get("tenant_id"):
		found.append(context["tenant_id"])
	return found


def pre_ingest_filter(gateway, context) -> bool:
	"""False (drop) when the tenant is missing/unparseable/not allowed. Fail closed."""
	claims = tenants_in_context(context)
	if claims and all(is_tenant_allowed(gateway, c) for c in claims):
		return True
	frappe.flags.gateway_filter_reason = REASON_TENANT_NOT_ALLOWED
	try:
		frappe.logger("huf.teams").warning(
			"%s gateway=%s", REASON_TENANT_NOT_ALLOWED, getattr(gateway, "name", "")
		)
	except Exception:
		pass
	return False


def register() -> None:
	hooks.register(
		hooks.PRE_INGEST_FILTER,
		pre_ingest_filter,
		provider=PROVIDER_LABEL,
		priority=HOOK_PRIORITY_TENANT,
	)


register()


# ---- whitelisted API ----------------------------------------------------------
def _authorize(gateway: str, ptype: str) -> None:
	if not gateway or not isinstance(gateway, str):
		frappe.throw(_("Choose a gateway."), frappe.ValidationError)
	if "System Manager" in (frappe.get_roles() or []):
		pass
	elif not frappe.has_permission("Gateway", ptype, doc=gateway):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("Gateway", gateway):
		frappe.throw(_("Gateway not found."), frappe.DoesNotExistError)


@frappe.whitelist()
def get_teams_settings(gateway: str) -> dict:
	_authorize(gateway, "read")
	data = get_settings(gateway)
	data["allowed_tenant_list"] = parse_tenant_text(data["allowed_tenants"])
	return data


@frappe.whitelist(methods=["POST"])
def save_teams_settings(
	gateway: str,
	allowed_tenants: str | list | None = None,
	bot_handle: str | None = None,
	app_package_version: str | None = None,
	private_output_policy: str | None = None,
	help_text_override: str | None = None,
) -> dict:
	_authorize(gateway, "write")
	values: dict[str, Any] = {}
	if allowed_tenants is not None:
		if isinstance(allowed_tenants, (list, tuple)):
			allowed_tenants = "\n".join(str(t) for t in allowed_tenants)
		values["allowed_tenants"] = normalize_tenant_text(allowed_tenants)
	if private_output_policy is not None:
		if private_output_policy not in POLICIES:
			frappe.throw(_("Unknown private output policy."), frappe.ValidationError)
		values["private_output_policy"] = private_output_policy
	for key, val in (
		("bot_handle", bot_handle),
		("app_package_version", app_package_version),
		("help_text_override", help_text_override),
	):
		if val is not None:
			values[key] = str(val).strip()
	if frappe.db.exists(SETTINGS_DOCTYPE, gateway):
		doc = frappe.get_doc(SETTINGS_DOCTYPE, gateway)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": SETTINGS_DOCTYPE, "gateway": gateway, **values})
		doc.insert(ignore_permissions=True)
	clear_cache(gateway)
	return get_teams_settings(gateway)
