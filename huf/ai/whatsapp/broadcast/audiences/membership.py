# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp audiences: membership rules, tag filters, suppression lookup and selection expansion.

An audience is a consented list. Opt-out is NOT stored here: ``gateway_consent`` (the Gateway Access
Entry ``opted_out`` state for STOP and the Gateway Consent marketing preference) stays the only source and
is read, never written, when a list is counted or expanded.

:func:`expand_selection` is a pure function (include lists minus exclude lists, deduped by recipient, the
first list wins for params and consent). Everything that touches the database is in the other functions.

Limits are read through ``policy.get(...)`` (group ``audiences`` in the limits registry).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

import frappe
from frappe.utils import cint

from huf.ai.gateway_core.constants import ENTRY_STATE_OPTED_OUT
from huf.ai.whatsapp.broadcast import policy

AUDIENCE = "WhatsApp Audience"
MEMBER = "WhatsApp Audience Member"
BROADCAST = "WhatsApp Broadcast"
BROADCAST_AUDIENCE = "WhatsApp Broadcast Audience"


PURPOSES = ("marketing", "utility", "events")
_PURPOSE_FIELD = {"marketing": "purpose_marketing", "utility": "purpose_utility", "events": "purpose_events"}
# Template category -> the consent purpose that must be on the audience.
_CATEGORY_PURPOSE = {"MARKETING": "marketing", "UTILITY": "utility", "AUTHENTICATION": "utility"}
ACTIVE_BROADCAST_STATUSES = ("Draft", "Queued", "Running", "Paused")
_TAG_SPLIT = re.compile(r"[,;|]")


# --- tags and purposes -----------------------------------------------------------------------------
def normalize_tags(value: Any) -> list[str]:
	"""Tags as a deduped, lower-cased list. Accepts a list, a JSON list string or a ``a,b;c`` string.

	Raises ValueError when a tag is too long or there are too many.
	"""
	if value in (None, ""):
		return []
	if isinstance(value, str):
		text = value.strip()
		if text.startswith("["):
			try:
				value = json.loads(text)
			except ValueError:
				value = _TAG_SPLIT.split(text)
		else:
			value = _TAG_SPLIT.split(text)
	if not isinstance(value, (list, tuple, set)):
		raise ValueError("tags must be a list")
	max_len = policy.get("audience_max_tag_length")
	out: list[str] = []
	for item in value:
		tag = re.sub(r"\s+", " ", str(item or "")).strip().lower()
		if not tag or tag in out:
			continue
		if len(tag) > max_len:
			raise ValueError(f"tag too long (max {max_len} characters)")
		out.append(tag)
	max_tags = policy.get("audience_max_tags_per_member")
	if len(out) > max_tags:
		raise ValueError(f"too many tags (max {max_tags})")
	return out


def purposes_of(audience: dict | Any) -> set[str]:
	get = audience.get if hasattr(audience, "get") else (lambda k: getattr(audience, k, None))
	return {p for p, field in _PURPOSE_FIELD.items() if cint(get(field))}


def purpose_for_category(category: str | None) -> str | None:
	"""The consent purpose a template of this category needs, or None when the category is unknown/absent."""
	return _CATEGORY_PURPOSE.get(str(category or "").strip().upper())


def tags_match(member_tags: Iterable[str], wanted: Iterable[str], mode: str = "any") -> bool:
	wanted = {t for t in (str(w).strip().lower() for w in wanted or []) if t}
	if not wanted:
		return True
	have = {str(t).strip().lower() for t in member_tags or []}
	return wanted <= have if mode == "all" else bool(wanted & have)


def _as_dict(value: Any) -> dict | None:
	if isinstance(value, dict):
		return value
	if isinstance(value, str) and value.strip():
		try:
			parsed = json.loads(value)
		except ValueError:
			return None
		return parsed if isinstance(parsed, dict) else None
	return None


def _as_list(value: Any) -> list:
	if isinstance(value, list):
		return value
	if isinstance(value, str) and value.strip():
		try:
			parsed = json.loads(value)
		except ValueError:
			return []
		return parsed if isinstance(parsed, list) else []
	return []


