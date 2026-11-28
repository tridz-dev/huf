# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Retry classes, backoff and delivery error shape of the channel outbox (see ``outbox`` for the lifecycle).

Imported back into ``outbox`` under the same names, so ``outbox.classify`` and the rest keep working.
"""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.channels.outbound import recipient_binder, token_binder


TRANSIENT, PERMANENT, BLOCKED, AMBIGUOUS = "transient", "permanent", "blocked", "ambiguous"
MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 3600
RETRY_EXHAUSTED = "retry_exhausted"
NOT_ACCEPTED = "not_accepted"


class LiteralRecipient(ValueError):
	"""The step names a phone number itself; the outbox stores references only (G4)."""


def classify(error: Any) -> str:
	"""The retry class of ``error``: a reason code string (guard/binder block), a classification dict, or a send exception."""
	return delivery_error(error)["class"]


def delivery_error(error: Any, *, posting: bool = True) -> dict:
	"""``{"class", "code", "kind"}`` for ``error``; codes and kinds only, never message text (G4).

	``posting`` False: the error was raised before the transport ran, so nothing can have been sent.
	"""
	if isinstance(error, token_binder.TokenUnbound):
		return {"class": BLOCKED, "code": token_binder.TOKEN_UNBOUND, "kind": "guard"}
	if isinstance(error, recipient_binder.RecipientUnbound):
		return {"class": BLOCKED, "code": recipient_binder.RECIPIENT_UNBOUND, "kind": "guard"}
	if isinstance(error, str):
		return {"class": BLOCKED, "code": error, "kind": "guard"}
	classification = error if isinstance(error, dict) else _classify_exception(error)
	code = classification.get("code")
	retryable = bool(classification.get("retryable"))
	error_class = TRANSIENT if retryable else PERMANENT
	if posting and isinstance(error, BaseException) and _outcome_unknown(error, retryable):
		error_class = AMBIGUOUS
	return {
		"class": error_class,
		"code": str(code) if code is not None else str(classification.get("kind") or "unknown"),
		"kind": str(classification.get("kind") or "unknown"),
	}


def backoff_seconds(attempts: int) -> int:
	"""Delay before attempt ``attempts + 1``: 30 s doubling, capped at one hour."""
	return min(BACKOFF_BASE_S * 2 ** max(attempts - 1, 0), BACKOFF_MAX_S)


def _outcome_unknown(exc: BaseException, retryable: bool) -> bool:
	"""Whether the channel may have accepted the message although the send raised ``exc``."""
	import requests

	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.gateway_adapters.whatsapp_parts.send_errors import is_provably_unsent

	# a non-retryable local error is plainly permanent; a transport or unreadable-answer one is not
	posted = retryable or isinstance(exc, (requests.RequestException, bridge.BridgeError))
	if not posted:
		return False
	try:
		return not is_provably_unsent(exc)
	except Exception:  # noqa: BLE001 - unclassifiable is unknown
		return True


def _classify_exception(exc: BaseException) -> dict:
	from huf.ai.gateway_adapters.whatsapp_parts.send_errors import classify_send_exception

	if isinstance(exc, frappe.PermissionError):
		return {"kind": "permission", "retryable": False, "code": "no_send_authority"}
	try:
		return classify_send_exception(exc)
	except Exception:  # noqa: BLE001 - unclassifiable is permanent
		return {"kind": "unknown", "retryable": False}
