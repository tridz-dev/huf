# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Ordered, fail-closed pre-send guard chain (H-W2-01).

:func:`evaluate` runs Huf's built-in steps and then every handler an app registers in ``hooks.py``::

        huf_pre_send_hooks = ["my_app.sending.check_consent"]

A step is called as ``step(request)`` with its own copy of the plain request dict and answers with exactly::

        {"allow": True}
        {"allow": False, "reason": "<code>"}  # a code registered in ``reason_codes``

The first block ends the chain. Anything else (``None``, a bare bool, another shape), an exception, a bad
dotted path or a failing hook lookup blocks with ``hook_error``; a step that runs longer than the timeout
(2 s, site config ``huf_pre_send_hook_timeout_s``) blocks with ``hook_timeout``. A block is final. This is
stricter than ``huf_gateway_pre_send``, where ``None`` allows.

Huf's own steps (:mod:`huf.ai.channels.guard_steps`) run first. Steps must only observe and decide.

The frequency cap runs last, only when every step allowed. For a live send (``request["live"] is True``)
with a cap it counts the send and COMMITS the current transaction, so call :func:`evaluate` only where
committing the work so far is safe. A preview never counts. Neither the result nor the log line holds request data or exception text.

A step runs in its own thread so the wait can be bounded. A thread cannot be killed: one that timed out is
abandoned and refused any further ``frappe.db`` call, and a query it already has in flight is waited for,
because the caller and the step share one connection.
"""

from __future__ import annotations

import contextvars
import copy
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import frappe
from frappe.utils.local import _contextvar

from huf.ai.channels import guard_steps
from huf.ai.flow.support import reason_codes

HOOK = "huf_pre_send_hooks"
TIMEOUT_CONF = "huf_pre_send_hook_timeout_s"
DEFAULT_TIMEOUT_SECONDS = 2.0
HOOK_ERROR = "hook_error"
HOOK_TIMEOUT = "hook_timeout"

Step = Callable[[dict], Any]
# Huf's own steps as (name, step), run in this order before any app hook.
BUILTIN_STEPS: list[tuple[str, Step]] = list(guard_steps.STEPS)


@dataclass(frozen=True)
class GuardResult:
	allowed: bool
	reason: str | None = None
	step: str | None = None
	defer_until: datetime | None = None  # aware UTC; only the send window step sets it


def evaluate(request: dict, *, header: dict | None = None, timeout: float | None = None) -> GuardResult:
	"""Run the chain for one send. Never raises: whatever goes wrong is a block.

	``header`` is the send's media or location header, seen by built-in steps only.
	"""
	step_name = None
	try:
		seconds = _timeout(timeout)
		# Both lists are read before any step runs, so a broken hook lookup blocks without side effects.
		steps = [*BUILTIN_STEPS, *((path, None) for path in _hook_paths())]
		builtins = len(BUILTIN_STEPS)
		for index, (step_name, step) in enumerate(steps):
			step = step or frappe.get_attr(step_name)
			args = {**request, "header": header} if index < builtins else request
			reason = _run_step(step_name, step, copy.deepcopy(args), seconds)
			if reason:
				return GuardResult(False, reason, step_name)
		step_name = guard_steps.CAP_STEP
		reason = _cap_step(copy.deepcopy(request), seconds)
		return GuardResult(False, reason, step_name) if reason else GuardResult(True)
	except Exception as error:  # noqa: BLE001 - fail closed, never raise out
		_warn(step_name, type(error).__name__)
		return GuardResult(False, HOOK_ERROR, step_name if isinstance(step_name, str) else None)


def _cap_step(request: dict, seconds: float) -> str | None:
	"""Resolver hooks run under the step timeout; the counting runs on the caller's thread.

	A step thread can be abandoned, which would leave a half-made claim and its row lock in the transaction.
	"""
	name, caps = guard_steps.CAP_STEP, []

	def resolve(args: dict) -> dict:
		caps.extend(guard_steps.resolve_caps(args))
		return {"allow": True}

	reason = _run_step(name, resolve, request, seconds)
	return reason or _reason(name, guard_steps.apply_caps(request, caps))


def _hook_paths() -> list[str]:
	raw = frappe.get_hooks(HOOK) or []
	return [raw] if isinstance(raw, str) else list(raw)


def _timeout(override: float | None) -> float:
	value = override if override is not None else (frappe.conf or {}).get(TIMEOUT_CONF)
	try:
		value = float(value)
	except (TypeError, ValueError):
		return DEFAULT_TIMEOUT_SECONDS
	# also rejects nan and inf, which would leave the wait unbounded
	return value if 0 < value <= threading.TIMEOUT_MAX else DEFAULT_TIMEOUT_SECONDS


def _run_step(name: str, step: Step, request: dict, seconds: float) -> str | None:
	"""None when the step allows, else the block reason."""
	outcome: dict[str, Any] = {}
	db = _StepDB.wrap(getattr(frappe.local, "db", None))

	def call() -> None:
		try:
			if db:
				# a private copy of frappe.local, so only this thread sees the wrapped connection
				_contextvar.set({**_contextvar.get(), "db": db})
			outcome["verdict"] = step(request)
		except BaseException as error:  # noqa: BLE001 - a thread would otherwise swallow it and report nothing
			outcome["error"] = type(error).__name__

	thread = threading.Thread(
		target=contextvars.copy_context().run, args=(call,), name="huf-pre-send-step", daemon=True
	)
	thread.start()
	try:
		thread.join(seconds)
	finally:
		timed_out = thread.is_alive()
		if timed_out and db:
			db.abandon()

	if timed_out:
		_warn(name, HOOK_TIMEOUT)
		return HOOK_TIMEOUT
	if "error" in outcome:
		_warn(name, outcome["error"])
		return HOOK_ERROR
	return _reason(name, outcome.get("verdict"))


def _reason(name: str, verdict: Any) -> str | None:
	if isinstance(verdict, dict):
		allowed = verdict.get("allow")
		if allowed is True and set(verdict) == {"allow"}:
			return None
		if allowed is False:
			return reason_codes.normalize(verdict.get("reason"))
	_warn(name, "invalid verdict")
	return HOOK_ERROR


def _warn(step: Any, what: str) -> None:
	try:
		frappe.logger("flow").warning(f"pre-send step {step} blocked: {what}")
	except Exception:  # noqa: BLE001, S110 - logging must never turn a block into a raise
		pass


class _StepDB:
	"""The caller's connection as a step thread sees it: calls are serialised and stop once abandoned."""

	__slots__ = ("_abandoned", "_db", "_lock")

	def __init__(self, db: Any):
		self._db = db
		self._lock = threading.RLock()
		self._abandoned = False

	@classmethod
	def wrap(cls, db: Any) -> _StepDB | None:
		return cls(db) if db is not None else None

	def abandon(self) -> None:
		self._abandoned = True
		with self._lock:  # returns once no query is in flight
			pass

	def __getattr__(self, name: str) -> Any:
		attr = getattr(self._db, name)
		if not callable(attr):
			return attr

		def call(*args, **kwargs):
			with self._lock:
				if self._abandoned:
					raise RuntimeError("pre-send step timed out; database access refused")  # noqa: TRY003
				return attr(*args, **kwargs)

		return call
