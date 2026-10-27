"""Unit tests for the Slack Events inbound handler (huf/ai/gateways/slack_events.py).

Covers signature/timestamp admission in `_verify_slack_signature` and the
dispatch logic in `handle_slack_event`: url_verification challenges, message
and app_mention ingestion context, and bot-authored events being ignored.

Runs without a bench: frappe is a MagicMock from `_stub_env`, and the
frappe-facing names the handler relies on (`frappe.throw`, the exception
classes, `frappe.request`, `frappe.db.exists`, `frappe.get_doc`) are patched
per test with small fakes.

Run with:
    python3 -c "import sys; sys.path.insert(0,'huf/ai/tests'); import _stub_env; \
_stub_env.install(); import pytest; sys.exit(pytest.main(['-q','huf/ai/tests/test_slack_events.py']))"

(`python -m pytest huf/ai/tests/test_slack_events.py` cannot be used directly:
the package conftest imports `huf`, which imports frappe before any stub runs.)
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

# `slack_events` imports `frappe.rate_limiter.rate_limit`, which a bare frappe
# MagicMock cannot satisfy as a submodule import. Provide an identity decorator.
if "frappe.rate_limiter" not in sys.modules:
	_rate_limiter = types.ModuleType("frappe.rate_limiter")
	_rate_limiter.rate_limit = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe.rate_limiter"] = _rate_limiter

# `url_verification` imports werkzeug.wrappers.Response lazily. Stub it only
# when werkzeug is not installed so the challenge body can be inspected.
if importlib.util.find_spec("werkzeug") is None and "werkzeug.wrappers" not in sys.modules:
	_werkzeug = types.ModuleType("werkzeug")
	_wrappers = types.ModuleType("werkzeug.wrappers")

	class _FakeResponse:
		def __init__(self, body, status=200, mimetype=None):
			self.body = body
			self.status = status
			self.mimetype = mimetype

	_wrappers.Response = _FakeResponse
	_werkzeug.wrappers = _wrappers
	sys.modules["werkzeug"] = _werkzeug
	sys.modules["werkzeug.wrappers"] = _wrappers

import frappe  # noqa: E402  (MagicMock stub)

# `slack_events` imports `ingest_gateway_event` from gateway_service, which pulls
# in the whole gateway adapter stack (and optional deps such as cryptography).
# The handler is tested in isolation, so stand that module in before import.
if "huf.ai.gateway_service" not in sys.modules:
	_gateway_service = types.ModuleType("huf.ai.gateway_service")
	_gateway_service.ingest_gateway_event = MagicMock(name="ingest_gateway_event")
	sys.modules["huf.ai.gateway_service"] = _gateway_service

# `@frappe.whitelist(...)` on the handler is a MagicMock call under the stub, which
# would replace handle_slack_event with a mock. Import the module with an identity
# decorator, then restore the shared frappe stub's attribute.
_original_whitelist = frappe.whitelist
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
sys.modules.pop("huf.ai.gateways.slack_events", None)
try:
	from huf.ai.gateways import slack_events  # noqa: E402
finally:
	frappe.whitelist = _original_whitelist

SECRET = "test-signing-secret"
NOW = 1_700_000_000
GATEWAY = "slack-main"


class FakePermissionError(Exception):
	pass


class FakeDoesNotExistError(Exception):
	pass


def _fake_throw(message, exc=None, *args, **kwargs):
	raise (exc or Exception)(message)


class FakeRequest:
	def __init__(self, body: bytes, headers: dict, gateway_name: str | None = GATEWAY):
		self._body = body
		self.headers = headers
		self.args = {} if gateway_name is None else {"gateway_name": gateway_name}

	def get_data(self, as_text=False):
		return self._body


def sign(body: bytes, timestamp: int | str, secret: str = SECRET) -> str:
	base = f"v0:{timestamp}:".encode() + body
	return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def signed_headers(body: bytes, timestamp: int | None = NOW, secret: str = SECRET) -> dict:
	ts = str(NOW if timestamp is None else timestamp)
	return {
		"X-Slack-Signature": sign(body, ts, secret),
		"X-Slack-Request-Timestamp": ts,
	}


def message_event(**overrides) -> dict:
	event = {
		"type": "message",
		"channel": "C0123456",
		"user": "U_SENDER",
		"text": "hello there",
		"ts": "1700000000.000100",
		"client_msg_id": "cmid-1",
	}
	event.update(overrides)
	return {"type": "event_callback", "event": event}


class TestSlackEventsHandler(unittest.TestCase):
	def setUp(self):
		self.gateway = SimpleNamespace(
			name=GATEWAY,
			provider="Slack",
			is_enabled=1,
			integration_settings="slack-settings",
		)
		self.settings = SimpleNamespace(
			credentials=[SimpleNamespace(key="signing_secret", get_password=lambda field: SECRET)]
		)
		self.gateways = {GATEWAY: self.gateway}

		def fake_exists(doctype, name=None, *args, **kwargs):
			return doctype == "Gateway" and name in self.gateways

		def fake_get_doc(doctype, name=None, *args, **kwargs):
			if doctype == "Gateway":
				return self.gateways[name]
			if doctype == "Integration Settings":
				return self.settings
			raise AssertionError(f"unexpected get_doc({doctype!r}, {name!r})")

		self.ingest = MagicMock(name="ingest_gateway_event")
		patches = [
			patch.object(frappe, "throw", side_effect=_fake_throw),
			patch.object(frappe, "PermissionError", FakePermissionError),
			patch.object(frappe, "DoesNotExistError", FakeDoesNotExistError),
			patch.object(frappe.db, "exists", side_effect=fake_exists),
			patch.object(frappe, "get_doc", side_effect=fake_get_doc),
			patch.object(frappe, "log_error"),
			patch.object(slack_events, "ingest_gateway_event", self.ingest),
			patch.object(slack_events, "time", MagicMock(time=MagicMock(return_value=NOW))),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def _call(self, payload: dict | bytes, headers: dict | None = None, gateway_name=GATEWAY, sign_it=True):
		body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
		if headers is None:
			headers = signed_headers(body) if sign_it else {}
		request = FakeRequest(body, headers, gateway_name)
		with patch.object(frappe, "request", request):
			return slack_events.handle_slack_event()

	def _assert_rejected(self, payload, headers=None, gateway_name=GATEWAY, sign_it=True, status=401):
		frappe.local.response.http_status_code = None
		result = self._call(payload, headers, gateway_name, sign_it)
		self.assertEqual(frappe.local.response.http_status_code, status)
		self.assertIs(result["ok"], False)
		self.ingest.assert_not_called()

	# -- signature / admission -------------------------------------------------

	def test_valid_signature_is_accepted_and_event_ingested(self):
		result = self._call(message_event())
		self.assertEqual(result, {"ok": True})
		self.ingest.assert_called_once()

	def test_missing_signature_header_is_rejected(self):
		body = json.dumps(message_event()).encode()
		headers = {"X-Slack-Request-Timestamp": str(NOW)}
		self._assert_rejected(body, headers=headers)

	def test_missing_timestamp_header_is_rejected(self):
		body = json.dumps(message_event()).encode()
		headers = {"X-Slack-Signature": sign(body, NOW)}
		self._assert_rejected(body, headers=headers)

	def test_stale_timestamp_older_than_300_seconds_is_rejected(self):
		body = json.dumps(message_event()).encode()
		stale = NOW - 301
		self._assert_rejected(body, headers=signed_headers(body, timestamp=stale))

	def test_future_timestamp_beyond_300_seconds_is_rejected(self):
		body = json.dumps(message_event()).encode()
		future = NOW + 301
		self._assert_rejected(body, headers=signed_headers(body, timestamp=future))

	def test_non_integer_timestamp_is_rejected(self):
		body = json.dumps(message_event()).encode()
		headers = {"X-Slack-Signature": sign(body, "not-a-number"), "X-Slack-Request-Timestamp": "not-a-number"}
		self._assert_rejected(body, headers=headers)

	def test_bad_signature_is_rejected(self):
		body = json.dumps(message_event()).encode()
		headers = {"X-Slack-Signature": sign(body, NOW, secret="wrong"), "X-Slack-Request-Timestamp": str(NOW)}
		self._assert_rejected(body, headers=headers)

	def test_signature_over_different_body_is_rejected(self):
		body = json.dumps(message_event()).encode()
		tampered = json.dumps(message_event(text="tampered")).encode()
		self._assert_rejected(tampered, headers=signed_headers(body))

	def test_unknown_gateway_is_404(self):
		body = json.dumps(message_event()).encode()
		self._assert_rejected(body, headers=signed_headers(body), gateway_name="does-not-exist", status=404)

	def test_missing_gateway_name_is_404(self):
		body = json.dumps(message_event()).encode()
		self._assert_rejected(body, headers=signed_headers(body), gateway_name=None, status=404)

	def test_non_slack_gateway_is_rejected(self):
		self.gateway.provider = "Telegram"
		body = json.dumps(message_event()).encode()
		self._assert_rejected(body, headers=signed_headers(body), status=403)

	def test_disabled_gateway_is_rejected(self):
		self.gateway.is_enabled = 0
		body = json.dumps(message_event()).encode()
		self._assert_rejected(body, headers=signed_headers(body), status=403)

	def test_missing_signing_secret_is_rejected(self):
		self.settings.credentials = [SimpleNamespace(key="bot_token", get_password=lambda f: "xoxb-1")]
		body = json.dumps(message_event()).encode()
		self._assert_rejected(body, headers=signed_headers(body))

	def test_empty_signing_secret_is_rejected(self):
		self.settings.credentials = [SimpleNamespace(key="signing_secret", get_password=lambda f: "")]
		body = json.dumps(message_event()).encode()
		self._assert_rejected(body, headers=signed_headers(body))

	def test_malformed_json_is_400(self):
		body = b"{not json"
		self._assert_rejected(body, headers=signed_headers(body), status=400)

	def test_non_dict_json_is_400(self):
		for raw in (b"[1, 2]", b'"str"', b"null", b"42"):
			self._assert_rejected(raw, headers=signed_headers(raw), status=400)

	def test_verify_returns_reason_strings(self):
		body = b"{}"
		verify = slack_events._verify_slack_signature
		self.assertIsNone(verify(GATEWAY, body, signed_headers(body)))
		self.assertEqual(verify(GATEWAY, body, {}), "missing_headers")
		self.assertEqual(verify(GATEWAY, body, signed_headers(body, NOW - 301)), "stale_timestamp")
		self.assertEqual(verify(GATEWAY, body, signed_headers(body, secret="x")), "bad_signature")

	def test_rejection_does_not_log_header_values(self):
		body = b"{}"
		headers = {"X-Slack-Signature": "v0=secretish", "X-Slack-Request-Timestamp": "garbage-ts"}
		self._call(body, headers=headers)
		frappe.log_error.assert_not_called()

	def test_retry_delivery_returns_200_without_ingest(self):
		body = json.dumps(message_event()).encode()
		headers = signed_headers(body)
		headers["X-Slack-Retry-Num"] = "1"
		frappe.local.response.http_status_code = None
		result = self._call(body, headers=headers)
		self.assertEqual(result, {"ok": True})
		self.assertIsNone(frappe.local.response.http_status_code)
		self.ingest.assert_not_called()

	# -- url_verification ------------------------------------------------------

	def test_url_verification_returns_challenge_without_ingesting(self):
		payload = {"type": "url_verification", "challenge": "abc123xyz"}
		response = self._call(payload)
		self.assertEqual(json.loads(response.body), {"challenge": "abc123xyz"})
		self.assertEqual(response.status, 200)
		self.ingest.assert_not_called()

	# -- event dispatch --------------------------------------------------------

	def test_channel_message_builds_expected_context(self):
		payload = message_event(
			channel="C0123456",
			user="U_SENDER",
			text="ping <@U_BOT> please",
			ts="1700000000.000100",
			thread_ts="1699999999.000001",
			client_msg_id="cmid-42",
		)
		self._call(payload)

		self.ingest.assert_called_once()
		args, kwargs = self.ingest.call_args
		self.assertEqual(args[0], GATEWAY)
		self.assertEqual(args[1], "C0123456:1700000000.000100")
		context = args[2]
		self.assertEqual(context["sender_id"], "U_SENDER")
		self.assertEqual(context["conversation_id"], "C0123456")
		self.assertEqual(context["thread_id"], "1699999999.000001")
		self.assertEqual(context["message_text"], "ping <@U_BOT> please")
		self.assertIs(context["is_room"], True)
		self.assertIs(context["mentioned"], True)
		self.assertIs(kwargs["verified_sender"], True)
		self.assertEqual(kwargs["raw_payload"], payload)

	def test_direct_message_is_not_a_room(self):
		self._call(message_event(channel="D0998877", text="plain dm"))

		context = self.ingest.call_args.args[2]
		self.assertEqual(context["conversation_id"], "D0998877")
		self.assertIs(context["is_room"], False)
		self.assertIs(context["mentioned"], False)

	def test_thread_id_falls_back_to_ts_when_not_in_thread(self):
		self._call(message_event(ts="1700000000.000100", client_msg_id="cmid-7"))

		context = self.ingest.call_args.args[2]
		self.assertEqual(context["thread_id"], "1700000000.000100")

	def test_event_id_is_channel_ts_regardless_of_client_msg_id(self):
		payload = message_event(ts="1700000000.000500")
		del payload["event"]["client_msg_id"]
		self._call(payload)

		self.assertEqual(self.ingest.call_args.args[1], "C0123456:1700000000.000500")

	def test_bot_authored_message_is_ignored(self):
		result = self._call(message_event(bot_id="B_OTHER_BOT"))

		self.assertEqual(result, {"ok": True})
		self.ingest.assert_not_called()

	def test_app_mention_is_ingested_as_mentioned(self):
		payload = {
			"type": "event_callback",
			"event": {
				"type": "app_mention",
				"channel": "C0555",
				"user": "U_SENDER",
				"text": "<@U_BOT> summarize this",
				"ts": "1700000100.000200",
			},
		}
		result = self._call(payload)

		self.assertEqual(result, {"ok": True})
		self.ingest.assert_called_once()
		args, kwargs = self.ingest.call_args
		self.assertEqual(args[1], "C0555:1700000100.000200")
		self.assertIs(args[2]["mentioned"], True)
		self.assertIs(args[2]["is_room"], True)
		self.assertEqual(args[2]["sender_id"], "U_SENDER")

	def test_unhandled_event_type_is_ignored(self):
		result = self._call({"type": "event_callback", "event": {"type": "reaction_added", "user": "U1"}})

		self.assertEqual(result, {"ok": True})
		self.ingest.assert_not_called()

	def test_bot_app_mention_is_ignored(self):
		payload = {
			"type": "event_callback",
			"event": {"type": "app_mention", "channel": "C1", "text": "<@U_BOT> hi", "ts": "1.0", "bot_id": "B1"},
		}
		self._call(payload)

		self.ingest.assert_not_called()

	# -- S3b semantics ---------------------------------------------------------

	def test_message_and_app_mention_dedupe_to_same_event_id_both_orders(self):
		msg = message_event(channel="C9", ts="1700000200.000300", text="<@U_BOT> hi")
		men = {"type": "event_callback", "event": {
			"type": "app_mention", "channel": "C9", "user": "U_SENDER",
			"text": "<@U_BOT> hi", "ts": "1700000200.000300"}}
		self._call(msg)
		self._call(men)
		self.ingest.reset_mock()
		self._call(men)
		self._call(msg)
		ids = [c.args[1] for c in self.ingest.call_args_list]
		self.assertEqual(ids, ["C9:1700000200.000300"] * 2)


if __name__ == "__main__":
	unittest.main()
