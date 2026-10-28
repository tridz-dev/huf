# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Wiring audiences into a Draft broadcast: pick lists, snapshot their members as recipient rows.

``set_broadcast_audiences`` stores the picks on the broadcast (``audiences`` table), expands them with
:func:`membership.expand_selection` and writes the rows through ``recipients.prepare`` - the same intake as
a manual add, so STOP, BSUID, US +1 marketing and the caps stay checked in one place. The rows are the frozen
snapshot: later edits to a list do not change the broadcast; pick again to refresh. Re-running replaces only
the rows that came from audiences (``audience`` set); manually added rows are kept.

When ``require_consent_attestation`` is on and every sendable row comes from an audience whose attester is
on record, those audiences satisfy the broadcast's own consent requirement (recorded in ``consent_source``
and the audit trail). Any manual row, or a change to the rows, takes that away again.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any

import frappe
from frappe.rate_limiter import rate_limit

from huf.ai.whatsapp.broadcast import api as broadcast_api, policy, recipients as br
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast.audiences import selection as audience_selection
from huf.ai.whatsapp.broadcast.audiences.common import _guard
from huf.ai.whatsapp.management import _bridge_guard, _error, _gateway_read_allowed

RECIPIENT = "WhatsApp Broadcast Recipient"
RATE_SECONDS = 60


def _template_category(broadcast: str, fallback: str | None) -> str | None:
	return aud.template_category(broadcast) or fallback or None


def _picks(broadcast: str) -> list[dict]:
	rows = frappe.get_all(
		aud.BROADCAST_AUDIENCE,
		filters={"parent": broadcast, "parenttype": aud.BROADCAST},
		fields=["audience", "tag_filter_mode", "tags", "exclude"],
		order_by="idx asc",
		limit_page_length=0,
		parent_doctype=aud.BROADCAST,
		ignore_permissions=True,
	)
	return [
		{
			"audience": r["audience"],
			"tag_filter_mode": r.get("tag_filter_mode") or "any",
			"tags": aud._as_list(r.get("tags")),
			"exclude": bool(r.get("exclude")),
		}
		for r in rows
	]


def _row_audiences(broadcast: str) -> tuple[list[str], int]:
	"""(audiences of the sendable rows, number of sendable rows without an audience)."""
	rows = frappe.db.sql(
		f"select audience, count(*) from `tab{RECIPIENT}` where broadcast=%s and status != 'skipped' "
		"group by audience",
		broadcast,
	)
	named = [str(a) for a, _n in rows if a]
	manual = sum(int(n) for a, n in rows if not a)
	return named, manual


def consent_cover(broadcast: str) -> dict[str, Any]:
	"""Whether the audiences alone cover this broadcast's consent requirement (read only).

	``satisfied``: there are sendable rows, all from audiences with a recorded attester. ``manual_rows``
	counts sendable rows without an audience (they need the broadcast's own attestation).
	"""
	named, manual = _row_audiences(broadcast)
	rows = []
	for name in named:
		v = frappe.db.get_value(
			aud.AUDIENCE, name, ["title", "consent_source", "consent_attested_by", "consent_attested_at"], as_dict=True
		)
		rows.append({"audience": name, **(v or {}), "attested": bool(v and v.get("consent_attested_by"))})
	return {
		"satisfied": bool(rows) and manual == 0 and all(r["attested"] for r in rows),
		"manual_rows": manual,
		"audiences": [
			{"audience": r["audience"], "title": r.get("title"), "consent_source": r.get("consent_source"),
			 "attested": r["attested"]}
			for r in rows
		],
	}  # fmt: skip


def _prepare_with_retry(broadcast: str, rows: list[dict]) -> dict | None:
	tries = policy.get("prepare_retries")
	for attempt in range(tries):
		try:
			return br.prepare(broadcast, rows)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt < tries - 1:
				time.sleep(random.uniform(0.05, 0.25))
	return None


def _store_picks(broadcast: str, items: list[dict]) -> None:
	doc = frappe.get_doc(aud.BROADCAST, broadcast)
	doc.set("audiences", [])
	for item in items:
		doc.append(
			"audiences",
			{
				"audience": item["audience"],
				"tag_filter_mode": "all" if item.get("tag_filter_mode") == "all" else "any",
				"tags": json.dumps(aud.normalize_tags(item.get("tags"))),
				"exclude": 1 if aud._truthy(item.get("exclude")) else 0,
			},
		)
	doc.save(ignore_permissions=True)


