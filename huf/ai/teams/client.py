"""Outbound Teams (Bot Connector) sends.

Routing: a reply is addressed from the stored conversation reference (``refs.get_reference``), keyed by
``app_id`` + ``conversation_id``; the Gateway name (for the Gateway Event fallback) arrives through the
generic ``adapter_context`` provider hook as ``gateway_context={"gateway_name": ...}``.

Error taxonomy (core convention, see ``provider_hooks`` ``send_errors``):

- ``TeamsPermanentError`` (registered as the Teams ``send_errors`` type): operator/user-fixable; the event
  fails cleanly with no retry (missing reference, bad credentials, other 4xx, partial multi-part delivery).
- ``TeamsTransientError``: retries exhausted (429/412/502/504/network/token 5xx); propagates so the job
  queue / dead-letter policy may retry later.

Tokens and the app password never appear in logs, exceptions or return values.
"""

from __future__ import annotations

import email.utils
import hashlib
import json
import random
import re
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote

from huf.ai.gateway_adapters.types import GatewayReply, OutboundDelivery
from huf.ai.teams import refs

# Module-level only (tests override); never derived from request data.
_AUTHORITY_BASE = "https://login.microsoftonline.com"
_SCOPE = "https://api.botframework.com/.default"
_TIMEOUT = (3.05, 10)
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1.0
_BACKOFF_CAP = 20.0
_RETRY_STATUSES = frozenset({429, 412, 502, 504})
_TOKEN_SKEW = 300
TARGET_BYTES = 80 * 1024
HARD_LIMIT_BYTES = 100 * 1024
_TOKEN_CACHE_PREFIX = "huf_teams_token:"

_now: Callable[[], float] = time.time
_sleep: Callable[[float], None] = time.sleep
_tokens: dict[tuple[str, str], tuple[str, float]] = {}
_tokens_lock = threading.Lock()


class TeamsSendError(Exception):
	"""Base class for Teams delivery failures. Messages never contain secrets or tokens."""

	retryable = False

	def __init__(self, message: str, *, status: int | None = None, delivered_ids: tuple[str, ...] = ()):
		super().__init__(message)
		self.status = status
		self.delivered_ids = delivered_ids


class TeamsPermanentError(TeamsSendError):
	"""Not sendable without operator/user action; do not retry."""


class TeamsAuthError(TeamsPermanentError):
	"""Token acquisition rejected (wrong tenant / app id / secret)."""


class TeamsTransientError(TeamsSendError):
	"""Retries exhausted on a transient condition; a later retry may succeed."""

	retryable = True


def send_errors() -> tuple[type[BaseException], ...]:
	return (TeamsPermanentError,)


def error_text(exc: BaseException) -> str:
	return str(exc) if isinstance(exc, TeamsSendError) else "Microsoft Teams delivery failed"


def register_hooks(provider_hooks: Any, provider: str) -> None:
	"""Register the outbound provider hooks (called from ``huf.ai.teams.hooks``)."""
	provider_hooks.register(
		provider, "adapter_context", lambda gateway, _contact="": {"gateway_name": gateway.name}
	)
	provider_hooks.register(provider, "send_errors", send_errors)
	provider_hooks.register(provider, "error_text", error_text)


# -- transport -------------------------------------------------------------------------------------------

Transport = Callable[..., tuple[int, Mapping[str, str], Any]]


def _requests_transport(
	method: str,
	url: str,
	*,
	headers: Mapping[str, str],
	data: Any = None,
	json_body: Any = None,
	timeout: Any,
) -> tuple[int, Mapping[str, str], Any]:
	import requests

	response = requests.request(
		method, url, headers=dict(headers), data=data, json=json_body, timeout=timeout, allow_redirects=False
	)
	try:
		body = response.json() if response.content else None
	except ValueError:
		body = None
	return response.status_code, response.headers, body


def _call(transport: Transport, method: str, url: str, **kw: Any) -> tuple[int, Mapping[str, str], Any]:
	try:
		return transport(method, url, timeout=_TIMEOUT, **kw)
	except TeamsSendError:
		raise
	except Exception as exc:
		# Exception text may echo URLs or headers; report only the type.
		raise TeamsTransientError(f"Microsoft Teams request failed ({type(exc).__name__})") from None


def _safe_code(body: Any) -> str:
	"""A short machine code from an error body (never free text, which could echo request data)."""
	code: Any = ""
	if isinstance(body, dict):
		err = body.get("error")
		code = err.get("code") if isinstance(err, dict) else err
		aadsts = re.search(r"AADSTS\d{4,8}", str(body.get("error_description") or ""))
		if aadsts:
			code = f"{code or 'error'} {aadsts.group(0)}"
	code = re.sub(r"[^A-Za-z0-9_. -]", "", str(code or ""))[:80]
	return f" ({code})" if code else ""


