# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Typed, redacted provider errors.

Legacy provider modules used to *return* ``"... API Error: ..."`` strings that were
persisted as a successful agent response. They now raise ``ProviderError`` instead.
This module is dependency-free (no frappe, no litellm) so any provider can import it.
"""

from __future__ import annotations

import re

KINDS = (
	"auth",
	"model_not_found",
	"rate_limited",
	"quota_exceeded",
	"bad_request",
	"server_error",
	"timeout",
	"unknown",
)

PUBLIC_MESSAGES = {
	"auth": "This provider is not configured correctly yet. Add or update its API key and try again.",
	"model_not_found": "The selected model is no longer available from this provider. Choose a different model and try again.",
	"rate_limited": "This provider is rate-limiting requests right now. Please wait a moment and try again.",
	"quota_exceeded": "The provider account has run out of quota or reached its spend cap. Check the provider's billing and try again.",
	"bad_request": "The AI provider rejected this request. Try again or choose a different model.",
	"server_error": "The AI provider is temporarily unavailable. Please try again in a moment.",
	"timeout": "The AI provider took too long to respond. Please try again in a moment.",
	"unknown": "The AI provider could not complete this request. Please try again or choose a different model.",
}

_REDACTIONS = (
	re.compile(r"(?i)([?&](?:token|api[_-]?key|secret|access_token|key|password)=)[^&\s\"'<>]+"),
	re.compile(r"(?i)\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}"),
	re.compile(r"(?i)((?:x-goog-api-key|x-api-key|authorization|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"),
	re.compile(r"\b(?:sk|AIza|gsk|xai)[-_A-Za-z0-9]{16,}"),
)


def redact_text(text) -> str:
	"""Strip API keys / auth headers from provider text."""
	out = str(text or "")
	out = _REDACTIONS[0].sub(r"\1[redacted]", out)
	out = _REDACTIONS[1].sub(r"\1 [redacted]", out)
	out = _REDACTIONS[2].sub(r"\1[redacted]", out)
	out = _REDACTIONS[3].sub("[redacted]", out)
	return out


def specific_message(kind: str, provider: str | None = None, model: str | None = None) -> str | None:
	"""Plain-English, provider-specific reason for a failure kind (None when kind has no specific wording)."""
	who = f"The {provider} key" if provider else "The provider key"
	prov = provider or "the provider"
	if kind == "auth":
		return f"{who} was rejected: check the provider key in AI Providers."
	if kind == "model_not_found":
		m = f" '{model.split('/', 1)[-1]}'" if model else ""
		return f"The model{m} was not found at {prov}: check the model name on the agent."
	if kind == "rate_limited":
		return f"{prov} is rate-limiting requests: wait a moment and run again."
	if kind == "quota_exceeded":
		return f"The {prov} account is out of quota or credit: check billing at the provider."
	if kind == "timeout":
		return f"{prov} took too long to respond: run again in a moment."
	if kind == "server_error":
		return f"Could not reach {prov} (network or provider outage): run again in a moment."
	return None


def classify_status(status_code, text: str = "") -> str:
	"""Map an HTTP status (and body text) to an error kind."""
	low = (text or "").lower()
	try:
		status = int(status_code) if status_code is not None else None
	except (TypeError, ValueError):
		status = None
	quota = any(m in low for m in ("quota", "spend cap", "spending cap", "billing", "insufficient_quota", "credit"))
	if status in (401, 403):
		return "auth"
	if status == 404:
		return "model_not_found"
	if status == 402:
		return "quota_exceeded"
	if status == 429:
		return "quota_exceeded" if quota else "rate_limited"
	if status in (408, 504):
		return "timeout"
	if status is not None and status >= 500:
		return "server_error"
	if status is not None and 400 <= status < 500:
		return "bad_request"
	return classify_text(text)


def classify_text(text: str) -> str:
	low = (text or "").lower()
	if any(m in low for m in ("api key not configured", "password not found", "invalid api key", "incorrect api key", "unauthorized", "authenticationerror", "permissiondeniederror")):
		return "auth"
	if any(m in low for m in ("no longer available", "model not found", "notfounderror", "unsupported model")):
		return "model_not_found"
	if any(m in low for m in ("insufficient_quota", "spend cap", "spending cap", "exceeded your current quota")):
		return "quota_exceeded"
	if "ratelimit" in low or "rate limit" in low or "too many requests" in low:
		return "rate_limited"
	if "timeout" in low or "timed out" in low:
		return "timeout"
	if any(m in low for m in ("internalservererror", "server error", "service unavailable", "connection refused",
		"failed to connect", "connection error", "connection reset")):
		return "server_error"
	if "badrequesterror" in low or "invalid_request" in low:
		return "bad_request"
	return "unknown"


class ProviderError(Exception):
	"""A provider call failed. ``str(exc)`` is the user-safe public message.

	``log_message`` is the redacted raw detail (safe to store, never shown to end users).
	"""

	def __init__(self, kind: str = "unknown", *, status_code=None, detail: str = "", public_message: str | None = None):
		kind = kind if kind in KINDS else "unknown"
		self.kind = kind
		self.status_code = status_code
		self.public_message = public_message or PUBLIC_MESSAGES[kind]
		self.log_message = redact_text(detail)[:1000] or self.public_message
		super().__init__(self.public_message)

	@classmethod
	def from_http(cls, status_code, text: str, provider: str = "provider") -> "ProviderError":
		kind = classify_status(status_code, text)
		return cls(kind, status_code=status_code, detail=f"{provider} HTTP {status_code}: {text}")

	@classmethod
	def from_exception(cls, exc: BaseException, provider: str = "provider") -> "ProviderError":
		if isinstance(exc, ProviderError):
			return exc
		status = getattr(exc, "status_code", None)
		detail = f"{provider} {type(exc).__name__}: {exc}"
		kind = classify_status(status, f"{type(exc).__name__} {exc}")
		return cls(kind, status_code=status, detail=detail)
