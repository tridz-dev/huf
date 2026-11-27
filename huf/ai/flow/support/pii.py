# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Mask personal data before a flow writes a run trace, a step error or an error log (H-W2-12, G4).

The masker itself (:mod:`huf.ai.flow.support.pii_mask`) is pure; this module adds the app field names from the
``huf_flow_pii_fields`` hook (a list of field names) and the write rules:

- ``mask_pii`` returning ``None`` means "cannot be masked": the value is dropped, never written raw.
- An error log keeps its title and a masked traceback; one that cannot be masked keeps only a placeholder.

frappe is imported inside functions so the module also loads without a bench.
"""

from __future__ import annotations

from huf.ai.flow.support.pii_mask import mask_pii

HOOK = "huf_flow_pii_fields"
DROPPED = "[redacted]"


def app_pii_fields() -> tuple[str, ...]:
	"""Field names apps declare as personal data. ``frappe.get_hooks`` is cached per site."""
	try:
		import frappe

		return tuple(str(f) for f in (frappe.get_hooks(HOOK) or []) if isinstance(f, str) and f.strip())
	except Exception:  # noqa: BLE001 - no site: no app fields
		return ()


def mask_value(value):
	"""A masked copy of ``value`` for a trace, or ``None`` when it must be dropped."""
	return mask_pii(value, app_pii_fields())


def mask_text(text) -> str:
	"""``text`` with personal data masked; ``[redacted]`` when it cannot be masked."""
	if text is None or text == "":
		return text
	masked = mask_value(str(text))
	return masked if isinstance(masked, str) else DROPPED


def log_flow_error(title=None, message=None, *args, **kwargs):
	"""``frappe.log_error`` with the title and message masked; the traceback is the default message."""
	import frappe

	if message is None:
		message = frappe.get_traceback(with_context=False) if _has_exception() else None
	return frappe.log_error(mask_text(title), mask_text(message), *args, **kwargs)


def _has_exception() -> bool:
	import sys

	return sys.exc_info()[0] is not None