# -- token -----------------------------------------------------------------------------------------------


def _token_cache_key(tenant_id: str, app_id: str) -> str:
	return _TOKEN_CACHE_PREFIX + hashlib.sha256(f"{tenant_id}\x00{app_id}".encode()).hexdigest()


def _redis() -> Any:
	try:
		import frappe

		return frappe.cache
	except Exception:
		return None


def clear_token_cache(tenant_id: str | None = None, app_id: str | None = None) -> None:
	"""Drop cached tokens for one (tenant, app) or, with no arguments, every in-process one."""
	with _tokens_lock:
		keys = [(tenant_id, app_id or "")] if tenant_id is not None else list(_tokens)
		for key in keys:
			_tokens.pop(key, None)
	cache = _redis()
	for tenant, app in keys:
		try:
			cache.delete_value(_token_cache_key(tenant, app))
		except Exception:
			pass


def get_token(credentials: Mapping[str, str], transport: Transport | None = None) -> str:
	"""Bot Framework access token (client_credentials, tenant authority), cached until exp - 5 min."""
	transport = transport or _requests_transport
	key = (str(credentials["tenant_id"]), str(credentials["app_id"]))
	now = _now()
	with _tokens_lock:
		hit = _tokens.get(key)
	if hit and hit[1] - _TOKEN_SKEW > now:
		return hit[0]
	cache = _redis()
	try:
		stored = cache.get_value(_token_cache_key(*key))
	except Exception:
		stored = None
	if isinstance(stored, dict) and stored.get("t") and float(stored.get("exp") or 0) - _TOKEN_SKEW > now:
		with _tokens_lock:
			_tokens[key] = (stored["t"], float(stored["exp"]))
		return stored["t"]

	url = f"{_AUTHORITY_BASE}/{quote(key[0], safe='')}/oauth2/v2.0/token"
	status, _headers, body = _call(
		transport,
		"POST",
		url,
		headers={"Content-Type": "application/x-www-form-urlencoded"},
		data={
			"grant_type": "client_credentials",
			"client_id": key[1],
			"client_secret": credentials["app_password"],
			"scope": _SCOPE,
		},
	)
	if status in (400, 401, 403):
		raise TeamsAuthError(
			f"Microsoft Teams token request was rejected (HTTP {status}){_safe_code(body)}: check the App ID, "
			"client secret value and tenant ID of the single-tenant bot registration",
			status=status,
		)
	if not 200 <= status < 300:
		raise TeamsTransientError(f"Microsoft Teams token request failed (HTTP {status})", status=status)
	token = body.get("access_token") if isinstance(body, dict) else None
	if not token:
		raise TeamsTransientError("Microsoft Teams token response had no access token", status=status)
	try:
		expires_in = float(body.get("expires_in") or 3600)
	except (TypeError, ValueError):
		expires_in = 3600.0
	exp = now + expires_in
	with _tokens_lock:
		_tokens[key] = (token, exp)
	try:
		cache.set_value(_token_cache_key(*key), {"t": token, "exp": exp}, expires_in_sec=int(expires_in))
	except Exception:
		pass
	return token


# -- activity sizing -------------------------------------------------------------------------------------


def activity_size(activity: Mapping[str, Any]) -> int:
	"""Serialized size as Teams counts it (UTF-16), including JSON escaping."""
	return len(json.dumps(activity, ensure_ascii=False).encode("utf-16-le"))


_SEPARATORS = (r"\n[ \t]*\n", r"\n", r"(?<=[.!?])\s+")


def split_text(text: str, fits: Callable[[str], bool], level: int = 0) -> list[str]:
	"""Ordered chunks that each ``fits``: paragraphs first, then lines, sentences, then characters."""
	if fits(text):
		return [text] if text.strip() else []
	if level >= len(_SEPARATORS):
		return _hard_split(text, fits)
	pieces = re.split(f"({_SEPARATORS[level]})", text)
	out: list[str] = []
	current = ""
	for i in range(0, len(pieces), 2):
		piece = pieces[i]
		candidate = current + pieces[i - 1] + piece if current else piece
		if fits(candidate):
			current = candidate
			continue
		if current.strip():
			out.append(current.strip())
		if fits(piece):
			current = piece
		else:
			out.extend(split_text(piece, fits, level + 1))
			current = ""
	if current.strip():
		out.append(current.strip())
	return out


def _hard_split(text: str, fits: Callable[[str], bool]) -> list[str]:
	out: list[str] = []
	while text:
		lo, hi = 1, len(text)
		while lo < hi:
			mid = (lo + hi + 1) // 2
			if fits(text[:mid]):
				lo = mid
			else:
				hi = mid - 1
		if not fits(text[:lo]):
			raise TeamsPermanentError("Microsoft Teams message envelope exceeds the size limit")
		out.append(text[:lo])
		text = text[lo:]
	return [c for c in out if c.strip()]


