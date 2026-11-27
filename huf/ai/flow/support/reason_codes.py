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
		"bad_recipient",
		"freq_cap",
		"template_params_invalid",
		"header_invalid",
		"media_host_not_allowed",
		"no_opt_in",
		"window_defer_exhausted",
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
