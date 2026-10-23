"""In-memory fake Telegram Bot API for adapter tests (implements injected http_post / http_get)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "telegram"
TOKEN = "123456:ABCdefGhIJKlmNoPQRsTUVwxyZ"
SECRET = "shh-secret"


def load_fixture(name: str) -> dict:
	return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


class FakeResponse:
	def __init__(self, body: Any = None, status_code: int = 200, content: bytes | None = None) -> None:
		self.body = body
		self.status_code = status_code
		self.content = content

	def json(self) -> Any:
		return self.body

	def raise_for_status(self) -> None:
		if self.status_code >= 400:
			raise RuntimeError(f"HTTP {self.status_code}")


class FakeBotApi:
	"""Records every call; replies ``ok`` with an incrementing message_id unless a reply is queued.

	``queue(method, *responses)`` queues bodies (dicts) or callables(payload) -> body consumed in order;
	``error(description, error_code, retry_after=None)`` builds a Bot API error body.
	"""

	def __init__(self) -> None:
		self.calls: list[dict[str, Any]] = []
		self.gets: list[str] = []
		self._queues: dict[str, list[Any]] = {}
		self._next_id = 100
		self.file_bytes = b"file-bytes"

	@staticmethod
	def error(description: str, error_code: int, retry_after: int | None = None) -> dict:
		body: dict[str, Any] = {"ok": False, "error_code": error_code, "description": description}
		if retry_after is not None:
			body["parameters"] = {"retry_after": retry_after}
		return body

	def queue(self, method: str, *responses: Any) -> None:
		self._queues.setdefault(method, []).extend(responses)

	def of(self, method: str) -> list[dict[str, Any]]:
		return [c for c in self.calls if c["method"] == method]

	def last(self, method: str | None = None) -> dict[str, Any]:
		items = self.of(method) if method else self.calls
		return items[-1]

	def http_post(
		self,
		url: str,
		*,
		json_data: Mapping[str, Any] | None = None,
		data: Mapping[str, Any] | None = None,
		files: Mapping[str, Any] | None = None,
		timeout: int | None = None,
	) -> FakeResponse:
		method = url.rsplit("/", 1)[-1]
		payload = dict(json_data if json_data is not None else (data or {}))
		self.calls.append(
			{"method": method, "payload": payload, "files": dict(files) if files else None, "url": url}
		)
		queued = self._queues.get(method)
		if queued:
			body = queued.pop(0)
			body = body(payload) if callable(body) else body
			return FakeResponse(body, status_code=body.get("error_code", 200) if not body.get("ok") else 200)
		if method == "getFile":
			return FakeResponse(
				{"ok": True, "result": {"file_id": payload.get("file_id"), "file_path": "photos/f.jpg"}}
			)
		if method.startswith("send"):
			self._next_id += 1
			if method == "sendMediaGroup":
				return FakeResponse(
					{"ok": True, "result": [{"message_id": self._next_id}, {"message_id": self._next_id + 1}]}
				)
			return FakeResponse(
				{"ok": True, "result": {"message_id": self._next_id, "chat": {"id": payload.get("chat_id")}}}
			)
		if method == "getWebhookInfo":
			return FakeResponse({"ok": True, "result": {"url": "https://x/h", "pending_update_count": 0}})
		return FakeResponse({"ok": True, "result": True})

	def http_get(self, url: str, *, timeout: int | None = None) -> FakeResponse:
		self.gets.append(url)
		return FakeResponse(content=self.file_bytes)


# -- isolation helpers (tests must behave the same in the unit runner and on a real site with redis) --


def set_local_flags(testcase, **values) -> None:
	"""Give ``frappe.local.flags`` a complete ``frappe._dict`` for the test, then restore exactly what was there.

	``patch.object(frappe.local, "flags", ..., create=True)`` is unsafe: on a site the attribute lives on the
	werkzeug-style proxy, so mock deletes it on exit and later frappe code raises ``AttributeError: flags``.
	"""
	import frappe

	missing = object()
	old = getattr(frappe.local, "flags", missing)
	new = frappe._dict(old) if old is not missing and old else frappe._dict()
	new.update(values)
	frappe.local.flags = new

	def restore():
		if old is missing:
			try:
				del frappe.local.flags
			except Exception:
				pass
		else:
			frappe.local.flags = old

	testcase.addCleanup(restore)


def clear_update_dedup() -> None:
	"""Drop persisted ``huf_tg_upd:*`` update-id claims from a real redis cache (no-op without a site cache)."""
	try:
		import frappe

		if not getattr(frappe.local, "site", None):
			return
		cache = frappe.cache() if callable(frappe.cache) else frappe.cache
		cache.delete_keys("huf_tg_upd:*")
	except Exception:
		pass


def isolate_update_dedup(testcase) -> None:
	clear_update_dedup()
	testcase.addCleanup(clear_update_dedup)


def isolate_admin_cache(testcase, admin_module, cache) -> None:
	"""Route ``telegram_admin`` rate-limit / nonce / session state to ``cache`` instead of the site's redis."""
	from unittest.mock import patch

	p = patch.object(admin_module, "_cache", lambda c=None: c if c is not None else cache)
	p.start()
	testcase.addCleanup(p.stop)
