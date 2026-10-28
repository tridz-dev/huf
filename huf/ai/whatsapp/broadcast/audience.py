# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp audiences: membership rules, tag filters, suppression lookup and selection expansion.

An audience is a consented list. Opt-out is NOT stored here: ``gateway_consent`` (the Gateway Access
Entry ``opted_out`` state for STOP and the Gateway Consent marketing preference) stays the only source and
is read, never written, when a list is counted or expanded.

:func:`expand_selection` is a pure function (include lists minus exclude lists, deduped by recipient, the
first list wins for params and consent). Everything that touches the database is in the other functions.

Limits in this module are module constants (``LIMIT_*``). WP-A's ``policy.py`` is not available in this
branch yet; the coordinator rewires them to ``policy.get(...)``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from typing import Any

import frappe
from frappe.utils import cint, get_datetime, now_datetime

from huf.ai.gateway_core.constants import ENTRY_STATE_OPTED_OUT
from huf.ai.whatsapp.broadcast import params as broadcast_params
from huf.ai.whatsapp.broadcast import recipients as broadcast_recipients

AUDIENCE = "WhatsApp Audience"
MEMBER = "WhatsApp Audience Member"
BROADCAST = "WhatsApp Broadcast"
BROADCAST_AUDIENCE = "WhatsApp Broadcast Audience"

# --- limits (to be rewired to policy.get by the coordinator) ---------------------------------------
LIMIT_MAX_MEMBERS_PER_AUDIENCE = 200000
LIMIT_INLINE_IMPORT_ROWS = 10000  # imports above this run as a background job
LIMIT_MAX_IMPORT_ROWS = 200000
LIMIT_MAX_CSV_BYTES = 20 * 1024 * 1024
LIMIT_MAX_TAGS_PER_MEMBER = 20
LIMIT_MAX_TAG_LENGTH = 50
LIMIT_MAX_NAME_LENGTH = 140
LIMIT_MAX_REMOVE_PER_REQUEST = 10000
LIMIT_PAGE_SIZE_MAX = 200
RETURNED_LIST_LIMIT = 200
IMPORT_CHUNK = 1000
SUPPRESSION_CHUNK = 500
IMPORT_JOB_TTL = 86400

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
	out: list[str] = []
	for item in value:
		tag = re.sub(r"\s+", " ", str(item or "")).strip().lower()
		if not tag or tag in out:
			continue
		if len(tag) > LIMIT_MAX_TAG_LENGTH:
			raise ValueError(f"tag too long (max {LIMIT_MAX_TAG_LENGTH} characters)")
		out.append(tag)
	if len(out) > LIMIT_MAX_TAGS_PER_MEMBER:
		raise ValueError(f"too many tags (max {LIMIT_MAX_TAGS_PER_MEMBER})")
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
	for i in range(0, len(items), SUPPRESSION_CHUNK):
		chunk = items[i : i + SUPPRESSION_CHUNK]
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


# --- member import ---------------------------------------------------------------------------------
def clean_member(raw: dict) -> tuple[dict | None, str | None]:
	"""Validate one mapped row (``recipient``, ``display_name``, ``tags``, ``params``, ``consent_*``).

	Returns ``(clean, None)`` or ``(None, reason)``. BSUIDs are refused: broadcasts need a phone number.
	"""
	phone = broadcast_recipients.normalize_recipient(raw.get("recipient"))
	if phone is None:
		return None, "invalid_number"
	if not phone.isdigit():
		return None, "bsuid_not_supported"
	name = str(raw.get("display_name") or "").strip()
	if len(name) > LIMIT_MAX_NAME_LENGTH:
		return None, f"name_too_long (max {LIMIT_MAX_NAME_LENGTH})"
	try:
		tags = normalize_tags(raw.get("tags"))
	except ValueError as exc:
		return None, f"invalid_tags: {exc}"
	params = raw.get("params")
	if params not in (None, "", {}, []):
		problem = broadcast_params.params_error(_as_dict(params) if isinstance(params, str) else params)
		if problem:
			return None, f"invalid_params: {problem}"
	consent_at = raw.get("consent_at")
	if consent_at not in (None, ""):
		try:
			when = get_datetime(consent_at)
		except Exception:
			return None, "invalid_consent_date"
		if when > get_datetime(now_datetime()):
			return None, "consent_date_in_future"
		consent_at = when
	else:
		consent_at = None
	return (
		{
			"recipient": phone,
			"display_name": name or None,
			"tags": tags,
			"params": _as_dict(params) if isinstance(params, str) else (params or None),
			"consent_source": str(raw.get("consent_source") or "").strip()[:255] or None,
			"consent_at": consent_at,
		},
		None,
	)