# -- send ------------------------------------------------------------------------------------------------


def _retry_delay(attempt: int, headers: Mapping[str, str]) -> float:
	retry_after = next((str(v).strip() for k, v in (headers or {}).items() if k.lower() == "retry-after"), "")
	if retry_after:
		try:
			return min(max(float(retry_after), 0.0), _BACKOFF_CAP)
		except ValueError:
			try:
				when = email.utils.parsedate_to_datetime(retry_after)
				return min(max(when.timestamp() - _now(), 0.0), _BACKOFF_CAP)
			except (TypeError, ValueError):
				pass
	return min(_BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 0.5), _BACKOFF_CAP)


def _post_activity(
	url: str, activity: dict[str, Any], credentials: Mapping[str, str], transport: Transport
) -> str:
	refreshed = False
	attempt = 0
	while True:
		attempt += 1
		token = get_token(credentials, transport)
		status, headers, body = _call(
			transport,
			"POST",
			url,
			headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
			json_body=activity,
		)
		if 200 <= status < 300:
			activity_id = body.get("id") if isinstance(body, dict) else None
			if not activity_id:
				raise TeamsPermanentError(
					"Microsoft Teams accepted the message but returned no activity id", status=status
				)
			return str(activity_id)
		if status in (401, 403) and not refreshed:
			# A cached token may be stale (secret rotated): drop it and retry exactly once.
			refreshed = True
			attempt -= 1
			clear_token_cache(str(credentials["tenant_id"]), str(credentials["app_id"]))
			continue
		if status in _RETRY_STATUSES:
			if attempt >= _MAX_ATTEMPTS:
				raise TeamsTransientError(
					f"Microsoft Teams send failed after {attempt} attempts (HTTP {status})", status=status
				)
			_sleep(_retry_delay(attempt, headers))
			continue
		hint = ""
		if status in (401, 403):
			hint = ": the bot is not authorised for this conversation (uninstalled, blocked or wrong tenant)"
		elif status == 404:
			hint = ": conversation not found; the stored reference may be stale"
		elif 300 <= status < 400:
			hint = ": redirects are not followed"
		raise TeamsPermanentError(
			f"Microsoft Teams send rejected (HTTP {status}){_safe_code(body)}{hint}", status=status
		)


def send_reply(
	reply: GatewayReply,
	credentials: Mapping[str, str],
	*,
	gateway_name: str = "",
	transport: Transport | None = None,
) -> OutboundDelivery:
	"""Send ``reply.text`` via the conversation's stored reference; large text becomes several messages."""
	transport = transport or _requests_transport
	app_id = str(credentials["app_id"])
	reference = refs.get_reference(gateway_name, app_id, reply.conversation_id)
	if not reference:
		raise TeamsPermanentError(
			"No Microsoft Teams conversation reference is stored for this conversation: the user must "
			"message the bot first (Teams only allows replies to conversations the bot has seen)"
		)
	try:
		service_url = refs.validate_service_url(reference.get("serviceUrl"))
	except ValueError as exc:
		raise TeamsPermanentError(f"Stored Teams reference rejected: {exc}") from None

	conversation_id = reply.conversation_id
	url = f"{service_url}/v3/conversations/{quote(conversation_id, safe='')}/activities"
	base: dict[str, Any] = {
		"type": "message",
		"textFormat": "markdown",
		"from": {"id": reference.get("bot_id") or f"28:{app_id}"},
		"conversation": {"id": conversation_id},
	}
	if reply.reply_to_provider_message_id:
		url += f"/{quote(str(reply.reply_to_provider_message_id), safe='')}"
		base["replyToId"] = str(reply.reply_to_provider_message_id)

	chunks = split_text(reply.text, lambda c: activity_size({**base, "text": c}) <= TARGET_BYTES) or [
		reply.text
	]
	delivered: list[str] = []
	for chunk in chunks:
		activity = {**base, "text": chunk}
		if activity_size(activity) > HARD_LIMIT_BYTES:
			raise TeamsPermanentError("Microsoft Teams message exceeds the 100 KB limit")
		try:
			delivered.append(_post_activity(url, activity, credentials, transport))
		except TeamsSendError as exc:
			if delivered:
				# Retrying the whole reply would duplicate the parts the user already sees.
				raise TeamsPermanentError(
					f"Microsoft Teams reply partially delivered ({len(delivered)}/{len(chunks)} parts): {exc}",
					status=exc.status,
					delivered_ids=tuple(delivered),
				) from None
			raise
	return OutboundDelivery(delivered[0], provider_response={"activity_ids": delivered, "parts": len(chunks)})
