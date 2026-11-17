# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Externally managed audiences: another app (a CRM) keeps an audience's members up to date.

``upsert_audience_members`` is the one write path. The audience is flagged ``externally_managed`` with a
``managed_by`` source label (display only) and the creating user in ``managed_by_user``; only that user (or a
System Manager), with the same ``source``, may change it, and the UI / CSV / manual endpoints refuse it
(``membership.assert_not_external``). Each member keeps its own consent source and date; the broadcast's consent
attestation is unchanged. Before a broadcast that uses such an audience starts, :func:`run_refresh_hooks` calls the
``huf_audience_refresh`` hooks so the members are current, and refuses to start when a refresh fails.

Register a refresh in the managing app's ``hooks.py``::

    huf_audience_refresh = ["my_app.huf_hooks.refresh_audience"]

The function receives ``audience=<name>, managed_by=<source>`` and returns nothing; it calls
``upsert_audience_members`` itself. A hook that does not manage that audience simply returns. Each hook runs in its
own background job (own site and database connection; nothing is shared with the starting request) and the start
waits up to ``audience_refresh_timeout_seconds`` for its result. On an error or timeout the start is refused; a
hook that was already running keeps going on its own, so a hook MUST be idempotent and safe to repeat.
"""

from __future__ import annotations

import json
import time
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
_KEYS_KEPT = 20
_SAVEPOINT = "huf_external_upsert"


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
	frappe.db.set_value(aud.AUDIENCE, name, {"externally_managed": 1, "managed_by": source, "managed_by_user": frappe.session.user}, update_modified=False)
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

	# Validate and stage everything first; nothing is written until the whole refresh is known to be usable.
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
	if mode == "replace" and not rows:
		return _error("empty_replace", "replace needs at least one contact; the audience was left as it was.")
	if mode == "replace" and not seen:
		return {**_error("no_valid_members", "None of the contacts could be used; the audience was left as it was."), "invalid": invalid[:50]}

	if audience:
		row = audience_api._require_audience_write(audience)
		if row.get("error"):
			return row
		managed = frappe.db.get_value(aud.AUDIENCE, audience, ["externally_managed", "managed_by", "managed_by_user"], as_dict=True)
		if not managed.externally_managed:
			return _error("not_externally_managed", "This audience is managed in Huf; it cannot be changed by another app.")
		if managed.managed_by_user != frappe.session.user and "System Manager" not in frappe.get_roles():
			return _error("owner_mismatch", "This audience was created by another user; only that user can change it.")
		if managed.managed_by != source:
			return _error("source_mismatch", f"This audience is managed by {managed.managed_by}; only that app can change it.")

	# One transaction: any failure rolls back to here, so the audience is never left half-applied or emptied.
	frappe.db.savepoint(_SAVEPOINT)
	try:
		created = False
		if audience:
			if key and not _claim_key(audience, key):
				return {"success": True, "noop": True, "audience": audience}
		else:
			made = _create(create, source)
			if made.get("error"):
				frappe.db.rollback(save_point=_SAVEPOINT)
				return made
			audience, created = made["name"], True
			row = audience_api._audience_row(audience)
			if key:
				_claim_key(audience, key)
		stale: list[str] = []
		if mode == "replace":
			stale = [r for r in frappe.get_all(aud.MEMBER, {"audience": audience}, pluck="recipient", limit_page_length=0) if r not in seen]
		# insert/update the new set first, delete the stale members only once that succeeded
		result = audience_import.import_rows(audience, clean_rows, "update", source=source, external=True, stale=set(stale))
		chunk = policy.get("audience_delete_chunk")
		for i in range(0, len(stale), chunk):
			frappe.db.delete(aud.MEMBER, {"audience": audience, "recipient": ["in", stale[i : i + chunk]]})
		removed = len(stale)
		counts = aud.refresh_counts(audience, row["gateway"])
	except Exception:
		frappe.db.rollback(save_point=_SAVEPOINT)
		raise
	_audit(audience, "external refresh", source=source, mode=mode, added=result["added"], updated=result["updated"], removed=removed, invalid=len(invalid))
	return {
		"success": True, "noop": False, "audience": audience, "created": created, "added": result["added"],
		"updated": result["updated"], "removed": removed, "invalid_total": len(invalid), "invalid": invalid[:50],
		"skipped_total": result["skipped_total"], **counts,
	}  # fmt: skip


def _claim_key(audience: str, key: str) -> bool:
	"""Claim ``key`` for this refresh before any work. False when it is among the audience's recent keys.

	Takes the audience row lock first, so concurrent calls for the audience run one at a time and the second sees
	the first's claim; the claim is written in the refresh's own transaction (a failed refresh releases it).
	Keeping the last ``_KEYS_KEPT`` keys also catches an A, B, A replay."""
	raw = frappe.db.get_value(aud.AUDIENCE, audience, "external_key", for_update=True)
	try:
		keys = json.loads(raw) if raw else []
	except ValueError:
		keys = [raw] if raw else []
	keys = [k for k in keys if isinstance(k, str)] if isinstance(keys, list) else []
	if key in keys:
		return False
	keys = (keys + [key])[-_KEYS_KEPT:]
	frappe.db.set_value(aud.AUDIENCE, audience, "external_key", json.dumps(keys), update_modified=False)
	return True


# --- refresh before a broadcast starts -------------------------------------------------------------
class RefreshFailed(frappe.ValidationError):
	pass


_SLACK = 15  # seconds the job may outlive the caller's wait
_POLL = 0.25
_FLAG_TTL = 600


def _flag_key(token: str) -> str:
	return f"huf_audience_refresh:{token}"


def refresh_hook_job(path: str, token: str, audience: str, managed_by: str) -> None:
	"""RQ job: run one refresh hook in this worker's own site/db connection and publish ok/error under ``token``.

	The hook commits its own writes (it calls ``upsert_audience_members``); the ``frappe.db.commit()`` after the
	call is by design and commits them in THIS job's connection, not the requesting one. Hook contract: idempotent
	and limited to the audience's members. If the caller already gave up
	(``cancelled`` flag) the hook is not started. Hooks MUST be idempotent: a hook that was already running when
	the caller timed out finishes on its own and its writes stand, but the caller has refused that start."""
	cache = frappe.cache()
	if cache.get_value(_flag_key(token)) == {"state": "cancelled"}:
		return
	try:
		frappe.get_attr(path)(audience=audience, managed_by=managed_by)
		frappe.db.commit()
		result = {"state": "ok"}
	except Exception as exc:  # noqa: BLE001 - relayed to the waiting caller
		frappe.db.rollback()
		frappe.log_error(title="Audience refresh hook failed", message=f"{path} for {audience}: {frappe.get_traceback()}")
		result = {"state": "error", "message": str(exc)[:300]}
	if cache.get_value(_flag_key(token)) != {"state": "cancelled"}:
		cache.set_value(_flag_key(token), result, expires_in_sec=_FLAG_TTL)


def _run_hook(path: str, seconds: int, audience: str, managed_by: str) -> None:
	"""Run a hook in its own RQ job and wait at most ``seconds`` for its result flag. Raises ``TimeoutError`` or
	``RuntimeError``. frappe.local / the db connection are never shared with another thread."""
	token = frappe.generate_hash(length=16)
	cache = frappe.cache()
	frappe.enqueue(
		"huf.ai.whatsapp.broadcast.audiences.external.refresh_hook_job",
		queue="short",
		timeout=seconds + _SLACK,
		path=path, token=token, audience=audience, managed_by=managed_by,
	)  # fmt: skip
	deadline = time.monotonic() + seconds
	try:
		while True:
			result = cache.get_value(_flag_key(token))
			if isinstance(result, dict) and result.get("state") == "ok":
				return
			if isinstance(result, dict) and result.get("state") == "error":
				raise RuntimeError(result.get("message") or "hook failed")
			if time.monotonic() >= deadline:
				cache.set_value(_flag_key(token), {"state": "cancelled"}, expires_in_sec=_FLAG_TTL)
				raise TimeoutError(f"no answer within {seconds}s")
			time.sleep(_POLL)
	finally:
		if cache.get_value(_flag_key(token)) != {"state": "cancelled"}:
			cache.delete_value(_flag_key(token))


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

	Commits mid-request BY DESIGN: the refresh runs in RQ jobs on their own connection, so this request must end
	its own snapshot (``frappe.db.commit()`` below) to see what the hook jobs committed. Hook contract: a refresh
	hook must be idempotent and must only write to the audience it is given (its members); the job commits the
	hook's writes in its own connection (see ``refresh_hook_job``).

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
				_run_hook(path, timeout, target["name"], target["managed_by"])
			except Exception as exc:
				frappe.log_error(title="Audience refresh failed", message=f"{path} for {target['name']}: {exc}")
				raise RefreshFailed(f"Audience {target['name']} could not be refreshed by {target['managed_by']} ({exc}). The broadcast was not started.") from exc
	frappe.db.commit()  # end our snapshot so the resnapshot sees what the hook jobs committed
	return True