def _clean_items(items: list[dict]) -> list[dict]:
	return [
		{
			"audience": str(i["audience"]),
			"tag_filter_mode": "all" if i.get("tag_filter_mode") == "all" else "any",
			"tags": aud.normalize_tags(i.get("tags")),
			"exclude": aud._truthy(i.get("exclude")),
		}
		for i in items
	]


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_audience_write"), seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def set_broadcast_audiences(broadcast: str | None = None, selection: Any = None) -> dict[str, Any]:
	"""Pick the audiences of a Draft broadcast and snapshot their members as recipient rows.

	``selection``: ``[{"audience", "tag_filter_mode": "any"|"all", "tags": [], "exclude": false}]``; at least
	one include. Every audience must belong to the broadcast's gateway. Replaces earlier audience rows (manual
	rows stay). Audiences without the template category's purpose are listed in ``blocked`` and add no rows;
	the preview also blocks the start (``audience_purpose_mismatch``).
	"""
	row = broadcast_api._require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") != "Draft":
		return _error("not_draft", "Audiences can only be changed while the broadcast is a Draft.")
	items = _clean_items(audience_selection.parse_selection(selection))
	problem = audience_selection.check_selection(row["gateway"], items)
	if problem:
		return _error("invalid", problem)
	category = _template_category(broadcast, row.get("category"))
	result, audiences, blocked = audience_selection.expand(row["gateway"], items, category)

	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True
	try:
		_store_picks(broadcast, items)
		replaced = int(frappe.db.count(RECIPIENT, {"broadcast": broadcast, "audience": ["is", "set"]}) or 0)
		frappe.db.delete(RECIPIENT, {"broadcast": broadcast, "audience": ["is", "set"]})
		rows = [
			{k: r.get(k) for k in ("recipient", "params", "consent_source", "consent_at", "audience")}
			for r in result["rows"]
		]
		prepared = _prepare_with_retry(broadcast, rows)
	finally:
		frappe.flags.in_broadcast_api = prev
	if prepared is None:
		return _error("busy_retry", "Another request is updating this broadcast; retry in a moment.")

	if row.get("consent_attested"):
		broadcast_api._reset_attestation(broadcast, "audiences changed")
	cover = consent_cover(broadcast)
	if policy.get("require_consent_attestation") and cover["satisfied"]:
		_attest_from_audiences(broadcast, cover)
	cover["attested"] = bool(frappe.db.get_value(aud.BROADCAST, broadcast, "consent_attested"))

	broadcast_api._broadcast_audit(
		broadcast,
		"audiences_set",
		audiences=",".join(i["audience"] for i in items if not i["exclude"]),
		excluded=",".join(i["audience"] for i in items if i["exclude"]),
		replaced=replaced,
		added=prepared.get("added"),
		skipped=prepared.get("skipped_total"),
		invalid=prepared.get("invalid_total"),
		blocked=",".join(b["audience"] for b in blocked),
		consent_via_audiences=cover["satisfied"] and cover["attested"],
	)
	return {
		"success": True,
		"broadcast": broadcast,
		"selection": items,
		"category": category,
		"counts": result["counts"],
		"per_audience": result["per_audience"],
		"blocked": blocked,
		"replaced": replaced,
		"added": prepared.get("added"),
		"skipped": prepared.get("skipped"),
		"skipped_total": prepared.get("skipped_total"),
		"invalid": prepared.get("invalid"),
		"invalid_total": prepared.get("invalid_total"),
		"queued": broadcast_api._queued_count(broadcast),
		"consent": cover,
	}


def _attest_from_audiences(broadcast: str, cover: dict[str, Any]) -> None:
	"""Record that the audiences' own attestations cover this broadcast (who/when are the caller/now)."""
	titles = ", ".join(str(a.get("title") or a["audience"]) for a in cover["audiences"])
	frappe.db.set_value(
		aud.BROADCAST,
		broadcast,
		{
			"consent_attested": 1,
			"consent_attested_by": frappe.session.user,
			"consent_attested_at": frappe.utils.now_datetime(),
			"consent_source": f"Audiences: {titles}"[:200],
		},
	)


@frappe.whitelist()
@rate_limit(limit=policy.rate("rate_audience_read"), seconds=RATE_SECONDS)
@_bridge_guard
@_guard
def get_broadcast_audiences(broadcast: str | None = None) -> dict[str, Any]:
	"""The audience picks stored on a broadcast, and whether they cover its consent requirement."""
	if not broadcast or not frappe.db.exists(aud.BROADCAST, broadcast):
		return _error("not_found", "Broadcast not found.")
	gateway = frappe.db.get_value(aud.BROADCAST, broadcast, "gateway")
	if not _gateway_read_allowed(gateway):
		raise frappe.PermissionError("Not permitted to read broadcasts on this Gateway")
	picks = _picks(broadcast)
	for p in picks:
		p["title"] = frappe.db.get_value(aud.AUDIENCE, p["audience"], "title")
	return {"success": True, "broadcast": broadcast, "selection": picks, "consent": consent_cover(broadcast)}
