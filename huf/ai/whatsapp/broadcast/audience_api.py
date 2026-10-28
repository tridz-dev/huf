# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp audiences: whitelisted API (create, import, members, selection preview).

Permissions follow the Gateway pattern of ``broadcast.api``: every call proves read or write authority on the
audience's own Gateway (never a caller-supplied gateway). Audience consent is attested server-side. Opt-out is
read from the gateway's consent records and never written here.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, now_datetime, strip_html_tags

from huf.ai.whatsapp.broadcast import audience as aud
from huf.ai.whatsapp.broadcast import recipients as broadcast_recipients
from huf.ai.whatsapp.management import (
	_bridge_guard,
	_error,
	_gateway_read_allowed,
	_gateway_write_allowed,
	_iso,
	_parse_json_arg,
)

# Rate limits (calls per RATE_SECONDS). WP-A's policy.py is not on this branch yet; the coordinator
# rewires these to the per-endpoint API limits in policy.
RATE_SECONDS = 60
RATE_LIMIT_WRITE = 60
RATE_LIMIT_IMPORT = 20
RATE_LIMIT_READ = 240
REQUIRE_CONSENT_ATTESTATION = True  # Huf's own record of consent (Meta requires opt-in for business-initiated messages)
MAX_SELECTION_ITEMS = 25
_LOG = "huf.whatsapp.audience"

_AUDIENCE_FIELDS = (
	"name", "gateway", "title", "description", "is_adhoc", "consent_source", "consent_basis",
	"purpose_marketing", "purpose_utility", "purpose_events", "default_consent_at", "consent_attested_by",
	"consent_attested_at", "member_count", "suppressed_count", "creation", "modified",
)  # fmt: skip
_ON_CONFLICT = ("skip", "update", "fail")
_AUTO_HEADERS = {
	"phone": broadcast_recipients.PHONE_HEADERS,
	"name": {"name", "display_name", "full_name", "contact", "customer"},
	"tags": {"tags", "tag", "segment", "segments", "labels"},
	"consent_source": {"consent_source"},
	"consent_at": {"consent_at", "consent_date", "consented_at"},
}


# --- guards ----------------------------------------------------------------------------------------
def _guard(fn):
	"""Turn validation failures into the standard error dict (permission errors still raise)."""
	import functools

	@functools.wraps(fn)
	def wrapper(*args: Any, **kwargs: Any):
		try:
			return fn(*args, **kwargs)
		except frappe.PermissionError:
			raise
		except (frappe.ValidationError, ValueError) as exc:
			return _error("invalid", strip_html_tags(str(exc)) or "Invalid request.")

	return wrapper


def _audience_row(audience: Any) -> dict[str, Any]:
	if not audience or not frappe.db.exists(aud.AUDIENCE, audience):
		return _error("not_found", "Audience not found.")
	return frappe.db.get_value(aud.AUDIENCE, audience, list(_AUDIENCE_FIELDS), as_dict=True)


def _require_audience_write(audience: Any) -> dict[str, Any]:
	row = _audience_row(audience)
	if row.get("error"):
		return row
	if not _gateway_write_allowed(row.get("gateway")):
		raise frappe.PermissionError(_("Not permitted to manage audiences on this Gateway"))
	return row


def _require_audience_read(audience: Any) -> dict[str, Any]:
	row = _audience_row(audience)
	if row.get("error"):
		return row
	if not _gateway_read_allowed(row.get("gateway")):
		raise frappe.PermissionError(_("Not permitted to read audiences on this Gateway"))
	return row


def _require_gateway(gateway: Any, write: bool) -> dict[str, Any] | None:
	"""None when the Gateway exists and the caller has the authority, else an error dict (or raises)."""
	if not gateway or not frappe.db.exists("Gateway", gateway):
		return _error("gateway_required", "Choose a WhatsApp gateway.")
	allowed = _gateway_write_allowed(gateway) if write else _gateway_read_allowed(gateway)
	if not allowed:
		raise frappe.PermissionError(_("Not permitted to manage audiences on this Gateway"))
	return None


