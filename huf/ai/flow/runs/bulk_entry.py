"""Bulk entry: start a flow for many members in one call, in chunks of background jobs.

Every member goes through :func:`huf.ai.flow.runs.start.start_flow_for_member`, so the entry policy and the
one-run-per ``(flow, member, entry_key)`` rule apply as for a single entry. Submitting the same list again with the
same ``entry_key`` starts nothing new; a new ``entry_key`` lets the same members enter again.
"""

from __future__ import annotations

import hashlib

import frappe
import redis
from frappe import _

from huf.ai.flow.runs.access import require_flow_read
from huf.ai.flow.runs.start import _check_key, start_flow_for_member
from huf.ai.channels import guard_steps
from huf.ai.flow.support import facts

CHUNK_SIZE = 500
MAX_MEMBERS = 200_000
SHORT_QUEUE_MAX = 1_000  # up to this many members the short queue is fast enough
PROGRESS_TTL_SECONDS = 7 * 24 * 3600
COUNTERS = ("done", "started", "skipped", "failed")


@frappe.whitelist(methods=["POST"])
def enter_members(flow: str, member_keys, entry_key: str | None = None) -> dict:
	"""Enter ``member_keys`` into ``flow``. Needs write on the flow. Returns ``{"batch_id", "total", "chunks"}``.

	``entry_key`` applies to every member (default: each member's own key, so one entry per member).
	"""
	from huf.ai.flow.app_scope.api_guards import guard_huf_flow
	guard_huf_flow(flow)
	keys = _clean_keys(member_keys)
	_require_flow_write(flow)
	if entry_key is not None and (not isinstance(entry_key, str) or not entry_key.strip()):
		frappe.throw(_("entry_key must be a non-empty string."))
	batch_id = batch_id_of(flow, keys, entry_key)
	chunks = [keys[i : i + CHUNK_SIZE] for i in range(0, len(keys), CHUNK_SIZE)]
	_init_progress(batch_id, len(keys))
	queue = "short" if len(keys) <= SHORT_QUEUE_MAX else "long"
	for index, chunk in enumerate(chunks):
		frappe.enqueue(
			"huf.ai.flow.runs.bulk_entry.run_chunk",
			queue=queue,
			job_id=f"huf_bulk_entry:{batch_id}:{index}",
			deduplicate=True,
			enqueue_after_commit=bool(getattr(frappe.local, "request", None)),
			flow_id=flow,
			member_keys=chunk,
			entry_key=entry_key,
			batch_id=batch_id,
		)
	return {"batch_id": batch_id, "total": len(keys), "chunks": len(chunks)}


@frappe.whitelist()
def get_bulk_entry_progress(flow: str, batch_id: str) -> dict:
	"""``{"total", "done", "started", "skipped", "failed"}`` of a batch (zeros once it expired). Needs read on the flow."""
	from huf.ai.flow.app_scope.api_guards import guard_flow
	guard_flow(flow, "view")
	require_flow_read(flow)
	if not frappe.db.exists("Flow Definition", flow):
		frappe.throw(_("Flow not found"), frappe.DoesNotExistError)
	return progress(batch_id)


def run_chunk(flow_id: str, member_keys: list[str], entry_key: str | None, batch_id: str) -> dict:
	"""Enter one chunk. Each member commits on its own, so a failure costs only that member's entry."""
	counts = dict.fromkeys(COUNTERS[1:], 0)
	with guard_steps.batch(), facts.batch(flow_id, member_keys):
		for key in member_keys:
			try:
				run = start_flow_for_member(flow_id, key, {}, entry_key=entry_key)
				counts["started" if run else "skipped"] += 1
			except Exception:  # noqa: BLE001 - one member must not stop the chunk; the key is not logged (PII rule)
				frappe.db.rollback()
				counts["failed"] += 1
				frappe.logger("flow").warning(f"bulk entry {batch_id}: a member entry failed")
	_add_progress(batch_id, counts)
	return counts


def batch_id_of(flow_id: str, keys: list[str], entry_key: str | None) -> str:
	"""Same flow, members and entry key give the same id, so a resubmission reuses its jobs and progress."""
	digest = hashlib.sha256(f"{flow_id}\0{entry_key or ''}\0".encode())
	for key in sorted(keys):
		digest.update(key.encode() + b"\0")
	return digest.hexdigest()[:32]


def progress(batch_id: str) -> dict:
	raw = redis.Redis.hgetall(frappe.cache, _redis_key(batch_id)) or {}  # raw ints, not pickled
	raw = {(k.decode() if isinstance(k, bytes) else k): v for k, v in raw.items()}
	return {name: int(raw.get(name) or 0) for name in ("total", *COUNTERS)}


def _clean_keys(member_keys) -> list[str]:
	if isinstance(member_keys, str):
		member_keys = frappe.parse_json(member_keys)
	if not isinstance(member_keys, list) or not member_keys:
		frappe.throw(_("member_keys must be a non-empty list."))
	if len(member_keys) > MAX_MEMBERS:
		frappe.throw(_("At most {0} members per call.").format(MAX_MEMBERS))
	for key in member_keys:
		_check_key(key)
	return list(dict.fromkeys(member_keys))  # drop repeats, keep order


def _require_flow_write(flow: str) -> None:
	if not flow or not frappe.db.exists("Flow Definition", flow):
		frappe.throw(_("Flow not found"), frappe.DoesNotExistError)
	require_flow_read(flow)
	if not frappe.has_permission("Flow Definition", "write", doc=flow):
		frappe.throw(
			_("Only people who can edit this flow can enter people into it."), frappe.PermissionError
		)


def _redis_key(batch_id: str) -> str:
	return frappe.cache.make_key(f"huf_bulk_entry_progress:{batch_id}")


def _init_progress(batch_id: str, total: int) -> None:
	"""A resubmission restarts the counters: its members are counted again (as skipped when already entered)."""
	key = _redis_key(batch_id)
	pipe = frappe.cache.pipeline()
	pipe.delete(key)
	pipe.hset(key, mapping={"total": total, **dict.fromkeys(COUNTERS, 0)})
	pipe.expire(key, PROGRESS_TTL_SECONDS)
	pipe.execute()


def _add_progress(batch_id: str, counts: dict) -> None:
	key = _redis_key(batch_id)
	pipe = frappe.cache.pipeline()
	for name, value in counts.items():
		pipe.hincrby(key, name, value)
	pipe.hincrby(key, "done", sum(counts.values()))
	pipe.expire(key, PROGRESS_TTL_SECONDS)
	pipe.execute()
