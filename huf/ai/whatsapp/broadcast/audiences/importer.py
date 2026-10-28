# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp audience member import: row validation, bulk insert, background job and its progress.

Limits come from :mod:`huf.ai.whatsapp.broadcast.audiences.membership` (limits read through ``policy.get``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import frappe
from frappe.utils import get_datetime, now_datetime

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast import params as broadcast_params
from huf.ai.whatsapp.broadcast import recipients as broadcast_recipients

MEMBER = aud.MEMBER

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
	max_name = policy.get("audience_max_name_length")
	if len(name) > max_name:
		return None, f"name_too_long (max {max_name})"
	try:
		tags = aud.normalize_tags(raw.get("tags"))
	except ValueError as exc:
		return None, f"invalid_tags: {exc}"
	params = raw.get("params")
	if params not in (None, "", {}, []):
		problem = broadcast_params.params_error(aud._as_dict(params) if isinstance(params, str) else params)
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
			"params": aud._as_dict(params) if isinstance(params, str) else (params or None),
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
	max_members, chunk = policy.get("audience_max_members"), policy.get("audience_import_chunk")
	list_cap = policy.get("returned_list_limit")
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
		if len(result[kind]) < list_cap:
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
			elif len(existing) + result["added"] >= max_members:
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
		if len(pending) >= chunk:
			flush()
		if progress and index % chunk == 0:
			progress({"processed": index, "total": len(rows), **_brief(result)})
	flush()
	if progress:
		progress({"processed": len(rows), "total": len(rows), **_brief(result)})
	return result


def example_rows(entries: Any, reveal: bool) -> list[dict]:
	"""Capped ``{row, recipient, reason}`` examples; phone digits are masked unless ``reveal``."""
	cap = policy.get("returned_list_limit")
	out = []
	for e in list(entries or [])[:cap]:
		if not isinstance(e, dict):
			continue
		who = e.get("recipient")
		out.append(
			{
				"row": e.get("row"),
				"recipient": who if reveal else aud.mask_phone(who),
				"reason": e.get("reason"),
			}
		)
	return out


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
		merged = list(dict.fromkeys(aud._as_list(existing.get("tags")) + clean["tags"]))
		values["tags"] = json.dumps(merged[:policy.get("audience_max_tags_per_member")])
	if values:
		frappe.db.set_value(MEMBER, existing["name"], values)


# --- import job + progress -------------------------------------------------------------------------
def _job_key(job_id: str) -> str:
	return f"wa_audience_import:{frappe.local.site}:{job_id}"


def set_job_state(job_id: str, state: dict) -> None:
	try:
		frappe.cache().set(_job_key(job_id), json.dumps(state, default=str), ex=policy.get("audience_import_job_ttl"))
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
		counts = aud.refresh_counts(audience)
		frappe.db.commit()
		report({"status": "done", "result": result, **counts}, force=True)
	except Exception as exc:
		frappe.db.rollback()
		frappe.log_error(title="WhatsApp audience import failed")
		report({"status": "failed", "error": str(exc)[:300]}, force=True)
