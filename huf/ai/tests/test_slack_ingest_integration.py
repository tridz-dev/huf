"""Slack webhook handler wired to the REAL gateway_service.ingest_gateway_event.

Only the persistence edges are faked (frappe.db.get_value, frappe.get_doc,
Gateway Event insert, admission/routing). Verifies that Slack's paired
`message` + `app_mention` events dedupe to one stored event and that the stored
one always carries mentioned=True.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "testing"))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import frappe  # noqa: E402

# Temporarily stub modules missing from a frappe-less env, import the real
# gateway_service + slack_events, then remove every stub/alias we added.
_STUBS = ("frappe.rate_limiter", "cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
		"cryptography.hazmat.primitives.ciphers", "cryptography.hazmat.primitives.padding",
		"cryptography.hazmat.backends")
_added = []
for _name in _STUBS:
	if _name in sys.modules:
		continue
	try:
		importlib.import_module(_name)
		continue
	except Exception:
		pass
	_m = types.ModuleType(_name)
	_m.__path__ = []
	_m.rate_limit = lambda *a, **k: (lambda f: f)
	_m.__getattr__ = lambda attr: MagicMock(name=attr)
	sys.modules[_name] = _m
	_added.append(_name)

_had_gs = "huf.ai.gateway_service" in sys.modules
_orig_whitelist = frappe.whitelist
frappe.whitelist = lambda *a, **k: (lambda fn: fn)
_saved_slack_events = sys.modules.pop("huf.ai.gateways.slack_events", None)
try:
	gs = importlib.import_module("huf.ai.gateway_service")
	_spec = importlib.util.spec_from_file_location(
		"_slack_events_real_gs",
		os.path.join(os.path.dirname(__file__), "..", "gateways", "slack_events.py"),
	)
	slack_events = importlib.util.module_from_spec(_spec)
	_spec.loader.exec_module(slack_events)
finally:
	frappe.whitelist = _orig_whitelist
	for _name in _added:
		sys.modules.pop(_name, None)
	if not _had_gs:
		sys.modules.pop("huf.ai.gateway_service", None)
	sys.modules.pop("huf.ai.gateways.slack_events", None)
	if _saved_slack_events is not None:
		sys.modules["huf.ai.gateways.slack_events"] = _saved_slack_events

GATEWAY = "slack-main"


class _Req:
	def __init__(self, body):
		self._body = body
		self.headers = {}
		self.args = {"gateway_name": GATEWAY}

	def get_data(self, as_text=False):
		return self._body


def _event(kind, text, auths):
	payload = {"type": "event_callback", "event": {
		"type": kind, "channel": "C1", "user": "U1", "text": text, "ts": "1700000000.000100"}}
	if auths:
		payload["authorizations"] = [{"user_id": "U_BOT"}]
	return payload


class TestSlackIngestIntegration:
	def setup_method(self):
		self.stored = {}  # idempotency_key -> name
		self.admitted = []  # contexts of events that were actually stored
		gateway = SimpleNamespace(name=GATEWAY, is_enabled=1, provider="Slack")

		def get_value(doctype, filters, field=None, *a, **k):
			return self.stored.get(filters["idempotency_key"])

		def make_event(doc):
			ev = MagicMock(name="event")
			ev.name = f"EVT-{len(self.stored) + 1}"
			ev.insert.side_effect = lambda **kw: self.stored.__setitem__(doc["idempotency_key"], ev.name)
			return ev

		def get_doc(arg, name=None, *a, **k):
			return make_event(arg) if isinstance(arg, dict) else gateway

		def admission(gw, context):
			self.admitted.append(dict(context))
			return True, ""

		route = {"status": "Queued", "target_type": "Agent", "agent": "A1", "binding": None}
		patches = [
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe, "enqueue"),
			patch.object(gs, "_admission", side_effect=admission),
			patch.object(gs, "resolve_gateway_route", return_value=route),
			patch.object(slack_events, "ingest_gateway_event", gs.ingest_gateway_event),
			patch.object(slack_events, "_verify_slack_signature", return_value=None),
		]
		for p in patches:
			p.start()
		self._patches = patches

	def teardown_method(self):
		for p in self._patches:
			p.stop()

	def _send(self, payload):
		with patch.object(frappe, "request", _Req(json.dumps(payload).encode())):
			slack_events.handle_slack_event()

	def _run(self, payloads):
		real = gs.ingest_gateway_event
		results = []

		def spy(*a, **k):
			r = real(*a, **k)
			results.append(r)
			return r

		with patch.object(slack_events, "ingest_gateway_event", spy):
			for p in payloads:
				self._send(p)
		return results

	def test_known_bot_message_then_app_mention_second_is_duplicate(self):
		text = "<@U_BOT> hi"
		res = self._run([_event("message", text, True), _event("app_mention", text, True)])
		assert "duplicate" not in res[0] and res[1]["duplicate"] is True
		assert res[1]["event_name"] == "EVT-1"
		assert len(self.admitted) == 1 and self.admitted[0]["mentioned"] is True

	def test_known_bot_app_mention_then_message_second_is_duplicate(self):
		text = "<@U_BOT> hi"
		res = self._run([_event("app_mention", text, True), _event("message", text, True)])
		assert res[1]["duplicate"] is True
		assert len(self.admitted) == 1 and self.admitted[0]["mentioned"] is True

	def test_unknown_bot_message_first_does_not_shadow_app_mention(self):
		text = "<@U_BOT> hi"
		res = self._run([_event("message", text, False), _event("app_mention", text, False)])
		# The message is ignored (never reaches ingest); the mention is stored as mentioned.
		assert len(res) == 1 and "duplicate" not in res[0]
		assert len(self.admitted) == 1 and self.admitted[0]["mentioned"] is True

	def test_unknown_bot_app_mention_first_then_message(self):
		text = "<@U_BOT> hi"
		res = self._run([_event("app_mention", text, False), _event("message", text, False)])
		assert len(res) == 1
		assert len(self.admitted) == 1 and self.admitted[0]["mentioned"] is True

	def test_retry_of_stored_event_is_duplicate(self):
		payload = _event("message", "plain", False)
		res = self._run([payload, payload])
		assert "duplicate" not in res[0] and res[1]["duplicate"] is True
