# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Request-scope cache for read-only Agent Procedure results (T-33).

Decision D7 is settled, not open for reinterpretation: **request scope only in v1, no
TTL cache** -- the invalidation problem disappears by construction, because a value never
outlives the request that computed it. Do not extend this to a TTL cache "for
completeness"; that is a different decision this module deliberately does not make.

Storage is ``frappe.local.cache`` -- a plain ``dict`` that Frappe resets at the start of
every request (``frappe.init``) -- rather than ``frappe.cache()`` (the Redis-backed,
cross-request cache). That is the actual request-scoping mechanism: no expiry accounting
is needed because the dict itself does not survive past the request. This is the
"frappe.local" half of GT-09's "namespacing tied to frappe.local, or similar."

The *shape* otherwise follows the house style at ``huf/permissions.py:161-238`` (GT-09,
the closest precedent -- there is no central cache helper in this app and this module is
not an attempt to become one): a namespaced key builder, a getter, a setter and an
explicit bust helper, nothing cleverer.

Cache key = pinned procedure version + normalised inputs (sorted-key, stable JSON, so
key order in the caller's dict never changes the digest) + user/security scope + tenant
(company). Two callers with equivalent inputs in different key order hit the same entry;
two callers with different users, companies, or procedure versions never collide.

Structural guarantee (I8): :func:`set_cached_result` takes the pinned procedure's own
``is_read_only`` flag (Agent Procedure doctype field, derived from ``not
contains_writes``) as a required keyword and refuses to write anything -- raises
:class:`MutatingProcedureCacheError` -- when it is falsy. There is no code path in this
module that stores a result without that check running first; callers cannot opt out of
it by passing a flag of their own, because there is no such flag to pass.
"""

from __future__ import annotations

import hashlib
import json

import frappe

_CACHE_NAMESPACE = "huf_procedure_result"


class MutatingProcedureCacheError(Exception):
	"""Raised when the cache is asked to store a result for a non-read-only procedure.

	D7 / I8: a Procedure whose ``contains_writes`` is true (``is_read_only`` false) must
	never be cached, by construction -- not by caller discipline.
	"""


def _normalise(value: object) -> str:
	"""Deterministic, stable JSON encoding: sorted keys, no separator ambiguity.

	Equivalent inputs supplied in different key order produce byte-identical output,
	so they hash to the same cache key.
	"""
	return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _cache_key(*, procedure_version: str, inputs: dict | None, user: str, company: str | None) -> str:
	if not procedure_version:
		raise ValueError("cache key requires a pinned procedure_version")
	if not user:
		raise ValueError("cache key requires a user (security scope)")

	digest = hashlib.sha256(_normalise(inputs or {}).encode("utf-8")).hexdigest()
	scope = company or ""
	return f"{_CACHE_NAMESPACE}::{procedure_version}::{user}::{scope}::{digest}"


def _request_store() -> dict:
	"""The request-scoped dict backing this cache.

	``frappe.local.cache`` is reset to a fresh dict at the start of every request by
	Frappe's own request bootstrap -- that reset is what makes this cache request-scope
	without any expiry bookkeeping. Falls back to a module-level dict only when
	``frappe.local`` has no ``cache`` attribute yet (e.g. very early bootstrap, or a
	console session that never went through a full request init) so a lookup never
	raises ``AttributeError``.
	"""
	local = getattr(frappe, "local", None)
	store = getattr(local, "cache", None) if local is not None else None
	if store is None:
		store = {}
		if local is not None:
			local.cache = store
	return store


def get_cached_result(*, procedure_version: str, inputs: dict | None, user: str, company: str | None = None):
	"""Return the cached result, or ``None`` if there is no entry for this key."""
	key = _cache_key(procedure_version=procedure_version, inputs=inputs, user=user, company=company)
	return _request_store().get(key)


def set_cached_result(
	*,
	procedure_version: str,
	inputs: dict | None,
	user: str,
	company: str | None = None,
	is_read_only: bool,
	result,
) -> None:
	"""Store *result* for this key -- refuses unless ``is_read_only`` is true (I8/D7).

	``is_read_only`` is not a hint the caller can fudge to force a cache write: it is
	meant to be passed straight through from the pinned procedure's own
	``is_read_only`` field, and this function is the single choke point every write
	path (see ``huf.ai.graph.procedure_runtime``) must go through to populate the
	cache. A falsy value here means "never write," full stop.
	"""
	if not is_read_only:
		raise MutatingProcedureCacheError(
			f"Refusing to cache result for procedure version {procedure_version!r}: "
			"not read-only (contains_writes) -- D7/I8 forbids caching a mutating procedure."
		)
	key = _cache_key(procedure_version=procedure_version, inputs=inputs, user=user, company=company)
	_request_store()[key] = result


def bust_procedure_cache(
	*, procedure_version: str, inputs: dict | None, user: str, company: str | None = None
) -> None:
	"""Explicit bust helper, mirroring ``permissions.py``'s ``_bust_cache`` shape.

	Rarely needed given request scope (the entry disappears with the request anyway),
	but kept symmetrical with the house pattern and useful for tests / a single request
	that mutates and then re-reads the same key.
	"""
	key = _cache_key(procedure_version=procedure_version, inputs=inputs, user=user, company=company)
	_request_store().pop(key, None)
