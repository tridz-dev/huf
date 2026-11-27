# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Reason codes a flow run trace may carry (H-W2-11).

A trace explains an outcome with a short code, never with free text, so no personal data can reach it. Huf's own
codes are listed here; an app adds its codes in ``hooks.py``::

        huf_flow_reason_codes = ["points_balance_low", "tier_not_eligible"]

(a mapping ``{code: description}`` works too). Nothing here raises: an unregistered code becomes ``unknown``.

frappe is imported inside functions so the module also loads without a bench.
"""

import re

HOOK = "huf_flow_reason_codes"
UNKNOWN = "unknown"

HUF_CODES = frozenset(
	{
		UNKNOWN,
		# pre-send guard chain and send policy
		"hook_error",
		"hook_timeout",
		# AI kill switch (huf.ai.run_budget.AI_DISABLED)
		"ai_disabled",
		# router.llm: the run's deadline passed or its AI spend cap is used up
		"ai_budget_exceeded",
		"bad_recipient",
		"freq_cap",
		"template_params_invalid",
		"header_invalid",
		"media_host_not_allowed",
		"no_opt_in",
		"window_defer_exhausted",
		# a send the window deferred: the run is parked (runs.park.SEND_WINDOW_REASON)
		"send_window",
		# a step that is turned off was skipped (support.turned_off)
		"turned_off",
		# send step: no outbox transport for this channel; a send step cannot be retried (G2)
		"channel_unsupported",
		"SEND_RETRY_FORBIDDEN",
		# member exited every flow on a STOP keyword (H-W2-14)
		"opt_out",
		# condition facts providers
		"facts_error",
		"facts_timeout",
		# send-time token binder
		"token_unbound",
		# split node: marketing send suppressed for a held-out run (H-W2-07)
		"holdout_no_contact",
		# codes the WhatsApp outbound policy already refuses with
		"blocked_by_hook",
		"bsuid_recipient",
		"marketing_opted_out",
		"opted_out",
		"recipient_not_allowlisted",
		"template_not_approved",
	}
)

_CODE_SHAPE = re.compile(r"[a-z][a-z0-9_]{0,63}")


def registered_codes() -> frozenset[str]:
	"""Huf's codes plus every well-formed code declared by an installed app.

	``frappe.get_hooks`` is cached per site, so this keeps no cache of its own.
	"""
	return HUF_CODES | _app_codes()


def normalize(code: object) -> str:
	"""``code`` if it is registered, else ``unknown`` (logged)."""
	if isinstance(code, str) and (code in HUF_CODES or code in _app_codes()):
		return code
	# The rejected value is not logged: a caller that passed free text may have passed personal data.
	_warn("unregistered flow reason code stored as unknown")
	return UNKNOWN


FIELD = "reason_code"
"""The step record key the trace reads the code from."""

_REASONED_STATUSES = frozenset({"blocked", "deferred", "skipped"})


def code_for(record: object) -> str | None:
	"""The reason code a step record explains itself with, or None for a step that needs none.

	A blocked, deferred or skipped record always gets a registered code (``unknown`` when its reason is not one).
	"""
	if not isinstance(record, dict):
		return None
	status = record.get("status")
	if record.get("skipped") is True and status not in _REASONED_STATUSES:
		return "turned_off"
	if status not in _REASONED_STATUSES:
		return None
	return normalize(record.get(FIELD) or record.get("reason"))


def stamp(record: object) -> object:
	"""``record`` with its ``reason_code`` set (a new dict); any other value unchanged. Never raises."""
	try:
		code = code_for(record)
	except Exception:  # noqa: BLE001 - a trace write must never fail a run
		_warn("flow reason code could not be read")
		code = UNKNOWN if isinstance(record, dict) else None
	if code is None:
		return record
	return {**record, FIELD: code}


def _app_codes() -> frozenset[str]:
	try:
		import frappe

		apps = frappe.get_installed_apps()
	except Exception:  # noqa: BLE001 - a trace write must never fail on this
		_warn(f"{HOOK}: installed apps could not be read")
		return frozenset()
	codes: set[str] = set()
	for app in apps:
		# one app's broken declaration must not drop the codes of the others
		try:
			declared = list(frappe.get_hooks(HOOK, app_name=app) or [])
		except Exception:  # noqa: BLE001 - an app's hooks must never fail a run
			_warn(f"{HOOK}: could not read the codes of {app}")
			continue
		for code in declared:
			if isinstance(code, str) and _CODE_SHAPE.fullmatch(code):
				codes.add(code)
			else:
				_warn(f"{HOOK}: ignored a malformed code from {app}")
	return frozenset(codes)


def _warn(message: str) -> None:
	try:
		import frappe

		frappe.logger("flow").warning(message)
	except Exception:  # noqa: BLE001, S110 - logging must never fail a run
		pass
