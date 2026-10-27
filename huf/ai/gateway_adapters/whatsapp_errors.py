"""Meta WhatsApp Cloud API error classification and retry policy (pure Python, no frappe).

``classify(err)`` turns whatever a send path caught (Graph error body, ``(status, body)``
tuple, requests-style exception or response, or a string) into one dict:

	code, subcode, kind, retryable, retry_after_hint, operator_text, user_msg, message,
	http_status

``kind`` is one of: auth, informational, rate_limited, pair_rate_limited, window_closed, pacing_dropped, template,
media, recipient, permission, param, server, timeout, unknown.

``backoff_seconds(kind, attempt)`` and ``is_permanent(classification)`` form the retry
policy: 2, 4, 8, 16 s with +/-20 percent jitter for retryable errors, a fixed 6 s for the
pair rate limit (131056). The caller re-enqueues a job with that delay; nothing here sleeps.

Provenance of the code table ("V" = listed in Meta's error-code documentation as recorded in
gap/META_CAPABILITIES.md, "M" = from memory, not re-verified against the live docs):
	V: 190, 80007, 130429, 131026, 131031, 131047, 131048, 131049, 131051, 131052, 131053,
	   131056, 132000, 132001, 132005, 132007, 132012, 132015, 132016, 133010, 368, 100, 131009
	M: 1, 2, 3, 4, 10, 17, 32, 33, 102, 200-299 range, 613, 131000, 131005, 131008, 131016,
	   131021, 131057, 130472, 2388xxx subcodes, 463/467 token subcodes
	U: 131030 (recipient not in allowed list on test numbers; behaviour unverified)
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

KINDS = (
	"auth",
	"rate_limited",
	"pair_rate_limited",
	"window_closed",
	"template",
	"media",
	"recipient",
	"pacing_dropped",
	"permission",
	"param",
	"server",
	"timeout",
	"unknown",
)

MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 16.0
BACKOFF_JITTER = 0.2
PAIR_RATE_LIMIT_DELAY_SECONDS = 6.0

# code -> (kind, retryable, retry_after_hint_seconds, operator_text)
_CODES: dict[int, tuple[str, bool, float | None, str]] = {
	# --- auth (190 V)
	# --- informational: expected, not an operator problem (131060 unsupported inbound type, 2593109 user-preference notice)
	131060: ("informational", False, None, "Informational: Meta could not deliver this item; no action needed."),  # U
	2593109: ("informational", False, None, "Informational: no action needed."),  # U
	190: ("auth", False, None, "The access token is invalid or expired. Generate a new system user token and update the account."),
	102: ("auth", False, None, "The API session expired. Generate a new access token."),  # M
	# --- permission
	10: ("permission", False, None, "The token lacks permission for this action. Grant whatsapp_business_messaging to the app/system user."),  # M
	3: ("permission", False, None, "The app lacks the required capability for this call. Check the app permissions."),  # M
	131005: ("permission", False, None, "Access denied. Check the token's WhatsApp permissions and the assigned assets."),  # M
	131031: ("permission", False, None, "The business account is restricted or the two-step PIN is wrong. Resolve it in WhatsApp Manager."),  # V
	131048: ("permission", False, None, "Message blocked because the sender was flagged for spam. Improve quality and wait before sending more."),  # V
	133010: ("permission", False, None, "The sending phone number is not registered. Register the number with the Cloud API."),  # V
	368: ("permission", False, None, "The account is temporarily blocked for a policy violation. Review Meta's account quality and policy notices."),  # V
	# --- rate limits (retryable)
	4: ("rate_limited", True, None, "App-level API rate limit reached. Retry with backoff."),  # M
	17: ("rate_limited", True, None, "User-level API rate limit reached. Retry with backoff."),  # M
	32: ("rate_limited", True, None, "Page-level API rate limit reached. Retry with backoff."),  # M
	613: ("rate_limited", True, None, "Call-volume rate limit reached. Retry with backoff."),  # M
	80007: ("rate_limited", True, None, "WhatsApp Business Account rate limit reached. Retry with backoff."),  # V
	130429: ("rate_limited", True, None, "Cloud API throughput limit reached. Retry with backoff and smooth the send rate."),  # V
	131056: ("pair_rate_limited", True, PAIR_RATE_LIMIT_DELAY_SECONDS, "Too many messages to this same recipient too fast. Wait a few seconds; other recipients are unaffected."),  # V
	131050: ("recipient", False, None, "The recipient stopped marketing messages from this business. Do not retry; suppress them from marketing sends."),  # V
	# 135000: Meta's error-code page calls it a generic request-parameter error; Meta's pacing docs (and the
	# broadcast research) say held messages dropped by portfolio pacing fail with it. Treated as a pause signal.
	135000: ("pacing_dropped", False, None, "A held message was dropped (portfolio pacing / request error). Pause sending and review account notices in WhatsApp Manager."),  # U
	131049: ("rate_limited", False, 86400.0, "Meta limited marketing/engagement messages to this recipient. Wait at least 24 hours; do not retry automatically."),  # V
	# --- window / recipient
	131047: ("window_closed", False, None, "More than 24 hours since the customer's last message. Send an approved template message instead."),  # V
	131026: ("recipient", False, None, "Message undeliverable: the number is not on WhatsApp, has not accepted the terms, or runs an old client. Do not retry."),  # V
	131030: ("recipient", False, None, "Recipient is not in the allowed list (test numbers). Add the number in the Meta app or use a production number."),  # U
	131021: ("recipient", False, None, "The recipient is the same as the sender. Use a different recipient."),  # M
	130472: ("recipient", False, None, "The recipient number is part of a Meta experiment and cannot be messaged right now."),  # M
	# --- media
	131051: ("media", False, None, "Unsupported message type for this recipient or channel."),  # V
	131052: ("media", False, None, "Inbound media could not be downloaded (for example larger than 100 MB)."),  # V
	131053: ("media", False, None, "Media upload failed or the MIME type is not supported. Check the file type and size."),  # V
	# --- param
	131000: ("param", False, None, "Request rejected by Meta. Check the payload and try again later."),  # M (Meta text: something went wrong)
	131008: ("param", False, None, "A required parameter is missing from the request."),  # M
	131009: ("param", False, None, "A parameter value is invalid. Check the request payload."),  # V
	100: ("param", False, None, "Invalid parameter in the request. Check the payload (for example body over 4096 characters or a bad media id)."),  # V
	33: ("param", False, None, "The referenced object does not exist or is not accessible. Check the phone number id."),  # M
	# --- template
	132000: ("template", False, None, "Template parameter count does not match the template definition."),  # V
	132001: ("template", False, None, "Template does not exist in this language or is not approved."),  # V
	132005: ("template", False, None, "Translated template text is too long."),  # V
	132007: ("template", False, None, "Template content violates a WhatsApp policy. Edit and resubmit the template."),  # V
	132012: ("template", False, None, "Template parameter format does not match the definition."),  # V
	132015: ("template", False, None, "Template is paused for low quality. Edit it or wait for Meta to re-enable it."),  # V
	132016: ("template", False, None, "Template is disabled permanently. Create a new template."),  # V
	# --- server (retryable)
	1: ("server", True, None, "Meta reported an unknown API error. Retry later."),  # M
	2: ("server", True, None, "Meta service temporarily unavailable. Retry later."),  # M
	131016: ("server", True, None, "Meta service overloaded. Retry later."),  # M
	131057: ("server", True, None, "Account in maintenance mode. Retry later."),  # M
}

_HTTP_FALLBACK: dict[int, tuple[str, bool, str]] = {
	400: ("param", False, "Meta rejected the request as malformed."),
	401: ("auth", False, "Unauthorized. The access token is invalid or expired."),
	403: ("permission", False, "Forbidden. The token lacks permission for this action."),
	404: ("param", False, "Resource not found. Check the phone number id and API version."),
	408: ("timeout", True, "Request timed out. Retry with backoff."),
	429: ("rate_limited", True, "HTTP 429 from Meta. Retry with backoff."),
	504: ("timeout", True, "Gateway timeout from Meta. Retry with backoff."),
}

# ---------------------------------------------------------------- redaction

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=\-]+")
_KV_RE = re.compile(
	r"(?i)((?:access_token|refresh_token|client_secret|app_secret|appsecret_proof|authorization|token|signature)"
	r"[\"']?\s*[=:]\s*[\"']?)(?!\[redacted\])[^&\s\"',}]+"
)
_EAA_RE = re.compile(r"\bEAA[A-Za-z0-9]{8,}\b")


def redact(text: Any) -> str:
	"""Strip bearer/access tokens and token-bearing URLs from text."""
	s = "" if text is None else str(text)

	def url(m: re.Match) -> str:
		u = m.group(0)
		if "?" in u or "#" in u:
			return re.split(r"[?#]", u, maxsplit=1)[0] + "?[redacted]"
		return u

	s = _URL_RE.sub(url, s)
	s = _BEARER_RE.sub(r"\1[redacted]", s)
	s = _KV_RE.sub(r"\1[redacted]", s)
	s = _EAA_RE.sub("[redacted]", s)
	return s


# ---------------------------------------------------------------- normalisation


def _to_int(value: Any) -> int | None:
	try:
		if value is None or isinstance(value, bool):
			return None
		return int(value)
	except (TypeError, ValueError):
		return None


def _inner(body: Any) -> dict[str, Any]:
	"""Extract the Graph error object from many body shapes."""
	if isinstance(body, (bytes, bytearray)):
		try:
			body = body.decode("utf-8", "replace")
		except Exception:
			return {}
	if isinstance(body, str):
		try:
			parsed = json.loads(body)
		except Exception:
			return {}
		return _inner(parsed) if isinstance(parsed, (dict, list)) else {}
	if isinstance(body, list):
		return _inner(body[0]) if body else {}
	if not isinstance(body, dict):
		return {}
	if isinstance(body.get("error"), dict):
		return body["error"]
	if isinstance(body.get("errors"), list) and body["errors"]:
		return _inner(body["errors"][0])
	if "code" in body or "message" in body:
		return body
	return {}


def _response_body(resp: Any) -> Any:
	try:
		return resp.json()
	except Exception:
		pass
	text = getattr(resp, "text", None)
	return text if isinstance(text, (str, bytes)) else None


def _retry_after_header(resp: Any) -> float | None:
	try:
		headers = getattr(resp, "headers", None) or {}
		raw = headers.get("Retry-After") or headers.get("retry-after")
		val = float(raw)
		return val if val > 0 else None
	except Exception:
		return None


def _unpack(err: Any) -> tuple[int | None, dict[str, Any], str, float | None, str]:
	"""Return (http_status, inner_error, raw_text, retry_after_header, exc_name)."""
	status: int | None = None
	body: Any = None
	raw = ""
	header_hint: float | None = None
	exc_name = ""

	if err is None:
		return None, {}, "", None, ""
	if isinstance(err, (tuple, list)) and len(err) == 2 and (isinstance(err[0], int) or err[0] is None):
		status, body = _to_int(err[0]), err[1]
		raw = body if isinstance(body, str) else ""
	elif isinstance(err, BaseException):
		exc_name = type(err).__name__
		resp = getattr(err, "response", None)
		if resp is not None:
			status = _to_int(getattr(resp, "status_code", None))
			body = _response_body(resp)
			header_hint = _retry_after_header(resp)
		raw = str(err)
		if not body:
			body = raw
	elif hasattr(err, "status_code") and hasattr(err, "json"):
		status = _to_int(err.status_code)
		body = _response_body(err)
		header_hint = _retry_after_header(err)
		raw = getattr(err, "text", "") if isinstance(getattr(err, "text", ""), str) else ""
	elif isinstance(err, (dict, list)):
		body = err
		if isinstance(err, dict):
			status = _to_int(err.get("status_code") or err.get("http_status"))
	else:
		body = raw = err.decode("utf-8", "replace") if isinstance(err, (bytes, bytearray)) else str(err)

	inner = _inner(body)
	if not inner and isinstance(body, str):
		# graph_error_message style: "(131047) Re-engagement message ..."
		m = re.match(r"\s*\((\d{1,7})\)\s*(.*)", body, re.S)
		if m:
			inner = {"code": int(m.group(1)), "message": m.group(2)}
		else:
			m = re.search(r"HTTP\s+(\d{3})", body)
			if m and status is None:
				status = int(m.group(1))
	if not raw and isinstance(body, str):
		raw = body
	return status, inner, raw, header_hint, exc_name


def _lookup(code: int | None) -> tuple[str, bool, float | None, str] | None:
	if code is None:
		return None
	if code in _CODES:
		return _CODES[code]
	if 200 <= code <= 299:  # M: permission error range documented by Meta
		return ("permission", False, None, "A required permission is missing or was revoked. Re-grant the app permissions.")
	return None


def classify(err: Any) -> dict[str, Any]:
	"""Classify a Meta/Graph send error. Never raises."""
	try:
		return _classify(err)
	except Exception:
		return _result(None, None, "unknown", False, None, "Unclassified error.", None, redact(err)[:500], None)


def _result(code, subcode, kind, retryable, hint, operator_text, user_msg, message, http_status) -> dict[str, Any]:
	return {
		"code": code,
		"subcode": subcode,
		"kind": kind,
		"retryable": bool(retryable),
		"retry_after_hint": hint,
		"operator_text": operator_text,
		"user_msg": user_msg,
		"message": message,
		"http_status": http_status,
	}


def _classify(err: Any) -> dict[str, Any]:
	status, inner, raw, header_hint, exc_name = _unpack(err)
	code = _to_int(inner.get("code"))
	subcode = _to_int(inner.get("error_subcode"))

	user_msg = None
	for key in ("error_user_msg", "error_user_title", "title"):
		val = inner.get(key)
		if isinstance(val, str) and val.strip():
			user_msg = redact(val.strip())
			break

	details = (inner.get("error_data") or {}).get("details") if isinstance(inner.get("error_data"), dict) else None
	if inner:
		bits = [f"({code})" if code is not None else "", str(inner.get("message") or ""), str(details or "")]
		message = redact(" ".join(b for b in bits if b).strip())
	else:
		message = redact(raw if raw else (f"HTTP {status}" if status else ""))
	message = message[:500]

	entry = _lookup(code)
	if code == 100 and subcode is not None and 2388000 <= subcode < 2389000 and user_msg is None:
		user_msg = None  # subcode 2388xxx carries the user message in error_user_msg; keep None when absent
	if code == 190 or (code is None and subcode in (463, 467)):
		entry = _CODES[190]

	if entry is not None:
		kind, retryable, hint, text = entry
	else:
		low = f"{exc_name} {raw}".lower()
		if status in _HTTP_FALLBACK:
			kind, retryable, text = _HTTP_FALLBACK[status]
			hint = None
		elif status is not None and 500 <= status <= 599:
			kind, retryable, hint, text = "server", True, None, "Meta server error. Retry with backoff."
		elif "timeout" in exc_name.lower() or "timed out" in low or "timeout" in low:
			kind, retryable, hint, text = "timeout", True, None, "The request to Meta timed out. Retry with backoff."
		elif "connection" in exc_name.lower() or "connection" in low:
			kind, retryable, hint, text = "server", True, None, "Could not reach Meta. Retry with backoff."
		else:
			kind, retryable, hint, text = "unknown", False, None, "Unrecognised error. Check the message and Meta's error-code reference."

	if header_hint is not None and retryable:
		hint = header_hint
	if kind == "param" and code == 100 and user_msg:
		text = f"{text} Meta says: {user_msg}"
	return _result(code, subcode, kind, retryable, hint, text, user_msg, message, status)


# ---------------------------------------------------------------- retry policy


def is_informational(classification: Any) -> bool:
	"""True for expected codes (131060, 2593109) that must not alert or mark a delivery Failed."""
	try:
		return classification.get("kind") == "informational"
	except Exception:
		return False


def is_permanent(classification: dict[str, Any]) -> bool:
	"""True when retrying will not help (everything not marked retryable)."""
	try:
		return not bool(classification.get("retryable"))
	except Exception:
		return True


def backoff_seconds(kind: Any, attempt: int, rng: Any = None) -> float | None:
	"""Seconds to wait before retry number ``attempt`` (1-based), or None when permanent.

	``kind`` may be a kind string or a classification dict. 2, 4, 8, 16 s (capped) with
	+/-20 percent jitter; ``pair_rate_limited`` is a fixed 6 s. ``rng`` is an optional
	``random.Random`` for deterministic tests. A larger ``retry_after_hint`` on a
	classification dict (for example a Retry-After header) wins.
	"""
	hint = None
	if isinstance(kind, dict):
		if not kind.get("retryable"):
			return None
		hint = kind.get("retry_after_hint")
		kind = kind.get("kind")
	if kind == "pair_rate_limited":
		return PAIR_RATE_LIMIT_DELAY_SECONDS
	if kind not in ("rate_limited", "server", "timeout"):
		return None
	n = max(1, _to_int(attempt) or 1)
	base = min(BACKOFF_BASE_SECONDS * (2 ** (n - 1)), BACKOFF_CAP_SECONDS)
	r = rng if rng is not None else random
	delay = base * (1 + r.uniform(-BACKOFF_JITTER, BACKOFF_JITTER))
	if isinstance(hint, (int, float)) and hint > delay:
		delay = float(hint)
	return delay


def should_retry(classification: dict[str, Any], attempt: int, max_attempts: int = MAX_ATTEMPTS) -> bool:
	"""True when the error is retryable and ``attempt`` (1-based, attempts made) is below the cap."""
	return (not is_permanent(classification)) and attempt < max_attempts


# ---------------------------------------------------------------- broadcast helpers

# 132015 template paused, 132016 template disabled, 135000 pacing drop, 131042 payment problem.
_PAUSE_CODES = frozenset({132015, 132016, 135000, 131042})


def _code_of(x: Any) -> int | None:
	if isinstance(x, dict):
		return _to_int(x.get("code"))
	return _to_int(x)


def is_pause_signal(code: Any) -> bool:
	"""True when a broadcast should pause on this error (code int or classification dict)."""
	return _code_of(code) in _PAUSE_CODES


def should_defer_24h(code: Any) -> bool:
	"""True for 131049 (per-user marketing limit): reschedule at least 24h later, never retry sooner."""
	return _code_of(code) == 131049


def is_marketing_stop(code: Any) -> bool:
	"""True for 131050: the caller records a marketing stop consent for the recipient."""
	return _code_of(code) == 131050