# --- expansion (pure) ------------------------------------------------------------------------------
def expand_selection(
	selection: list[dict],
	audiences: dict[str, dict],
	members: dict[str, list[dict]],
	suppressed: dict[str, str] | None = None,
	category: str | None = None,
) -> dict[str, Any]:
	"""Include lists minus exclude lists, deduped by recipient. Pure: no database access.

	``selection``: ``[{"audience", "tag_filter_mode": "any"|"all", "tags": [...], "exclude": bool}]``.
	``audiences``: name -> audience row (purpose checkboxes, consent_source, default_consent_at ...).
	``members``: audience name -> member rows (recipient, display_name, params, tags, consent_*).
	``suppressed``: recipient -> reason (from :func:`suppression_map`); those rows stay in ``rows`` flagged.
	``category``: template category; a MARKETING template blocks audiences without the marketing purpose.

	Returns ``{"rows", "counts", "blocked_audiences", "per_audience"}``. Each row is
	``{recipient, display_name, params, consent_source, consent_at, audience, suppressed}`` (``suppressed``
	is the reason or None). Counts: ``total`` (matched in include lists) = ``excluded`` + ``dupes`` +
	``blocked_by_purpose`` + ``len(rows)``; ``suppressed`` is part of ``len(rows)``; ``final`` = rows that
	can be sent. The first include list that holds a recipient wins its params and consent.
	"""
	suppressed = suppressed or {}
	needed = purpose_for_category(category)
	counts = {"total": 0, "dupes": 0, "excluded": 0, "suppressed": 0, "blocked_by_purpose": 0, "final": 0}

	def pick(item: dict) -> list[dict]:
		name = item.get("audience")
		if name not in audiences:
			raise ValueError(f"Unknown audience: {name}")
		wanted = normalize_tags(item.get("tags"))
		mode = "all" if item.get("tag_filter_mode") == "all" else "any"
		return [m for m in members.get(name, []) if tags_match(_as_list(m.get("tags")), wanted, mode)]

	excluded: set[str] = set()
	for item in selection or []:
		if _truthy(item.get("exclude")):
			excluded.update(m["recipient"] for m in pick(item))

	rows: list[dict] = []
	seen: set[str] = set()
	blocked: list[str] = []
	per_audience: list[dict] = []
	for item in selection or []:
		if _truthy(item.get("exclude")):
			continue
		name = item["audience"]
		matched = pick(item)
		aud = audiences[name]
		counts["total"] += len(matched)
		stat = {"audience": name, "matched": len(matched), "added": 0}
		if needed and needed not in purposes_of(aud):
			counts["blocked_by_purpose"] += len(matched)
			blocked.append(name)
			stat["blocked_by_purpose"] = True
			per_audience.append(stat)
			continue
		for m in matched:
			recipient = m["recipient"]
			if recipient in excluded:
				counts["excluded"] += 1
				continue
			if recipient in seen:
				counts["dupes"] += 1
				continue
			seen.add(recipient)
			reason = suppressed.get(recipient)
			if reason:
				counts["suppressed"] += 1
			rows.append(
				{
					"recipient": recipient,
					"display_name": m.get("display_name"),
					"params": _as_dict(m.get("params")),
					"consent_source": m.get("consent_source") or aud.get("consent_source"),
					"consent_at": m.get("consent_at")
					or aud.get("default_consent_at")
					or aud.get("consent_attested_at"),
					"audience": name,
					"suppressed": reason or None,
				}
			)
			stat["added"] += 1
		per_audience.append(stat)
	counts["final"] = len(rows) - counts["suppressed"]
	return {"rows": rows, "counts": counts, "blocked_audiences": blocked, "per_audience": per_audience}


def _truthy(value: Any) -> bool:
	return str(value).strip().lower() in ("1", "true", "yes") if isinstance(value, str) else bool(value)


