# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Small helpers shared by the audience API modules (argument parsing, views, audit trail)."""

from __future__ import annotations

import functools
from typing import Any

import frappe
from frappe.utils import cint, strip_html_tags

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.management import _error, _iso, _parse_json_arg

_LOG = "huf.whatsapp.audience"
AUDIENCE_FIELDS = (
	"name", "gateway", "title", "description", "is_adhoc", "consent_source", "consent_basis",
	"purpose_marketing", "purpose_utility", "purpose_events", "default_consent_at", "consent_attested_by",
	"consent_attested_at", "member_count", "suppressed_count", "creation", "modified",
)  # fmt: skip


def _guard(fn):
	"""Turn validation failures into the standard error dict (permission errors still raise)."""
	@functools.wraps(fn)
	def wrapper(*args: Any, **kwargs: Any):
		try:
			return fn(*args, **kwargs)
		except frappe.PermissionError:
			raise
		except (frappe.ValidationError, ValueError) as exc:
			return _error("invalid", strip_html_tags(str(exc)) or "Invalid request.")

	return wrapper


def _audit(audience: str, action: str, **details: Any) -> None:
	user = getattr(frappe.session, "user", None)
	extra = ", ".join(f"{k}={v}" for k, v in details.items() if v not in (None, ""))
	frappe.logger(_LOG).info(f"audience={audience} action={action} user={user} {extra}".strip())
	try:
		frappe.get_doc(aud.AUDIENCE, audience).add_comment("Info", f"{action} by {user}" + (f": {extra}" if extra else ""))
	except Exception:
		frappe.logger(_LOG).warning(f"audience={audience} action={action}: audit comment failed")


def _view(row: dict[str, Any]) -> dict[str, Any]:
	out = {k: row.get(k) for k in AUDIENCE_FIELDS if not k.startswith("purpose_")}
	out["consent_purposes"] = [p for p in aud.PURPOSES if cint(row.get(f"purpose_{p}"))]
	out["is_adhoc"] = bool(cint(row.get("is_adhoc")))
	for key in ("default_consent_at", "consent_attested_at", "creation", "modified"):
		out[key] = _iso(out.get(key))
	return out


def _parse_purposes(value: Any) -> set[str]:
	value = _parse_json_arg(value, "consent_purposes") if isinstance(value, str) and value.strip().startswith("[") else value
	if isinstance(value, str):
		value = [p for p in value.replace(";", ",").split(",")]
	chosen = {str(p).strip().lower() for p in (value or []) if str(p).strip()}
	unknown = chosen - set(aud.PURPOSES)
	if unknown:
		raise ValueError(f"Unknown consent purpose: {', '.join(sorted(unknown))}")
	return chosen


def _parse_list(value: Any, label: str) -> list:
	parsed = _parse_json_arg(value, label)
	if parsed in (None, ""):
		return []
	if not isinstance(parsed, list):
		raise ValueError(f"{label} must be a list")
	return parsed


def _flag(value: Any) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


def _page(limit: Any) -> int:
	return min(max(cint(limit) or 50, 1), policy.get("audience_page_size_max"))

