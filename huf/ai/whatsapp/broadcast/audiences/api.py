# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp audiences: whitelisted API (create, import, members, selection preview).

Permissions follow the Gateway pattern of ``broadcast.api``: every call proves read or write authority on the
audience's own Gateway (never a caller-supplied gateway). Audience consent is attested server-side. Opt-out is
read from the gateway's consent records and never written here.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, now_datetime

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast import recipients as broadcast_recipients
from huf.ai.whatsapp.broadcast.audiences import csv_map as audience_csv
from huf.ai.whatsapp.broadcast.audiences import importer as audience_import
from huf.ai.whatsapp.broadcast.audiences import selection as audience_selection
from huf.ai.whatsapp.broadcast.audiences.common import (
	AUDIENCE_FIELDS,
	_audit,
	_flag,
	_guard,
	_page,
	_parse_list,
	_parse_purposes,
	_view,
)
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

_ON_CONFLICT = ("skip", "update", "fail")

# --- guards ----------------------------------------------------------------------------------------


def _audience_row(audience: Any) -> dict[str, Any]:
	if not audience or not frappe.db.exists(aud.AUDIENCE, audience):
		return _error("not_found", "Audience not found.")
	return frappe.db.get_value(aud.AUDIENCE, audience, list(AUDIENCE_FIELDS), as_dict=True)


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










# --- audiences -------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_audience_write"), seconds=RATE_SECONDS)
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
	if policy.get("require_consent_attestation") and not _flag(consent_attested):
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
@rate_limit(limit=policy.rate("rate_audience_write"), seconds=RATE_SECONDS)
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
@rate_limit(limit=policy.rate("rate_audience_write"), seconds=RATE_SECONDS)
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
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
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
		fields=list(AUDIENCE_FIELDS),
		order_by="modified desc",
		limit_start=max(cint(start), 0),
		limit_page_length=_page(limit),
	)
	total = len(frappe.get_all(aud.AUDIENCE, filters=filters, or_filters=or_filters, pluck="name"))
	return {"success": True, "audiences": [_view(r) for r in rows], "total": total}


@frappe.whitelist()
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
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
@rate_limit(limit=policy.rate("rate_audience_import"), seconds=RATE_SECONDS)
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

	Up to ``audience_inline_import_rows`` rows are imported in the request and the totals returned, with
	``invalid`` / ``skipped`` example lists (``{row, recipient, reason}``, capped at ``returned_list_limit``;
	the ``*_total`` counts are exact). Larger files run as a background job: the result has ``queued: true``
	and a ``job_id`` for :func:`get_import_status`, which returns the same lists once the job is done.
	"""
	row = _require_audience_write(audience)
	if row.get("error"):
		return row
	if on_conflict not in _ON_CONFLICT:
		return _error("invalid", f"on_conflict must be one of {', '.join(_ON_CONFLICT)}.")
	mapped = audience_csv.mapped_rows(csv_text, rows, _parse_json_arg(mapping, "mapping"))
	if isinstance(mapped, dict):
		return mapped
	if not mapped:
		return _error("no_rows", "There are no contacts to import.")
	if on_conflict == "fail":
		existing = set(frappe.get_all(aud.MEMBER, {"audience": audience}, pluck="recipient", limit_page_length=0))
		clashes = [r["recipient"] for r in mapped if broadcast_recipients.normalize_recipient(r.get("recipient")) in existing]
		if clashes:
			return {**_error("conflicts", "Some contacts are already in this audience."), "conflicts": clashes[:50]}
	if len(mapped) > policy.get("audience_inline_import_rows"):
		job_id = frappe.generate_hash(length=16)
		audience_import.set_job_state(job_id, {"job_id": job_id, "audience": audience, "status": "queued", "processed": 0, "total": len(mapped)})
		frappe.enqueue(
			"huf.ai.whatsapp.broadcast.audiences.importer.run_import_job",
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
	result = audience_import.import_rows(audience, mapped, on_conflict)
	counts = aud.refresh_counts(audience, row["gateway"])
	_audit(audience, "imported", added=result["added"], updated=result["updated"], invalid=result["invalid_total"])
	result["invalid"] = audience_import.example_rows(result.get("invalid"), True)
	result["skipped"] = audience_import.example_rows(result.get("skipped"), True)
	return {"success": True, "queued": False, **result, **counts}


@frappe.whitelist()
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def get_import_status(job_id: str | None = None, audience: str | None = None) -> dict[str, Any]:
	"""Progress of a background import. ``audience`` is required so read access can be proved."""
	row = _require_audience_read(audience)
	if row.get("error"):
		return row
	state = audience_import.get_job_state(str(job_id or ""))
	if not state or state.get("audience") != audience:
		return _error("not_found", "Import not found or expired.")
	finished = dict(state["result"]) if isinstance(state.get("result"), dict) else {}
	reveal = _gateway_write_allowed(row.get("gateway"))
	examples = {}
	for kind in ("invalid", "skipped"):
		examples[kind] = finished[kind] = audience_import.example_rows(finished.get(kind), reveal)
		examples[f"{kind}_total"] = int(finished.get(f"{kind}_total") or state.get(f"{kind}_total") or 0)
	if finished:
		state = {**state, "result": finished}
	return {"success": True, **state, **examples}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_audience_write"), seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def remove_members(audience: str | None = None, recipients: Any = None) -> dict[str, Any]:
	"""Remove contacts (by phone number) from an audience."""
	row = _require_audience_write(audience)
	if row.get("error"):
		return row
	wanted = _parse_list(recipients, "recipients")
	max_remove = policy.get("audience_max_remove_per_request")
	if len(wanted) > max_remove:
		return _error("too_many", f"Remove at most {max_remove} contacts per request.")
	phones = [p for p in (broadcast_recipients.normalize_recipient(r) for r in wanted) if p]
	before = frappe.db.count(aud.MEMBER, {"audience": audience})
	for i in range(0, len(phones), 1000):
		frappe.db.delete(aud.MEMBER, {"audience": audience, "recipient": ["in", phones[i : i + 1000]]})
	counts = aud.refresh_counts(audience, row["gateway"])
	removed = before - counts["member_count"]
	_audit(audience, "removed members", removed=removed)
	return {"success": True, "removed": removed, **counts}


@frappe.whitelist()
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
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
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
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
	problem = audience_selection.check_selection(gateway, items)
	if problem:
		return _error("invalid", problem)
	return audience_selection.preview_payload(gateway, items, aud.template_category(broadcast))


@frappe.whitelist()
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def preview_audience_selection_for_gateway(
	gateway: str | None = None, selection: Any = None, template_category: str | None = None
) -> dict[str, Any]:
	"""Same counts as :func:`preview_audience_selection` but without a Broadcast document (wizard step).

	``template_category`` (MARKETING / UTILITY / AUTHENTICATION) applies the purpose rule and the marketing
	suppression; leave it out to count without the purpose rule. Needs read access to the Gateway.
	"""
	denied = _require_gateway(gateway, write=False)
	if denied:
		return denied
	items = _parse_selection(selection)
	problem = audience_selection.check_selection(gateway, items)
	if problem:
		return _error("invalid", problem)
	category = str(template_category or "").strip().upper() or None
	return audience_selection.preview_payload(gateway, items, category)


def _parse_selection(selection: Any) -> list[dict]:
	return audience_selection.parse_selection(selection)