# --- database helpers ------------------------------------------------------------------------------
def load_inputs(selection: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
	"""Audience rows and member rows for the audiences named in ``selection``."""
	names = sorted({s.get("audience") for s in selection or [] if s.get("audience")})
	audiences: dict[str, dict] = {}
	members: dict[str, list[dict]] = {}
	for name in names:
		row = frappe.db.get_value(AUDIENCE, name, "*", as_dict=True)
		if not row:
			raise ValueError(f"Unknown audience: {name}")
		audiences[name] = row
		members[name] = frappe.get_all(
			MEMBER,
			filters={"audience": name},
			fields=["recipient", "display_name", "params", "tags", "consent_source", "consent_at"],
			order_by="recipient asc",
			limit_page_length=0,
		)
	return audiences, members


def suppression_map(gateway: str, recipients: Iterable[str], marketing: bool = True) -> dict[str, str]:
	"""recipient -> reason for recipients that must not be messaged. READ ONLY against consent records.

	``opted_out``: the contact sent STOP on this gateway (Gateway Access Entry state). ``marketing_opted_out``:
	the contact's latest marketing preference is stop (Gateway Consent). Phone digits only; the phone<->BSUID
	alias lookup of ``gateway_service.is_opted_out`` is applied again by ``recipients.prepare`` at send time.
	"""
	items = [r for r in dict.fromkeys(recipients or []) if r]
	if not items:
		return {}
	out: dict[str, str] = {}
	opted_state = ENTRY_STATE_OPTED_OUT
	step = policy.get("audience_suppression_chunk")
	for i in range(0, len(items), step):
		chunk = items[i : i + step]
		for row in frappe.get_all(
			"Gateway Access Entry",
			filters={"gateway": gateway, "entry_type": "Sender", "external_id": ["in", chunk], "state": opted_state},
			fields=["external_id"],
			limit_page_length=0,
		):
			out[row["external_id"]] = "opted_out"
		if marketing:
			seen: set[str] = set()
			for row in frappe.get_all(
				"Gateway Consent",
				filters={"gateway": gateway, "sender_id": ["in", chunk], "category": "marketing_messages"},
				fields=["sender_id", "value"],
				order_by="meta_timestamp desc, creation desc, name desc",
				limit_page_length=0,
			):
				if row["sender_id"] in seen:
					continue
				seen.add(row["sender_id"])
				if row["value"] == "stop":
					out.setdefault(row["sender_id"], "marketing_opted_out")
	return out


def template_category(broadcast: str) -> str | None:
	template = frappe.db.get_value(BROADCAST, broadcast, "template")
	if not template or not frappe.db.exists("WhatsApp Templates", template):
		return None
	return frappe.db.get_value("WhatsApp Templates", template, "category")


def referencing_broadcasts(audience: str) -> list[dict]:
	"""Draft/Queued/Running/Paused broadcasts that pick this audience."""
	parents = frappe.get_all(
		BROADCAST_AUDIENCE,
		filters={"audience": audience, "parenttype": BROADCAST},
		pluck="parent",
		limit_page_length=0,
		parent_doctype=BROADCAST,
		ignore_permissions=True,
	)
	if not parents:
		return []
	return frappe.get_all(
		BROADCAST,
		filters={"name": ["in", list(set(parents))], "status": ["in", list(ACTIVE_BROADCAST_STATUSES)]},
		fields=["name", "status"],
		limit_page_length=0,
		ignore_permissions=True,
	)


def attested_covered_broadcasts(audience: str) -> list[str]:
	"""Broadcasts (any status) whose consent was covered by this audience's attestation."""
	rows = frappe.db.sql(
		"select distinct b.name from `tabWhatsApp Broadcast` b "
		"join `tabWhatsApp Broadcast Recipient` r on r.broadcast = b.name "
		"where r.audience = %s and b.consent_attested = 1 and b.consent_source like %s order by b.name",
		(audience, "Audiences:%"),
	)
	return [r[0] for r in rows]


def assert_not_in_use(audience: str, verb: str) -> None:
	used = referencing_broadcasts(audience)
	if used:
		names = ", ".join(f"{u['name']} ({u['status']})" for u in used[:5])
		frappe.throw(f"This audience cannot be {verb} while a broadcast that has not finished uses it: {names}.")


def refresh_counts(audience: str, gateway: str | None = None) -> dict[str, int]:
	"""Recompute member_count and suppressed_count on the audience."""
	gateway = gateway or frappe.db.get_value(AUDIENCE, audience, "gateway")
	members = frappe.get_all(MEMBER, filters={"audience": audience}, pluck="recipient", limit_page_length=0)
	suppressed = suppression_map(gateway, members)
	counts = {"member_count": len(members), "suppressed_count": len(suppressed)}
	frappe.db.set_value(AUDIENCE, audience, counts, update_modified=False)
	return counts


# --- masking ---------------------------------------------------------------------------------------
def mask_phone(value: Any) -> Any:
	text = str(value or "")
	return ("*" * max(len(text) - 4, 0) + text[-4:]) if text else value
