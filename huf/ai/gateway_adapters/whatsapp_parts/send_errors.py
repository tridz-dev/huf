"""WhatsApp send-error types and classifier (moved out of whatsapp.py; re-imported there)."""

from __future__ import annotations

from typing import Any

import frappe
import requests
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_errors as we


class WhatsAppWindowClosed(frappe.ValidationError):
	"""The 24h customer-service window is closed and no template fallback is configured."""


class WhatsAppFallbackUnavailable(WhatsAppWindowClosed):
	"""The window is closed and the configured fallback template cannot be sent.

	Subclasses :class:`WhatsAppWindowClosed` so every caller that already treats a closed window as
	"not sendable right now" handles it. ``code`` is the stable machine-readable reason (a refusal is a
	raised typed error, not a delivery: ``OutboundDelivery`` requires a real provider message id).
	"""

	def __init__(self, message: str, code: str):
		super().__init__(message)
		self.code = code


class WhatsAppSendError(ValueError):
	"""A Graph send failed. ``classification`` is the :func:`whatsapp_errors.classify` result."""

	def __init__(self, message: str, classification: dict[str, Any] | None = None):
		super().__init__(message)
		self.classification = classification or we.classify(message)


class WhatsAppPartsError(Exception):
	"""A multi-part text reply stopped part-way.

	``sent_ids`` are the wamids already accepted by Meta (in order), ``remaining`` the formatted
	parts still to send, ``cause`` the original error. Retry the SEND with ``remaining`` only.
	"""

	def __init__(self, cause: BaseException, sent_ids: list[str], remaining: list[str]):
		super().__init__(str(cause))
		self.cause = cause
		self.sent_ids = list(sent_ids)
		self.remaining = list(remaining)


# Graph "unknown error" / "service temporarily unavailable": the message may have been accepted.
_OUTCOME_UNKNOWN_CODES = frozenset({1, 2})
_RATE_LIMIT_KINDS = frozenset({"rate_limited", "pair_rate_limited"})


def _never_connected(exc: BaseException) -> bool:
	"""True when the cause chain shows the connection was never opened, so no request was written."""
	seen: set[int] = set()
	while exc is not None and id(exc) not in seen:
		seen.add(id(exc))
		if isinstance(exc, requests.ConnectTimeout):
			return True
		if isinstance(exc, requests.ConnectionError) and exc.args:
			reason = getattr(exc.args[0], "reason", None)
			if isinstance(reason, (NewConnectionError, ConnectTimeoutError)):
				return True
		exc = exc.__cause__ or exc.__context__
	return False


def is_provably_unsent(exc: BaseException) -> bool:
	"""True only when Meta certainly did not accept the message, so sending it again cannot double it.

	That is: the connection was never opened, Meta answered with an error code or a rate limit, or Huf
	refused before posting. A read timeout, a dropped connection, an unreadable answer and anything
	unrecognised are unknown outcomes: False.
	"""
	if isinstance(exc, WhatsAppPartsError):
		return not exc.sent_ids and is_provably_unsent(exc.cause)
	if isinstance(exc, WhatsAppWindowClosed) or _never_connected(exc):
		return True
	if isinstance(exc, bridge.BridgeError):
		payload = exc.payload if isinstance(exc.payload, dict) else {}
		if payload.get("error") not in (None, "send_failed"):
			return True  # a policy or validation refusal
	elif not isinstance(exc, (WhatsAppSendError, requests.HTTPError)):
		return False
	classification = classify_send_exception(exc)
	code = classification.get("code")
	if code is not None:
		return code not in _OUTCOME_UNKNOWN_CODES
	return classification.get("kind") in _RATE_LIMIT_KINDS


def classify_send_exception(exc: BaseException) -> dict[str, Any]:
	"""Classify whatever a WhatsApp send path raised (parts error, bridge error, Graph error, timeout)."""
	if isinstance(exc, WhatsAppPartsError):
		return classify_send_exception(exc.cause)
	if isinstance(exc, WhatsAppWindowClosed):
		return we.classify((None, {"error": {"code": 131047, "message": str(exc)}}))
	if isinstance(exc, WhatsAppSendError):
		return exc.classification
	if isinstance(exc, bridge.BridgeError):
		payload = exc.payload if isinstance(exc.payload, dict) else {}
		code = payload.get("graph_code")
		if code is not None or payload.get("kind"):
			base = we.classify((None, {"error": {"code": code, "message": payload.get("message") or ""}})) if code is not None else {}
			return {
				"code": code,
				"subcode": payload.get("subcode"),
				"kind": payload.get("kind") or base.get("kind") or "unknown",
				"retryable": bool(payload.get("retryable", base.get("retryable"))),
				"retry_after_hint": base.get("retry_after_hint"),
				"operator_text": payload.get("operator_text") or base.get("operator_text") or "",
				"user_msg": payload.get("user_msg"),
				"message": payload.get("message") or "",
				"http_status": base.get("http_status"),
			}
		return we.classify(str(payload.get("message") or payload.get("error") or exc))
	return we.classify(exc)
