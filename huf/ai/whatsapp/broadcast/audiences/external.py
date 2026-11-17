# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Externally managed audiences: another app (a CRM, a loyalty app) keeps an audience's members up to date.

``upsert_audience_members`` is the one write path. The audience is flagged ``externally_managed`` with a
``managed_by`` source label; only that same ``source`` may change it, and the UI / CSV / manual endpoints refuse it
(``membership.assert_not_external``). Each member keeps its own consent source and date; the broadcast's consent
attestation is unchanged. Before a broadcast that uses such an audience starts, :func:`run_refresh_hooks` calls the
``huf_audience_refresh`` hooks so the members are current, and refuses to start when a refresh fails.

Register a refresh in the managing app's ``hooks.py``::

    huf_audience_refresh = ["my_app.huf_hooks.refresh_audience"]

The function receives ``audience=<name>, managed_by=<source>`` and returns nothing; it calls
``upsert_audience_members`` itself. A hook that does not manage that audience simply returns.
"""

from __future__ import annotations

import contextlib
import signal
import threading
from typing import Any

import frappe
from frappe.rate_limiter import rate_limit

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.audiences import api as audience_api
from huf.ai.whatsapp.broadcast.audiences import importer as audience_import
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast.audiences.common import _audit, _guard, _parse_list
from huf.ai.whatsapp.management import _bridge_guard, _error

HOOK = "huf_audience_refresh"
_MODES = ("replace", "merge")
_SOURCE_MAX = 60
_KEY_MAX = 140


def _create(spec: Any, source: str) -> dict[str, Any]:
	spec = spec if isinstance(spec, dict) else {}
	made = audience_api.create_audience(
		gateway=spec.get("gateway"), title=spec.get("title"), consent_source=spec.get("consent_source"),
		consent_basis=spec.get("consent_basis"), consent_purposes=spec.get("consent_purposes"),
		consent_attested=spec.get("consent_attested"), description=spec.get("description"),
		default_consent_at=spec.get("default_consent_at"),
	)  # fmt: skip
	if made.get("error"):
		return made
	name = made["audience"]["name"]
	frappe.db.set_value(aud.AUDIENCE, name, {"externally_managed": 1, "managed_by": source}, update_modified=False)
	return {"success": True, "name": name, "created": True}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_audience_import"), seconds=audience_api.RATE_SECONDS)
@_bridge_guard
@_guard
def upsert_audience_members(
	audience: str | None = None,
	members: Any = None,
	mode: str = "replace",
	source: str | None = None,
	idempotency_key: str | None = None,
	create: Any = None,
) -> dict[str, Any]:
	"""Set (``replace``) or add to (``merge``) the members of an externally managed audience.

	``members``: list of ``{recipient, display_name, params, tags, consent_source, consent_at}``. ``source`` labels
	the managing app; the audience may be changed only with the same ``source``. ``create``: for a new audience,
	``{gateway, title, consent_source, consent_basis, consent_purposes, consent_attested, ...}`` (as for
	``create_audience``), used when ``audience`` is empty. A repeated ``idempotency_key`` for the audience is a no-op.
	Needs write on the audience's Gateway. The whole refresh is refused when it exceeds
	``audience_external_max_members``; ``replace`` with no valid contact is refused so a bad feed cannot empty a list.
	"""
	source = str(source or "").strip()
	if not source or len(source) > _SOURCE_MAX:
		return _error("source_required", f"Say which app manages this audience (up to {_SOURCE_MAX} characters).")
	if mode not in _MODES:
		return _error("invalid", f"mode must be one of {', '.join(_MODES)}.")
	key = str(idempotency_key or "").strip() or None
	if key and len(key) > _KEY_MAX:
		return _error("invalid", f"idempotency_key can be at most {_KEY_MAX} characters.")
	rows = _parse_list(members, "members")
	cap = policy.get("audience_external_max_members")
	if len(rows) > cap:
		return _error("too_many", f"Send at most {cap} contacts per refresh.")

	created = False
	if audience:
		row = audience_api._require_audience_write(audience)
		if row.get("error"):
			return row
		managed = frappe.db.get_value(aud.AUDIENCE, audience, ["externally_managed", "managed_by"], as_dict=True)
		if not managed.externally_managed:
			return _error("not_externally_managed", "This audience is managed in Huf; it cannot be changed by another app.")
		if managed.managed_by != source:
			return _error("source_mismatch", f"This audience is managed by {managed.managed_by}; only that app can change it.")
		if key and frappe.db.get_value(aud.AUDIENCE, audience, "external_key") == key:
			return {"success": True, "noop": True, "audience": audience}
	else:
		made = _create(create, source)
		if made.get("error"):
			return made
		audience, created = made["name"], True
		row = audience_api._audience_row(audience)

	clean_rows: list[dict] = []
	seen: set[str] = set()
	invalid: list[dict] = []
	for index, raw in enumerate(rows, start=1):
		clean, reason = audience_import.clean_member(raw if isinstance(raw, dict) else {})
		if clean is None:
			invalid.append({"row": index, "reason": reason})
		else:
			if clean["recipient"] not in seen:
				seen.add(clean["recipient"])
			clean_rows.append(raw)
	if mode == "replace" and rows and not seen:
		return {**_error("no_valid_members", "None of the contacts could be used; the audience was left as it was."), "invalid": invalid[:50]}

	removed = 0
	if mode == "replace":
		stale = [
			r for r in frappe.get_all(aud.MEMBER, {"audience": audience}, pluck="recipient", limit_page_length=0) if r not in seen
		]
		chunk = policy.get("audience_delete_chunk")
		for i in range(0, len(stale), chunk):
			frappe.db.delete(aud.MEMBER, {"audience": audience, "recipient": ["in", stale[i : i + chunk]]})
		removed = len(stale)
	result = audience_import.import_rows(audience, clean_rows, "update", source=source, external=True)
	counts = aud.refresh_counts(audience, row["gateway"])
	if key:
		frappe.db.set_value(aud.AUDIENCE, audience, "external_key", key, update_modified=False)
	_audit(audience, "external refresh", source=source, mode=mode, added=result["added"], updated=result["updated"], removed=removed, invalid=len(invalid))
	return {
		"success": True, "noop": False, "audience": audience, "created": created, "added": result["added"],
		"updated": result["updated"], "removed": removed, "invalid_total": len(invalid), "invalid": invalid[:50],
		"skipped_total": result["skipped_total"], **counts,
	}  # fmt: skip


# --- refresh before a broadcast starts -------------------------------------------------------------
class RefreshFailed(frappe.ValidationError):
	pass


@contextlib.contextmanager
def _deadline(seconds: int):
	"""Raise TimeoutError after ``seconds`` (main thread only; elsewhere the hook runs without a deadline)."""
	if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
		yield
		return

	def _fire(_signum, _frame):
		raise TimeoutError(f"no answer within {seconds}s")

	previous = signal.signal(signal.SIGALRM, _fire)
	signal.setitimer(signal.ITIMER_REAL, seconds)
	try:
		yield
	finally:
		signal.setitimer(signal.ITIMER_REAL, 0)
		signal.signal(signal.SIGALRM, previous)


def external_audiences(broadcast: str) -> list[dict]:
	from huf.ai.whatsapp.broadcast.checks import audience_check

	names = audience_check.included_audiences(broadcast)
	if not names:
		return []
	return frappe.get_all(
		aud.AUDIENCE, {"name": ["in", names], "externally_managed": 1}, ["name", "managed_by"], limit_page_length=0
	)


def run_refresh_hooks(broadcast: str) -> bool:
	"""Refresh every externally managed audience the broadcast includes. True when any ran.

	Fail closed: no registered ``huf_audience_refresh`` hook, a hook error or a timeout raises
	``RefreshFailed`` (a ValidationError) naming the audience, so the broadcast does not start on stale contacts.
	"""
	targets = external_audiences(broadcast)
	if not targets:
		return False
	hooks = frappe.get_hooks(HOOK) or []
	timeout = int(policy.get("audience_refresh_timeout_seconds"))
	for target in targets:
		if not hooks:
			raise RefreshFailed(f"Audience {target['name']} is managed by {target['managed_by']}, which has no refresh registered. The broadcast was not started.")
		for path in hooks:
			try:
				with _deadline(timeout):
					frappe.get_attr(path)(audience=target["name"], managed_by=target["managed_by"])
			except Exception as exc:
				frappe.log_error(title="Audience refresh failed", message=f"{path} for {target['name']}: {exc}")
				raise RefreshFailed(f"Audience {target['name']} could not be refreshed by {target['managed_by']} ({exc}). The broadcast was not started.") from exc
	return True