def _audit(audience: str, action: str, **details: Any) -> None:
	user = getattr(frappe.session, "user", None)
	extra = ", ".join(f"{k}={v}" for k, v in details.items() if v not in (None, ""))
	frappe.logger(_LOG).info(f"audience={audience} action={action} user={user} {extra}".strip())
	try:
		frappe.get_doc(aud.AUDIENCE, audience).add_comment("Info", f"{action} by {user}" + (f": {extra}" if extra else ""))
	except Exception:
		frappe.logger(_LOG).warning(f"audience={audience} action={action}: audit comment failed")


def _view(row: dict[str, Any]) -> dict[str, Any]:
	out = {k: row.get(k) for k in _AUDIENCE_FIELDS if not k.startswith("purpose_")}
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


# --- audiences -------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
@rate_limit(limit=RATE_LIMIT_WRITE, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def create_audience(
	gateway: str | None = None,
	title: str | None = None,
	consent_source: str | None = None,
	consent_basis: str | None = None,
	consent_purposes: Any = None,
	consent_attested: Any = None,
	description: str | None = None,
	default_consent_at: str | None = None,
	is_adhoc: Any = 0,
) -> dict[str, Any]:
	"""Create an audience. Needs write on the Gateway. The attester and time are set here, not by the client."""
	denied = _require_gateway(gateway, write=True)
	if denied:
		return denied
	purposes = _parse_purposes(consent_purposes)
	if not purposes:
		return _error("purposes_required", "Choose what these contacts agreed to receive.")
	if REQUIRE_CONSENT_ATTESTATION and not _flag(consent_attested):
		return _error("consent_not_attested", "Confirm that these contacts agreed to receive your messages.")
	if default_consent_at:
		try:
			when = get_datetime(default_consent_at)
		except Exception:
			return _error("invalid", "The consent date is not a valid date.")
		if when > get_datetime(now_datetime()):
			return _error("invalid", "The consent date cannot be in the future.")
	frappe.flags.in_audience_api = True
	doc = frappe.get_doc(
		{
			"doctype": aud.AUDIENCE,
			"gateway": gateway,
			"title": title,
			"description": description,
			"consent_source": consent_source,
			"consent_basis": consent_basis,
			"default_consent_at": default_consent_at or None,
			"is_adhoc": 1 if _flag(is_adhoc) else 0,
			**{f"purpose_{p}": 1 if p in purposes else 0 for p in aud.PURPOSES},
		}
	)
	doc.insert(ignore_permissions=True)
	_audit(doc.name, "created", gateway=gateway, purposes=",".join(sorted(purposes)))
	return {"success": True, "audience": _view(_audience_row(doc.name))}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=RATE_LIMIT_WRITE, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def update_audience(
	audience: str | None = None,
	title: str | None = None,
	description: str | None = None,
	consent_source: str | None = None,
	consent_purposes: Any = None,
) -> dict[str, Any]:
	"""Edit title, description, consent source text, or narrow the consent purposes.

	Attestation, consent date, basis and gateway are fixed at creation; purposes can only be narrowed.
	A title change is refused while an unfinished broadcast uses the audience.
	"""
	row = _require_audience_write(audience)
	if row.get("error"):
		return row
	doc = frappe.get_doc(aud.AUDIENCE, audience)
	if title is not None:
		doc.title = title
	if description is not None:
		doc.description = description
	if consent_source is not None:
		doc.consent_source = consent_source
	if consent_purposes is not None:
		purposes = _parse_purposes(consent_purposes)
		if not purposes:
			return _error("purposes_required", "Keep at least one consent purpose.")
		for p in aud.PURPOSES:
			doc.set(f"purpose_{p}", 1 if p in purposes else 0)
	doc.save(ignore_permissions=True)
	_audit(audience, "updated")
	return {"success": True, "audience": _view(_audience_row(audience))}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=RATE_LIMIT_WRITE, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def delete_audience(audience: str | None = None) -> dict[str, Any]:
	"""Delete an audience and its members. Refused while a Draft/Queued/Running/Paused broadcast uses it."""
	row = _require_audience_write(audience)
	if row.get("error"):
		return row
	used = aud.referencing_broadcasts(audience)
	if used:
		return _error(
			"audience_in_use",
			"This audience is used by a broadcast that has not finished: "
			+ ", ".join(f"{u['name']} ({u['status']})" for u in used[:5]),
		)
	_audit(audience, "deleted", members=row.get("member_count"))
	frappe.flags.in_audience_api = True
	frappe.delete_doc(aud.AUDIENCE, audience, ignore_permissions=True, force=True)  # finished broadcasts keep the name
	return {"success": True}


@frappe.whitelist()
@rate_limit(limit=RATE_LIMIT_READ, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def list_audiences(
	gateway: str | None = None,
	search: str | None = None,
	include_adhoc: Any = 0,
	start: Any = 0,
	limit: Any = 50,
) -> dict[str, Any]:
	denied = _require_gateway(gateway, write=False)
	if denied:
		return denied
	filters: dict[str, Any] = {"gateway": gateway}
	if not _flag(include_adhoc):
		filters["is_adhoc"] = 0
	or_filters = {"title": ["like", f"%{search.strip()}%"]} if search and search.strip() else None
	rows = frappe.get_all(
		aud.AUDIENCE,
		filters=filters,
		or_filters=or_filters,
		fields=list(_AUDIENCE_FIELDS),
		order_by="modified desc",
		limit_start=max(cint(start), 0),
		limit_page_length=_page(limit),
	)
	total = len(frappe.get_all(aud.AUDIENCE, filters=filters, or_filters=or_filters, pluck="name"))
	return {"success": True, "audiences": [_view(r) for r in rows], "total": total}


@frappe.whitelist()
@rate_limit(limit=RATE_LIMIT_READ, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def get_audience(audience: str | None = None) -> dict[str, Any]:
	row = _require_audience_read(audience)
	if row.get("error"):
		return row
	tag_counts: dict[str, int] = {}
	for value in frappe.get_all(aud.MEMBER, {"audience": audience}, pluck="tags", limit_page_length=0):
		for tag in aud._as_list(value):
			tag_counts[tag] = tag_counts.get(tag, 0) + 1
	view = _view(row)
	view["tags"] = [{"tag": t, "count": c} for t, c in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
	view["used_by"] = aud.referencing_broadcasts(audience)
	view["can_see_numbers"] = bool(_gateway_write_allowed(row["gateway"]))
	return {"success": True, "audience": view}


# --- members ---------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
@rate_limit(limit=RATE_LIMIT_IMPORT, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def import_members(
	audience: str | None = None,
	csv_text: str | None = None,
	rows: Any = None,
	mapping: Any = None,
	on_conflict: str = "skip",
) -> dict[str, Any]:
	"""Add contacts from CSV text or a list of row dicts.

	``mapping``: ``{"phone": col, "name": col, "tags": col, "consent_source": col, "consent_at": col,
	"params": [col, ...]}`` where ``col`` is a CSV header (or a key of a row dict). Without a mapping,
	known headers (phone, name, tags, consent_source, consent_at) are detected. ``params`` columns become
	the template body values in order. ``on_conflict``: ``skip`` (keep existing), ``update`` (overwrite
	provided fields, merge tags) or ``fail`` (write nothing when any contact already exists).

	Up to ``LIMIT_INLINE_IMPORT_ROWS`` rows are imported in the request and the totals returned. Larger
	files run as a background job: the result has ``queued: true`` and a ``job_id`` for
	:func:`get_import_status`.
	"""
	row = _require_audience_write(audience)
	if row.get("error"):
		return row
	if on_conflict not in _ON_CONFLICT:
		return _error("invalid", f"on_conflict must be one of {', '.join(_ON_CONFLICT)}.")
	mapped = _mapped_rows(csv_text, rows, _parse_json_arg(mapping, "mapping"))
	if isinstance(mapped, dict):
		return mapped
	if not mapped:
		return _error("no_rows", "There are no contacts to import.")
	if on_conflict == "fail":
		existing = set(frappe.get_all(aud.MEMBER, {"audience": audience}, pluck="recipient", limit_page_length=0))
		clashes = [r["recipient"] for r in mapped if broadcast_recipients.normalize_recipient(r.get("recipient")) in existing]
		if clashes:
			return {**_error("conflicts", "Some contacts are already in this audience."), "conflicts": clashes[:50]}
	if len(mapped) > aud.LIMIT_INLINE_IMPORT_ROWS:
		job_id = frappe.generate_hash(length=16)
		aud.set_job_state(job_id, {"job_id": job_id, "audience": audience, "status": "queued", "processed": 0, "total": len(mapped)})
		frappe.enqueue(
			"huf.ai.whatsapp.broadcast.audience.run_import_job",
			queue="long",
			timeout=3600,
			audience=audience,
			rows=mapped,
			on_conflict=on_conflict,
			job_id=job_id,
			user=frappe.session.user,
		)
		_audit(audience, "import queued", rows=len(mapped), job_id=job_id)
		return {"success": True, "queued": True, "job_id": job_id, "rows": len(mapped)}
	result = aud.import_rows(audience, mapped, on_conflict)
	counts = aud.refresh_counts(audience, row["gateway"])
	_audit(audience, "imported", added=result["added"], updated=result["updated"], invalid=result["invalid_total"])
	return {"success": True, "queued": False, **result, **counts}


@frappe.whitelist()
@rate_limit(limit=RATE_LIMIT_READ, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def get_import_status(job_id: str | None = None, audience: str | None = None) -> dict[str, Any]:
	"""Progress of a background import. ``audience`` is required so read access can be proved."""
	row = _require_audience_read(audience)
	if row.get("error"):
		return row
	state = aud.get_job_state(str(job_id or ""))
	if not state or state.get("audience") != audience:
		return _error("not_found", "Import not found or expired.")
	return {"success": True, **state}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=RATE_LIMIT_WRITE, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def remove_members(audience: str | None = None, recipients: Any = None) -> dict[str, Any]:
	"""Remove contacts (by phone number) from an audience."""
	row = _require_audience_write(audience)
	if row.get("error"):
		return row
	wanted = _parse_list(recipients, "recipients")
	if len(wanted) > aud.LIMIT_MAX_REMOVE_PER_REQUEST:
		return _error("too_many", f"Remove at most {aud.LIMIT_MAX_REMOVE_PER_REQUEST} contacts per request.")
	phones = [p for p in (broadcast_recipients.normalize_recipient(r) for r in wanted) if p]
	before = frappe.db.count(aud.MEMBER, {"audience": audience})
	for i in range(0, len(phones), 1000):
		frappe.db.delete(aud.MEMBER, {"audience": audience, "recipient": ["in", phones[i : i + 1000]]})
	counts = aud.refresh_counts(audience, row["gateway"])
	removed = before - counts["member_count"]
	_audit(audience, "removed members", removed=removed)
	return {"success": True, "removed": removed, **counts}


@frappe.whitelist()
@rate_limit(limit=RATE_LIMIT_READ, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def list_members(
	audience: str | None = None,
	search: str | None = None,
	tags: Any = None,
	tag_mode: str = "any",
	suppressed: Any = None,
	start: Any = 0,
	limit: Any = 50,
) -> dict[str, Any]:
	"""One page of members. Phone numbers are masked (last 4 digits) unless the caller can manage the Gateway.

	``suppressed``: true = only contacts who opted out, false = only the others. Each row has a
	``suppressed`` reason (``opted_out`` / ``marketing_opted_out``) or null.
	"""
	row = _require_audience_read(audience)
	if row.get("error"):
		return row
	wanted_tags = aud.normalize_tags(_parse_json_arg(tags, "tags") if isinstance(tags, str) and tags.strip().startswith("[") else tags)
	only = None if suppressed in (None, "") else _flag(suppressed)
	filters: dict[str, Any] = {"audience": audience}
	if search and search.strip():
		term = search.strip()
		filters["recipient"] = ["like", f"%{''.join(c for c in term if c.isdigit()) or term}%"]
	fields = ["recipient", "display_name", "tags", "consent_source", "consent_at", "source", "added_at"]
	size, offset = _page(limit), max(cint(start), 0)
	if wanted_tags or only is not None:
		members = frappe.get_all(aud.MEMBER, filters=filters, fields=fields, order_by="recipient asc", limit_page_length=0)
		members = [m for m in members if aud.tags_match(aud._as_list(m["tags"]), wanted_tags, tag_mode)]
		reasons = aud.suppression_map(row["gateway"], [m["recipient"] for m in members]) if only is not None else None
		if only is not None:
			members = [m for m in members if bool(reasons.get(m["recipient"])) == only]
		total = len(members)
		page = members[offset : offset + size]
	else:
		total = frappe.db.count(aud.MEMBER, filters)
		page = frappe.get_all(aud.MEMBER, filters=filters, fields=fields, order_by="recipient asc", limit_start=offset, limit_page_length=size)
	reasons = aud.suppression_map(row["gateway"], [m["recipient"] for m in page])
	reveal = bool(_gateway_write_allowed(row["gateway"]))
	out = []
	for m in page:
		out.append(
			{
				"recipient": m["recipient"] if reveal else aud.mask_phone(m["recipient"]),
				"display_name": m["display_name"],
				"tags": aud._as_list(m["tags"]),
				"consent_source": m["consent_source"],
				"consent_at": _iso(m["consent_at"]),
				"source": m["source"],
				"added_at": _iso(m["added_at"]),
				"suppressed": reasons.get(m["recipient"]),
			}
		)
	return {"success": True, "members": out, "total": total, "masked": not reveal}


# --- selection preview -----------------------------------------------------------------------------
@frappe.whitelist()
@rate_limit(limit=RATE_LIMIT_READ, seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def preview_audience_selection(broadcast: str | None = None, selection: Any = None) -> dict[str, Any]:
	"""Counts for a set of audience picks on a broadcast: total, duplicates, excluded, suppressed, blocked.

	``selection``: ``[{"audience", "tag_filter_mode": "any"|"all", "tags": [], "exclude": false}]``.
	A MARKETING template can only use audiences that include the marketing purpose; those that do not are
	listed in ``blocked`` with code ``audience_purpose_mismatch``.
	"""
	if not broadcast or not frappe.db.exists(aud.BROADCAST, broadcast):
		return _error("not_found", "Broadcast not found.")
	gateway = frappe.db.get_value(aud.BROADCAST, broadcast, "gateway")
	if not _gateway_read_allowed(gateway):
		raise frappe.PermissionError(_("Not permitted to read broadcasts on this Gateway"))
	items = _parse_selection(selection)
	if not any(not aud._truthy(i.get("exclude")) for i in items):
		return _error("invalid", "Pick at least one audience to include.")
	for item in items:
		other = frappe.db.get_value(aud.AUDIENCE, item.get("audience"), "gateway") if item.get("audience") else None
		if other != gateway:
			return _error("invalid", "Every audience must belong to the same WhatsApp gateway as the broadcast.")
	audiences, members = aud.load_inputs(items)
	category = aud.template_category(broadcast)
	everyone = {m["recipient"] for rows in members.values() for m in rows}
	suppressed = aud.suppression_map(gateway, everyone, marketing=str(category or "").upper() == "MARKETING")
	result = aud.expand_selection(items, audiences, members, suppressed, category)
	needed = aud.purpose_for_category(category)
	blocked = [
		{
			"code": "audience_purpose_mismatch",
			"audience": name,
			"message": f"{audiences[name]['title']} was not collected for {needed} messages.",
		}
		for name in result["blocked_audiences"]
	]
	return {
		"success": True,
		"counts": result["counts"],
		"per_audience": result["per_audience"],
		"blocked": blocked,
		"category": category,
		"purpose_required": needed,
	}


def _parse_selection(selection: Any) -> list[dict]:
	items = _parse_list(selection, "selection")
	if len(items) > MAX_SELECTION_ITEMS:
		raise ValueError(f"Pick at most {MAX_SELECTION_ITEMS} audiences.")
	if not all(isinstance(i, dict) and i.get("audience") for i in items):
		raise ValueError("Each pick needs an audience.")
	return items


# --- CSV / mapping ---------------------------------------------------------------------------------
def _mapped_rows(csv_text: Any, rows: Any, mapping: Any) -> list[dict] | dict[str, Any]:
	"""Rows in ``import_rows`` shape, or an error dict."""
	if csv_text and rows:
		return _error("invalid", "Send either csv_text or rows, not both.")
	if csv_text:
		if len(str(csv_text).encode("utf-8")) > aud.LIMIT_MAX_CSV_BYTES:
			return _error("csv_too_large", f"The file is larger than {aud.LIMIT_MAX_CSV_BYTES // (1024 * 1024)} MB.")
		reader = csv.reader(io.StringIO(str(csv_text).lstrip("﻿")))
		table = [cells for cells in reader if any(c.strip() for c in cells)]
		if not table:
			return []
		headers = [h.strip() for h in table[0]]
		records = [dict(zip(headers, row + [""] * (len(headers) - len(row)), strict=False)) for row in table[1:]]
	else:
		records = _parse_list(rows, "rows")
		if not all(isinstance(r, dict) for r in records):
			return _error("invalid", "rows must be a list of objects.")
		headers = list(records[0].keys()) if records else []
	if len(records) > aud.LIMIT_MAX_IMPORT_ROWS:
		return _error("too_many", f"Import at most {aud.LIMIT_MAX_IMPORT_ROWS} contacts at a time.")
	columns = _resolve_mapping(headers, mapping)
	if isinstance(columns, dict) and columns.get("error"):
		return columns
	out = []
	for rec in records:
		item: dict[str, Any] = {"recipient": rec.get(columns["phone"])}
		for field, key in (("display_name", "name"), ("tags", "tags"), ("consent_source", "consent_source"), ("consent_at", "consent_at")):
			if columns.get(key):
				item[field] = rec.get(columns[key])
		if columns.get("params"):
			item["params"] = {"body": [str(rec.get(c) if rec.get(c) is not None else "") for c in columns["params"]]}
		out.append(item)
	return out


def _resolve_mapping(headers: list[str], mapping: Any) -> dict[str, Any]:
	lowered = {h.strip().lower().replace("-", "_"): h for h in headers}
	cols: dict[str, Any] = {}
	if mapping:
		if not isinstance(mapping, dict):
			return _error("invalid", "mapping must be an object.")
		cols = {("phone" if k == "recipient" else k): v for k, v in mapping.items()}
		wanted = [v for k, v in cols.items() if k != "params" and v] + list(cols.get("params") or [])
		missing = [c for c in wanted if c not in headers]
		if missing:
			return _error("unknown_column", f"These columns are not in the file: {', '.join(map(str, missing))}")
	for key, names in _AUTO_HEADERS.items():
		if not cols.get(key):
			found = next((lowered[n] for n in lowered if n in names), None)
			if found:
				cols[key] = found
	if not cols.get("phone"):
		return _error("mapping_missing_phone", "Choose which column holds the phone number.")
	return cols


def _flag(value: Any) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


def _page(limit: Any) -> int:
	return min(max(cint(limit) or 50, 1), aud.LIMIT_PAGE_SIZE_MAX)
