# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Distributed execution lock for a single Agent Procedure Run (T-21, GT-08).

Flow has no equivalent: two concurrent ``run_flow(name)`` calls both advance the same
``current_node_id`` cursor with nothing serializing them. This module copies the
precedent at ``huf/ai/agent_integration.py`` (``_conversation_lock_key`` /
``_run_queued_agent``, around lines 1135-2398): ``frappe.cache().set(key, 1, ex=TTL,
nx=True)`` to acquire, ``frappe.cache().expire(key, TTL)`` to heartbeat/extend, and
``frappe.cache().delete(key)`` to release -- the same "cache set nx/ex" convention
``agent_integration.py`` itself attributes to ``huf/ai/knowledge/indexer.py``.

Scope: one lock per Agent Procedure Run (not per procedure, not per conversation) --
two different runs of the same procedure execute independently; only two attempts to
advance the *same* run must be serialized.
"""

import frappe

RUN_LOCK_TTL = 600  # seconds; matches agent_integration._QUEUE_LOCK_TTL


def _run_lock_key(run_name: str) -> str:
	return f"agent_procedure_run_lock_{run_name}"


def acquire_run_lock(run_name: str, ttl: int = RUN_LOCK_TTL) -> bool:
	"""Try to acquire the execution lock for ``run_name``. Returns True iff acquired.

	Non-blocking: a caller that fails to acquire should treat this the same way
	``_run_queued_agent`` treats a held conversation lock -- another worker already owns
	execution of this run, so this caller must not advance any step state.
	"""
	return bool(frappe.cache().set(_run_lock_key(run_name), 1, ex=ttl, nx=True))


def extend_run_lock(run_name: str, ttl: int = RUN_LOCK_TTL) -> None:
	"""Heartbeat: refresh the lock's TTL while a long-running step is still in flight."""
	try:
		frappe.cache().expire(_run_lock_key(run_name), ttl)
	except (RuntimeError, OSError, AttributeError, KeyError) as exc:
		# Heartbeat must never raise into the caller's execution loop.
		frappe.logger("huf").debug(f"Procedure run lock heartbeat failed for {run_name}: {exc!s}")


def release_run_lock(run_name: str) -> None:
	"""Release the lock. Safe to call even if the lock was never held or already expired."""
	try:
		frappe.cache().delete(_run_lock_key(run_name))
	except (RuntimeError, OSError, AttributeError, KeyError) as exc:
		# Release is a cleanup path; must not mask the caller's own exception.
		frappe.logger("huf").debug(f"Procedure run lock release failed for {run_name}: {exc!s}")


class ProcedureRunLock:
	"""Context manager wrapping acquire/release for one Agent Procedure Run.

	Usage::

	    with ProcedureRunLock(run.name) as lock:
	        if not lock.acquired:
	            return  # another worker is already advancing this run
	        ...advance one or more steps...

	Mirrors the try/finally shape of ``agent_integration._run_queued_agent`` /
	``_RunHeartbeat`` without pulling in that module's conversation-specific concerns
	(sequencing, draining, heartbeat thread) -- Procedure runs execute one step chain at a
	time synchronously in Wave 2 (T-23), so no background heartbeat thread is needed yet;
	``extend_run_lock`` is exposed for a future long-running-step caller to call inline.
	"""

	def __init__(self, run_name: str, ttl: int = RUN_LOCK_TTL):
		self.run_name = run_name
		self.ttl = ttl
		self.acquired = False

	def __enter__(self):
		self.acquired = acquire_run_lock(self.run_name, self.ttl)
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		if self.acquired:
			release_run_lock(self.run_name)
		return False
