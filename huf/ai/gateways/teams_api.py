"""Microsoft Teams outbound client (T2): bot token + Bot Connector calls.

Everything is injectable (``http``, ``now``, ``sleep``); there are no hidden globals.

Security notes:
- The client secret and bearer tokens never appear in exception text, ``repr`` or logs.
  Error messages carry only HTTP status and a sanitised provider error code.
- Every outbound URL is built from a ``validate_service_url``-checked base (SSRF guard).
- The default HTTP transport never follows redirects (a redirect could leak the token).

``http`` contract: ``http(method, url, *, headers, json=None, data=None, timeout=10)`` returning an
object with ``status_code``, ``headers`` and ``json()``.

``token`` for the connector calls is either a plain string (a 401 then surfaces as an error) or a
provider callable ``provider(refresh: bool) -> str`` (see ``make_token_provider``); with a provider a
401 invalidates the cache, fetches a fresh token and retries exactly once.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlsplit

import frappe

from huf.ai.gateways.teams_contract import BOT_TOKEN_SCOPE, BOT_TOKEN_URL_TEMPLATE

logger = logging.getLogger(__name__)

ALLOWED_HOST_SUFFIXES = (".botframework.com", ".trafficmanager.net", ".teams.microsoft.com")
TOKEN_CACHE_PREFIX = "teams:token:"
TOKEN_EXPIRY_MARGIN = 300
MAX_RETRY_AFTER = 86400
TRANSIENT_RETRY_DELAY = 0.5
DEFAULT_TIMEOUT = 10

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
_TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,127}$")
_CODE_RE = re.compile(r"[^A-Za-z0-9_.:-]")


class TeamsApiError(Exception):
	"""Teams outbound failure. Text contains only status/code, never a secret or response body."""

	def __init__(self, status: int = 0, retry_after: float | None = None, code: str | None = None):
		self.status = int(status or 0)
		self.retry_after = retry_after
		self.code = _safe_code(code)
		suffix = f" code={self.code}" if self.code else ""
		super().__init__(f"teams api error: http {self.status}{suffix}")


def _safe_code(code: Any) -> str | None:
	if not code:
		return None
	return _CODE_RE.sub("", str(code))[:64] or None


def is_transient(error: BaseException) -> bool:
	"""True when the outbox (T6) should retry later: transport failures, 408, 429, 5xx."""
	if not isinstance(error, TeamsApiError):
		return False
	return error.status in (0, 408, 429) or error.status >= 500


# ---- SSRF guard ---------------------------------------------------------------------
def validate_service_url(url: str) -> str:
	"""Return the normalised service URL (https, allowlisted host, no trailing slash) or raise."""

	def bad() -> TeamsApiError:
		return TeamsApiError(0, code="invalid_service_url")

	if not isinstance(url, str) or not url or url != url.strip():
		raise bad()
	if any(ord(c) <= 0x20 or ord(c) >= 0x7F or c == "\\" for c in url):
		raise bad()
	try:
		parts = urlsplit(url)
		port = parts.port
	except ValueError:
		raise bad() from None
	if parts.scheme != "https" or parts.query or parts.fragment or "@" in parts.netloc:
		raise bad()
	if port not in (None, 443):
		raise bad()
	host = parts.hostname or ""
	if parts.netloc.endswith(":") or host != host.lower() and not host.isascii():
		raise bad()
	host = host.lower()
	if host.endswith(".") or not _HOST_RE.match(host):
		raise bad()
	try:
		ipaddress.ip_address(host)
		raise bad()
	except ValueError:
		pass
	if not host.endswith(ALLOWED_HOST_SUFFIXES):
		raise bad()
	segments = []
	for seg in parts.path.split("/"):
		if seg in ("..", "."):
			raise bad()
		if seg:
			if "%" in seg:
				raise bad()
			segments.append(seg)
	path = "/" + "/".join(segments) if segments else ""
	return f"https://{host}{path}"


# ---- HTTP ---------------------------------------------------------------------------
def _default_http(method: str, url: str, *, headers: dict, json=None, data=None, timeout=DEFAULT_TIMEOUT):
	import requests

	return requests.request(
		method, url, headers=headers, json=json, data=data, timeout=timeout, allow_redirects=False
	)


def _parse_retry_after(resp, now: Callable[[], float]) -> float | None:
	raw = (getattr(resp, "headers", None) or {}).get("Retry-After")
	if raw is None:
		raw = (getattr(resp, "headers", None) or {}).get("retry-after")
	if raw is None:
		return None
	raw = str(raw).strip()
	try:
		value = float(raw)
	except ValueError:
		try:
			value = parsedate_to_datetime(raw).timestamp() - now()
		except (TypeError, ValueError, IndexError):
			return None
	if value != value:  # NaN
		return None
	return max(0.0, min(value, MAX_RETRY_AFTER))


def _json_body(resp) -> dict:
	try:
		body = resp.json()
	except Exception:
		return {}
	return body if isinstance(body, dict) else {}


def _error_code(body: dict) -> str | None:
	err = body.get("error")
	if isinstance(err, dict):
		return err.get("code")
	if isinstance(err, str):
		return err
	return None


def _call(http, method, url, headers, *, json=None, data=None, timeout=DEFAULT_TIMEOUT):
	try:
		return http(method, url, headers=headers, json=json, data=data, timeout=timeout)
	except Exception as e:
		# Never chain/format the original: library messages may echo headers or bodies.
		raise TeamsApiError(0, code=f"transport_{type(e).__name__}") from None


def _raise_for_status(resp, now) -> None:
	status = getattr(resp, "status_code", 200)
	if status >= 400:
		raise TeamsApiError(status, _parse_retry_after(resp, now), _error_code(_json_body(resp)))


# ---- token --------------------------------------------------------------------------
def _cache():
	return frappe.cache()


def _cache_key(creds: Mapping, gateway_name: str | None) -> str:
	return f"{TOKEN_CACHE_PREFIX}{gateway_name or creds.get('app_id')}"


def get_bot_token(
	creds: Mapping,
	*,
	gateway_name: str | None = None,
	http: Callable | None = None,
	now: Callable[[], float] | None = None,
	sleep: Callable[[float], None] | None = None,
	refresh: bool = False,
) -> str:
	"""Client-credentials token for the Bot Connector, cached until ``expires_in - 300`` seconds."""
	now = now or time.time
	sleep = sleep or time.sleep
	http = http or _default_http
	app_id = creds.get("app_id")
	secret = creds.get("app_password")
	tenant_id = creds.get("tenant_id")
	if not (app_id and secret and tenant_id):
		raise TeamsApiError(0, code="missing_credentials")
	if not _TENANT_RE.match(str(tenant_id)):
		raise TeamsApiError(0, code="invalid_tenant_id")

	key = _cache_key(creds, gateway_name)
	if refresh:
		_cache().delete_value(key)
	else:
		cached = _cache().get_value(key)
		if isinstance(cached, dict) and cached.get("token") and cached.get("exp", 0) > now():
			return cached["token"]

	url = BOT_TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
	form = {
		"grant_type": "client_credentials",
		"client_id": app_id,
		"client_secret": secret,
		"scope": BOT_TOKEN_SCOPE,
	}
	headers = {"Content-Type": "application/x-www-form-urlencoded"}
	attempt = 0
	while True:
		try:
			resp = _call(http, "POST", url, headers, data=form)
			_raise_for_status(resp, now)
			break
		except TeamsApiError as e:
			if attempt == 0 and is_transient(e):
				attempt += 1
				sleep(min(e.retry_after, 5.0) if e.retry_after else TRANSIENT_RETRY_DELAY)
				continue
			raise
	body = _json_body(resp)
	token = body.get("access_token")
	if not token or not isinstance(token, str):
		raise TeamsApiError(getattr(resp, "status_code", 200), code="invalid_token_response")
	try:
		ttl = int(float(body.get("expires_in", 0))) - TOKEN_EXPIRY_MARGIN
	except (TypeError, ValueError):
		ttl = 0
	if ttl > 0:
		_cache().set_value(key, {"token": token, "exp": now() + ttl}, expires_in_sec=ttl)
	return token


def make_token_provider(
	creds: Mapping,
	*,
	gateway_name: str | None = None,
	http: Callable | None = None,
	now: Callable[[], float] | None = None,
	sleep: Callable[[float], None] | None = None,
) -> Callable[..., str]:
	"""Return ``provider(refresh=False) -> token`` for the connector calls (enables 401 re-token)."""

	def provider(refresh: bool = False) -> str:
		return get_bot_token(
			creds, gateway_name=gateway_name, http=http, now=now, sleep=sleep, refresh=refresh
		)

	return provider


# ---- connector ----------------------------------------------------------------------
def _request(method, url, token, payload, *, http, now, sleep) -> dict:
	http = http or _default_http
	now = now or time.time
	sleep = sleep or time.sleep
	refreshed = False
	transient_retried = False
	while True:
		tok = token(refresh=refreshed) if callable(token) else token
		headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=utf-8"}
		resp = _call(http, method, url, headers, json=payload)
		status = getattr(resp, "status_code", 200)
		if status == 401 and callable(token) and not refreshed:
			refreshed = True
			continue
		try:
			_raise_for_status(resp, now)
		except TeamsApiError as e:
			# One quick retry only for connection-level failures / 5xx without a Retry-After hint;
			# 429 and the rest are left to the outbox (T6).
			if not transient_retried and e.status in (0, 500, 502, 503, 504) and e.retry_after is None:
				transient_retried = True
				sleep(TRANSIENT_RETRY_DELAY)
				continue
			raise
		return _json_body(resp)


def _require_id(body: dict, status: int = 200) -> dict:
	if not body.get("id") or not isinstance(body.get("id"), str):
		raise TeamsApiError(status, code="missing_activity_id")
	return body


def _q(value: str) -> str:
	return quote(str(value), safe="")


def post_activity(
	service_url: str,
	conversation_id: str,
	activity: dict,
	*,
	token,
	http: Callable | None = None,
	now: Callable[[], float] | None = None,
	sleep: Callable[[float], None] | None = None,
) -> dict:
	base = validate_service_url(service_url)
	url = f"{base}/v3/conversations/{_q(conversation_id)}/activities"
	return _require_id(_request("POST", url, token, activity, http=http, now=now, sleep=sleep))


def update_activity(
	service_url: str,
	conversation_id: str,
	activity_id: str,
	activity: dict,
	*,
	token,
	http: Callable | None = None,
	now: Callable[[], float] | None = None,
	sleep: Callable[[float], None] | None = None,
) -> dict:
	base = validate_service_url(service_url)
	url = f"{base}/v3/conversations/{_q(conversation_id)}/activities/{_q(activity_id)}"
	return _request("PUT", url, token, activity, http=http, now=now, sleep=sleep)


def create_personal_conversation(
	service_url: str,
	tenant_id: str,
	bot_id: str,
	user_aad_id: str,
	*,
	token,
	http: Callable | None = None,
	now: Callable[[], float] | None = None,
	sleep: Callable[[float], None] | None = None,
) -> str:
	base = validate_service_url(service_url)
	payload = {
		"bot": {"id": bot_id},
		"isGroup": False,
		"members": [{"id": user_aad_id}],
		"tenantId": tenant_id,
		"channelData": {"tenant": {"id": tenant_id}},
	}
	body = _require_id(_request("POST", f"{base}/v3/conversations", token, payload, http=http, now=now, sleep=sleep))
	return body["id"]