def import_rows(
	audience: str,
	rows: list[dict],
	on_conflict: str = "skip",
	source: str = "import",
	progress: Callable[[dict], None] | None = None,
	commit_chunks: bool = False,
) -> dict[str, Any]:
	"""Validate and store mapped rows. ``on_conflict``: ``skip`` | ``update`` (tags are merged).

	Duplicates inside ``rows`` count as ``duplicate_in_file``. Returns exact totals plus capped example lists.
	"""
	frappe.flags.in_audience_api = True
	existing = {
		r["recipient"]: r
		for r in frappe.get_all(
			MEMBER, filters={"audience": audience}, fields=["name", "recipient", "tags"], limit_page_length=0
		)
	}
	result: dict[str, Any] = {"added": 0, "updated": 0, "skipped": [], "invalid": [], "skipped_total": 0, "invalid_total": 0}
	seen: set[str] = set()
	stamp = now_datetime()
	user = frappe.session.user
	pending: list[list[Any]] = []
	fields = [
		"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "audience", "recipient",
		"display_name", "params", "tags", "consent_source", "consent_at", "source", "added_at",
	]  # fmt: skip

	def flush():
		if pending:
			frappe.db.bulk_insert(MEMBER, fields, pending, ignore_duplicates=True)
			pending.clear()
		if commit_chunks:
			frappe.db.commit()

	def note(kind: str, entry: dict):
		result[f"{kind}_total"] += 1
		if len(result[kind]) < RETURNED_LIST_LIMIT:
			result[kind].append(entry)

	for index, raw in enumerate(rows, start=1):
		clean, reason = clean_member(raw)
		if clean is None:
			note("invalid", {"row": index, "recipient": raw.get("recipient"), "reason": reason})
		else:
			phone = clean["recipient"]
			if phone in seen:
				note("skipped", {"row": index, "recipient": phone, "reason": "duplicate_in_file"})
			elif phone in existing and on_conflict != "update":
				note("skipped", {"row": index, "recipient": phone, "reason": "already_in_audience"})
			elif phone in existing:
				seen.add(phone)
				_update_member(existing[phone], clean)
				result["updated"] += 1
			elif len(existing) + result["added"] >= LIMIT_MAX_MEMBERS_PER_AUDIENCE:
				note("skipped", {"row": index, "recipient": phone, "reason": "audience_full"})
			else:
				seen.add(phone)
				pending.append(
					[
						f"{audience}-{phone}"[:140], user, stamp, stamp, user, 0, 0, audience, phone,
						clean["display_name"], json.dumps(clean["params"]) if clean["params"] else None,
						json.dumps(clean["tags"]), clean["consent_source"], clean["consent_at"], source, stamp,
					]
				)  # fmt: skip
				result["added"] += 1
		if len(pending) >= IMPORT_CHUNK:
			flush()
		if progress and index % IMPORT_CHUNK == 0:
			progress({"processed": index, "total": len(rows), **_brief(result)})
	flush()
	if progress:
		progress({"processed": len(rows), "total": len(rows), **_brief(result)})
	return result


def _brief(result: dict) -> dict:
	return {k: result[k] for k in ("added", "updated", "skipped_total", "invalid_total")}


def _update_member(existing: dict, clean: dict) -> None:
	values: dict[str, Any] = {}
	if clean["display_name"]:
		values["display_name"] = clean["display_name"]
	if clean["params"]:
		values["params"] = json.dumps(clean["params"])
	if clean["consent_source"]:
		values["consent_source"] = clean["consent_source"]
	if clean["consent_at"]:
		values["consent_at"] = clean["consent_at"]
	if clean["tags"]:
		merged = list(dict.fromkeys(_as_list(existing.get("tags")) + clean["tags"]))
		values["tags"] = json.dumps(merged[:LIMIT_MAX_TAGS_PER_MEMBER])
	if values:
		frappe.db.set_value(MEMBER, existing["name"], values)


# --- import job + progress -------------------------------------------------------------------------
def _job_key(job_id: str) -> str:
	return f"wa_audience_import:{frappe.local.site}:{job_id}"


def set_job_state(job_id: str, state: dict) -> None:
	try:
		frappe.cache().set(_job_key(job_id), json.dumps(state, default=str), ex=IMPORT_JOB_TTL)
	except Exception:
		pass


def get_job_state(job_id: str) -> dict | None:
	try:
		raw = frappe.cache().get(_job_key(job_id))
	except Exception:
		return None
	if not raw:
		return None
	try:
		return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
	except ValueError:
		return None


def run_import_job(audience: str, rows: list[dict], on_conflict: str, job_id: str, user: str) -> None:
	"""Background import of a large list. Reports progress through the job state and a realtime event.

	``progress.py`` publishes per-broadcast counters only, so the throttle (``progress.THROTTLE_SECONDS``) is
	reused here with an audience-specific event instead.
	"""
	import time

	from huf.ai.whatsapp.broadcast import progress as broadcast_progress

	frappe.set_user(user)
	last = {"t": 0.0}
	state = {"job_id": job_id, "audience": audience, "status": "running", "processed": 0, "total": len(rows)}
	set_job_state(job_id, state)

	def report(info: dict, force: bool = False):
		now = time.time()
		if not force and now - last["t"] < broadcast_progress.THROTTLE_SECONDS:
			return
		last["t"] = now
		state.update(info)
		set_job_state(job_id, state)
		try:
			frappe.publish_realtime("wa_audience_import_progress", dict(state), user=user)
		except Exception:
			pass

	try:
		result = import_rows(audience, rows, on_conflict, progress=report, commit_chunks=True)
		counts = refresh_counts(audience)
		frappe.db.commit()
		report({"status": "done", "result": result, **counts}, force=True)
	except Exception as exc:
		frappe.db.rollback()
		frappe.log_error(title="WhatsApp audience import failed")
		report({"status": "failed", "error": str(exc)[:300]}, force=True)


# --- masking ---------------------------------------------------------------------------------------
def mask_phone(value: Any) -> Any:
	text = str(value or "")
	return ("*" * max(len(text) - 4, 0) + text[-4:]) if text else value
