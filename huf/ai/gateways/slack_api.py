"""Shared Slack Web API helper (S0).

Thin, dependency-injected wrapper around https://slack.com/api/<method>.

Security notes:
- The bot token is never included in exception text, ``repr(api)`` or logs.
- A user token (``xoxp-``) is a RISK (it can read far more than the bot, e.g. search.messages).
  ``inspect_token`` reports ``token_kind``; callers (setup wizard, gateway save) should REJECT
  anything that is not ``"bot"``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

API_BASE = "https://slack.com/api/"
MAX_PAGES = 20
MAX_RETRY_AFTER = 30

REQUIRED_BOT_SCOPES = [
	"chat:write",
	"app_mentions:read",
	"channels:history",
	"groups:history",
	"im:history",
	"mpim:history",
	"users:read",
	"users:read.email",
	"im:write",
	"reactions:write",
	"channels:read",
	"groups:read",
	"mpim:read",
]


class SlackApiError(Exception):
	"""Slack API failure. Message contains only method/code/status, never the token."""

	def __init__(self, method: str, error_code: str, status: int = 200):
		self.method = method
		self.error_code = error_code
		self.status = status
		super().__init__(f"slack {method} failed: {error_code} (http {status})")


def _default_http(url: str, *, headers: dict, data=None, json=None, timeout=10):
	import requests

	return requests.post(url, headers=headers, data=data, json=json, timeout=timeout)


def _clean(params: dict) -> dict:
	return {k: v for k, v in params.items() if v is not None}


class SlackApi:
	def __init__(self, token: str, *, http: Callable | None = None, timeout: int = 10,
		sleep: Callable[[float], None] = time.sleep):
		self._token = token or ""
		self._http = http or _default_http
		self._timeout = timeout
		self._sleep = sleep
		self.last_headers: dict = {}

	def __repr__(self) -> str:
		return "<SlackApi token=***>"

	__str__ = __repr__

	# ---- core -------------------------------------------------------------
	def _send(self, method: str, params: dict, as_json: bool):
		headers = {"Authorization": f"Bearer {self._token}"}
		url = API_BASE + method
		try:
			if as_json:
				headers["Content-Type"] = "application/json; charset=utf-8"
				return self._http(url, headers=headers, json=params, timeout=self._timeout)
			return self._http(url, headers=headers, data=params, timeout=self._timeout)
		except SlackApiError:
			raise
		except Exception as e:
			# Do not chain/format the original: library messages may echo headers.
			raise SlackApiError(method, f"transport_error:{type(e).__name__}", 0) from None

	@staticmethod
	def _retry_after(resp) -> float:
		try:
			val = float((getattr(resp, "headers", None) or {}).get("Retry-After", 1))
		except (TypeError, ValueError):
			val = 1.0
		return max(0.0, min(val, MAX_RETRY_AFTER))

	def call(self, method: str, *, as_json: bool = False, **params) -> dict:
		params = _clean(params)
		retried = False
		while True:
			resp = self._send(method, params, as_json)
			status = getattr(resp, "status_code", 200)
			self.last_headers = dict(getattr(resp, "headers", None) or {})
			if status == 429:
				if retried:
					raise SlackApiError(method, "ratelimited", 429)
				retried = True
				self._sleep(self._retry_after(resp))
				continue
			if status >= 400:
				raise SlackApiError(method, f"http_{status}", status)
			try:
				body = resp.json()
			except Exception:
				raise SlackApiError(method, "invalid_json", status) from None
			if not isinstance(body, dict):
				raise SlackApiError(method, "invalid_json", status)
			if not body.get("ok"):
				code = str(body.get("error") or "unknown_error")
				if code == "ratelimited" and not retried:
					retried = True
					self._sleep(self._retry_after(resp))
					continue
				raise SlackApiError(method, code, status)
			return body

	def paginate(self, method: str, key: str, *, max_pages: int = MAX_PAGES, **params) -> Iterator[Any]:
		"""Yield items of ``key`` across cursor pages, stopping after ``max_pages`` pages."""
		cursor = params.pop("cursor", None)
		for _ in range(max(1, max_pages)):
			body = self.call(method, cursor=cursor, **params)
			yield from body.get(key) or []
			cursor = (body.get("response_metadata") or {}).get("next_cursor")
			if not cursor:
				return

	# ---- methods ----------------------------------------------------------
	def auth_test(self) -> dict:
		return self.call("auth.test")

	def users_info(self, user_id: str) -> dict:
		"""Return a normalized user dict (id, team_id, is_bot, restricted flags, deleted, email)."""
		u = self.call("users.info", user=user_id).get("user") or {}
		out = {
			"id": u.get("id"),
			"team_id": u.get("team_id"),
			"is_bot": bool(u.get("is_bot")),
			"is_restricted": bool(u.get("is_restricted")),
			"is_ultra_restricted": bool(u.get("is_ultra_restricted")),
			"deleted": bool(u.get("deleted")),
		}
		email = (u.get("profile") or {}).get("email")
		if email:
			out["profile"] = {"email": email}
		return out

	def users_list(self, cursor: str | None = None, limit: int = 200) -> dict:
		return self.call("users.list", cursor=cursor, limit=limit)

	def conversations_list(self, types: str = "public_channel", cursor: str | None = None,
		limit: int = 200) -> dict:
		return self.call("conversations.list", types=types, cursor=cursor, limit=limit)

	def conversations_open(self, users: list[str]) -> str:
		body = self.call("conversations.open", users=",".join(users))
		return (body.get("channel") or {}).get("id")

	@staticmethod
	def _content(payload: dict, text, blocks) -> dict:
		payload["text"] = text
		payload["blocks"] = blocks
		return payload

	def post_message(self, channel: str, text: str | None = None, blocks: list | None = None,
		thread_ts: str | None = None, unfurl: bool = False) -> dict:
		p = self._content({"channel": channel, "thread_ts": thread_ts,
			"unfurl_links": unfurl, "unfurl_media": unfurl}, text, blocks)
		return self.call("chat.postMessage", as_json=True, **p)

	def post_ephemeral(self, channel: str, user: str, text: str | None = None,
		blocks: list | None = None, thread_ts: str | None = None) -> dict:
		p = self._content({"channel": channel, "user": user, "thread_ts": thread_ts}, text, blocks)
		return self.call("chat.postEphemeral", as_json=True, **p)

	def update_message(self, channel: str, ts: str, text: str | None = None,
		blocks: list | None = None) -> dict:
		p = self._content({"channel": channel, "ts": ts}, text, blocks)
		return self.call("chat.update", as_json=True, **p)

	def add_reaction(self, channel: str, ts: str, name: str) -> dict:
		return self.call("reactions.add", channel=channel, timestamp=ts, name=name)

	def remove_reaction(self, channel: str, ts: str, name: str) -> dict:
		return self.call("reactions.remove", channel=channel, timestamp=ts, name=name)

	def permalink(self, channel: str, ts: str) -> str:
		return self.call("chat.getPermalink", channel=channel, message_ts=ts).get("permalink")


def token_kind(token: str) -> str:
	t = token or ""
	if t.startswith("xoxb-"):
		return "bot"
	if t.startswith("xoxp-"):
		return "user"
	return "unknown"


def parse_scopes(header: str | None) -> list[str]:
	return [s.strip() for s in (header or "").split(",") if s.strip()]


def missing_scopes(granted: list[str], required: list[str] | None = None) -> list[str]:
	have = set(granted or [])
	return [s for s in (REQUIRED_BOT_SCOPES if required is None else required) if s not in have]


def inspect_token(api: SlackApi) -> dict:
	"""auth.test + scope/kind introspection. Callers must reject token_kind != "bot"."""
	body = api.auth_test()
	headers = {str(k).lower(): v for k, v in (api.last_headers or {}).items()}
	granted = parse_scopes(headers.get("x-oauth-scopes"))
	return {
		"bot_user_id": body.get("user_id"),
		"team_id": body.get("team_id"),
		"team": body.get("team"),
		"url": body.get("url"),
		"token_kind": token_kind(api._token),
		"granted_scopes": granted,
		"missing_scopes": missing_scopes(granted),
	}
