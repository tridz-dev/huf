#!/usr/bin/env python3
"""Read-only live smoke check for a WhatsApp access token.

Reads WA_TOKEN and WA_PHONE_ID from the environment, asks Meta's ``debug_token``
endpoint whether the token is still valid, and prints exactly one of:

    token valid until <YYYY-MM-DD>
    token valid (no expiry)
    token invalid

Nothing is sent to WhatsApp: the only request is the read-only token debug call.
Neither the token nor the phone number id is ever printed, and transport errors
are collapsed to ``token invalid`` so URLs, query strings and exception text
cannot leak the credential.

The phone number id is required as an operator guard so the person running the
smoke confirms which number they are checking; it is not needed by the Graph
call and is never transmitted or displayed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

GRAPH_VERSION = "v22.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
DEBUG_TOKEN_URL = f"{GRAPH_BASE}/debug_token"
TIMEOUT_SECONDS = 15

MSG_INVALID = "token invalid"
MSG_VALID_UNTIL = "token valid until {date}"
MSG_VALID_NO_EXPIRY = "token valid (no expiry)"

_NUMERIC_RE = re.compile(r"^\d+$")

HttpGet = Callable[..., tuple[int, dict]]


def default_http_get(url: str, params: dict, timeout: int = TIMEOUT_SECONDS) -> tuple[int, dict]:
	"""GET ``url`` with ``params`` and return ``(status, json)``; never echoes the URL."""
	query = urllib.parse.urlencode(params)
	request = urllib.request.Request(  # noqa: S310 - constant HTTPS Graph endpoint
		f"{url}?{query}", headers={"Accept": "application/json"}, method="GET"
	)
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - constant HTTPS endpoint
			body = response.read().decode("utf-8", errors="replace")
			return int(response.status), json.loads(body or "{}")
	except urllib.error.HTTPError as exc:
		raw = exc.read().decode("utf-8", errors="replace")
		try:
			return int(exc.code), json.loads(raw or "{}")
		except ValueError:
			return int(exc.code), {}
	except Exception:  # noqa: BLE001 - any failure means the token could not be confirmed
		# Timeouts, DNS failures and TLS errors are reported as an invalid token,
		# never re-raised: exception text can contain the token-bearing URL.
		return 0, {}


def _format_expiry(expires_at: Any) -> str:
	"""Return the success line for a valid token, or an empty string if unparseable."""
	if expires_at in (0, "0", None, ""):
		return MSG_VALID_NO_EXPIRY
	try:
		timestamp = int(expires_at)
	except (TypeError, ValueError):
		return ""
	if timestamp <= 0:
		return MSG_VALID_NO_EXPIRY
	return MSG_VALID_UNTIL.format(date=datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat())


def check_token(token: str, http_get: HttpGet | None = None) -> str:
	"""Return the one-line, non-secret verdict for ``token`` (``WA_PHONE_ID`` is not sent)."""
	if not token:
		return MSG_INVALID
	get = http_get or default_http_get
	try:
		status, payload = get(DEBUG_TOKEN_URL, {"input_token": token, "access_token": token})
	except Exception:  # noqa: BLE001 - injected transports must not leak or crash the CLI
		return MSG_INVALID
	data = payload.get("data") if isinstance(payload, dict) else None
	if status != 200 or not isinstance(data, dict) or data.get("is_valid") is not True:
		return MSG_INVALID
	return _format_expiry(data.get("expires_at")) or MSG_INVALID


def main(env: dict | None = None, http_get: HttpGet | None = None) -> int:
	env = os.environ if env is None else env
	token = (env.get("WA_TOKEN") or "").strip()
	phone_id = (env.get("WA_PHONE_ID") or "").strip()
	if not token:
		print("WA_TOKEN is not set", file=sys.stderr)
		return 2
	if not phone_id or not _NUMERIC_RE.match(phone_id):
		print("WA_PHONE_ID is not set or is not numeric", file=sys.stderr)
		return 2
	verdict = check_token(token, http_get=http_get)
	print(verdict)
	return 0 if verdict != MSG_INVALID else 1


if __name__ == "__main__":
	raise SystemExit(main())
