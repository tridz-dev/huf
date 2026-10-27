"""Unit tests for the Slack interactivity endpoint and action sessions.

Run with the command in test_slack_events.py's docstring (frappe is stubbed; a small fake
frappe is patched into the modules under test).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import types
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import frappe as _frappe_stub  # noqa: E402

def _load_isolated():
	"""Import slack_interactivity and slack_events with identity decorators and stubbed heavy
	deps, then remove everything we added from sys.modules (no leaked stubs)."""
	touched = {}
	stubs = {}
	if "frappe.rate_limiter" not in sys.modules:
		rl = types.ModuleType("frappe.rate_limiter")
		rl.rate_limit = lambda *a, **k: (lambda fn: fn)
		stubs["frappe.rate_limiter"] = rl
	if "huf.ai.gateway_service" not in sys.modules:
		gs = types.ModuleType("huf.ai.gateway_service")
		gs.ingest_gateway_event = MagicMock()
		stubs["huf.ai.gateway_service"] = gs
	for name in ("huf.ai.gateways.slack_interactivity", "huf.ai.gateways.slack_events"):
		touched[name] = sys.modules.pop(name, None)
	sys.modules.update(stubs)
	orig = _frappe_stub.whitelist
	_frappe_stub.whitelist = lambda *a, **k: (lambda fn: fn)
	try:
		from huf.ai.gateways import slack_events as ev
		from huf.ai.gateways import slack_interactivity as mod
	finally:
		_frappe_stub.whitelist = orig
		for name in stubs:
			sys.modules.pop(name, None)
		for name, old in touched.items():
			sys.modules.pop(name, None)
			if old is not None:
				sys.modules[name] = old
	return mod, ev


si, slack_events = _load_isolated()

SECRET = "sig-secret"
NOW = 1_700_000_000
GATEWAY = "slack-main"


class Row(dict):
	__getattr__ = dict.get


class FakeCursor:
	rowcount = 0


class FakeDb:
	def __init__(self):
		self.sessions = {}
		self._cursor = FakeCursor()

	def sql(self, query, params=()):
		q = " ".join(query.split())
		if q.startswith("UPDATE `tabGateway Action Session` SET state=%s"):
			state, by, at, name, now = params
			s = self.sessions.get(name)
			ok = bool(s and s["state"] == "Pending" and s["expires_at"] > now)
			if ok:
				s.update(state=state, consumed_by=by, consumed_at=at)
			self._cursor.rowcount = 1 if ok else 0
		elif q.startswith("UPDATE `tabGateway Action Session` SET state='Pending'"):
			name, by = params[0], params[1]
			s = self.sessions.get(name)
			ok = bool(s and s["state"] == "Consumed" and s.get("consumed_by") == by
				and (len(params) < 3 or s.get("consumed_at") == params[2]))
			if ok:
				s.update(state="Pending", consumed_by=None, consumed_at=None)
			self._cursor.rowcount = 1 if ok else 0
		elif q.startswith("UPDATE `tabGateway Action Session` SET state='Expired'"):
			s = self.sessions.get(params[0])
			ok = bool(s and s["state"] == "Pending")
			if ok:
				s["state"] = "Expired"
			self._cursor.rowcount = 1 if ok else 0
		else:
			raise AssertionError(query)

	def get_value(self, doctype, name, fields, as_dict=False):
		s = self.sessions.get(name)
		if s is None:
			return None
		if isinstance(fields, str):
			return s.get(fields)
		return Row(s)

	def exists(self, doctype, name):
		return name == GATEWAY


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v


class FakeFrappe:
	class DoesNotExistError(Exception):
		pass

	def __init__(self, gateway):
		self.db = FakeDb()
		self.cache = FakeCache()
		self.local = SimpleNamespace(response=SimpleNamespace(http_status_code=200))
		self.request = None
		self.gateway = gateway
		self.logged = []
		self.counter = 0
		self.clock = datetime(2026, 1, 1, 12, 0, 0)
		self.utils = SimpleNamespace(now_datetime=lambda: self.clock, now=lambda: self.clock)

	def get_doc(self, arg, name=None):
		if isinstance(arg, dict):
			self.counter += 1
			doc = SimpleNamespace(name=f"s{self.counter}")
			data = dict(arg)
			data["name"] = doc.name
			data["payload"] = arg.get("payload")
			doc.insert = lambda ignore_permissions=False: self.db.sessions.__setitem__(doc.name, data)
			return doc
		if arg == "Gateway":
			return self.gateway
		if arg == "Integration Settings":
			row = SimpleNamespace(key="signing_secret", get_password=lambda f: SECRET)
			return SimpleNamespace(credentials=[row])
		raise self.DoesNotExistError()

	def log_error(self, *a, **k):
		self.logged.append((a, k))


class Req:
	def __init__(self, body, headers, gateway=GATEWAY):
		self.body, self.headers = body, headers
		self.args = {} if gateway is None else {"gateway_name": gateway}

	def get_data(self, as_text=False):
		return self.body


def sign(body, ts=NOW, secret=SECRET):
	return "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()


def form(payload):
	return urlencode({"payload": json.dumps(payload)}).encode()


def click(session, choice=None, user="U1", team="T1", channel="C1", ts="1.1", action_ts="9.9"):
	aid = f"{session}.{choice}" if choice else session
	return {
		"type": "block_actions",
		"user": {"id": user, "team_id": team},
		"team": {"id": team},
		"container": {"channel_id": channel, "message_ts": ts},
		"actions": [{"action_id": aid, "value": session, "action_ts": action_ts}],
		"trigger_id": "tr1",
		"response_url": "https://evil.example/x",
	}


class Base(unittest.TestCase):
	def setUp(self):
		self.gw = SimpleNamespace(name=GATEWAY, provider="Slack", is_enabled=1, integration_settings="is")
		self.f = FakeFrappe(self.gw)
		self.api = MagicMock()
		self.linked = {("T1", "U1"): "alice@x.com", ("T1", "U2"): "bob@x.com"}
		from huf.ai.gateways import identity, slack_context

		def find(gw, team, ext):
			u = self.linked.get((team, ext))
			return Row(user=u, source="Self link") if u else None

		patches = [
			patch.object(si, "frappe", self.f),
			patch.object(slack_events, "frappe", self.f),
			patch.object(si, "verify_request_signature", slack_events._verify_slack_signature),
			patch.object(identity, "_find_link", find),
			patch.object(identity, "_usable", lambda u, s=None: True),
			patch.object(slack_context, "get_slack_api", lambda gw: self.api),
			patch.dict(si._HANDLERS, {}, clear=True),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		self.handler = MagicMock(return_value={"text": "Approved."})
		si.register_action_handler("approve", self.handler)

	def make(self, kind="approve", **kw):
		return si.create_action_session(self.gw, kind, {"run": "R1"}, **kw)

	def run_endpoint(self, body, headers=None, gateway=GATEWAY, ts=NOW):
		if headers is None:
			headers = {"X-Slack-Signature": sign(body, ts), "X-Slack-Request-Timestamp": str(ts)}
		self.f.request = Req(body, headers, gateway)
		with patch("time.time", return_value=NOW):
			return si.handle_slack_interaction()

	def ephemerals(self):
		return [c.kwargs.get("text") or c.args[-1] for c in self.api.post_ephemeral.call_args_list]


class TestEndpoint(Base):
	def test_valid_signature_ok(self):
		s = self.make()
		self.assertEqual(self.run_endpoint(form(click(s, "approve"))), {})
		self.handler.assert_called_once()

	def test_bad_signature_401(self):
		body = form(click(self.make()))
		out = self.run_endpoint(body, {"X-Slack-Signature": "v0=bad", "X-Slack-Request-Timestamp": str(NOW)})
		self.assertEqual(self.f.local.response.http_status_code, 401)
		self.assertEqual(out["error"], "bad_signature")
		self.handler.assert_not_called()

	def test_stale_timestamp(self):
		body = form(click(self.make()))
		self.run_endpoint(body, ts=NOW - 1000)
		self.assertEqual(self.f.local.response.http_status_code, 401)

	def test_missing_headers(self):
		out = self.run_endpoint(form(click(self.make())), {})
		self.assertEqual(out["error"], "missing_headers")
		self.assertEqual(self.f.local.response.http_status_code, 401)

	def test_invalid_timestamp(self):
		out = self.run_endpoint(b"x", {"X-Slack-Signature": "v0=a", "X-Slack-Request-Timestamp": "abc"})
		self.assertEqual(out["error"], "invalid_timestamp")

	def test_unknown_gateway_404(self):
		body = form(click(self.make()))
		out = self.run_endpoint(body, gateway="nope")
		self.assertEqual(self.f.local.response.http_status_code, 404)
		self.assertEqual(out["error"], "unknown_gateway")

	def test_missing_gateway_param(self):
		out = self.run_endpoint(form(click(self.make())), gateway=None)
		self.assertEqual(out["error"], "unknown_gateway")

	def test_disabled_gateway_403(self):
		self.gw.is_enabled = 0
		self.run_endpoint(form(click(self.make())))
		self.assertEqual(self.f.local.response.http_status_code, 403)

	def test_wrong_provider_403(self):
		self.gw.provider = "Discord"
		self.run_endpoint(form(click(self.make())))
		self.assertEqual(self.f.local.response.http_status_code, 403)

	def test_malformed_payload_400(self):
		for raw in (b"payload=notjson", b"other=1", b"payload={}&payload={}", b"payload=%5B1%5D"):
			self.f.local.response.http_status_code = 200
			out = self.run_endpoint(raw)
			self.assertEqual(out["error"], "malformed_payload", raw)
			self.assertEqual(self.f.local.response.http_status_code, 400)

	def test_signature_checked_before_parse(self):
		with patch.object(si, "_parse_payload") as parse:
			self.run_endpoint(b"junk", {"X-Slack-Signature": "v0=x", "X-Slack-Request-Timestamp": str(NOW)})
			parse.assert_not_called()


class TestFlow(Base):
	def test_dispatch_passes_actor_choice_and_session(self):
		s = self.make()
		self.run_endpoint(form(click(s, "approve")))
		gw, session, actor, payload = self.handler.call_args.args
		self.assertEqual(actor, "alice@x.com")
		self.assertEqual(session["choice"], "approve")
		self.assertEqual(session["payload"], {"run": "R1"})
		self.assertEqual(payload["type"], "block_actions")

	def test_message_updated_with_status_line(self):
		s = self.make()
		self.run_endpoint(form(click(s, "approve", channel="C9", ts="5.5")))
		self.api.update_message.assert_called_once()
		args, kw = self.api.update_message.call_args
		self.assertEqual(args[:2], ("C9", "5.5"))
		self.assertEqual(kw["text"], "Approved.")
		self.assertEqual(kw["blocks"][0]["type"], "context")

	def test_handler_blocks_used_when_returned(self):
		self.handler.return_value = {"text": "ok", "blocks": [{"type": "divider"}]}
		self.run_endpoint(form(click(self.make())))
		self.assertEqual(self.api.update_message.call_args.kwargs["blocks"], [{"type": "divider"}])

	def test_unlinked_clicker(self):
		s = self.make()
		self.run_endpoint(form(click(s, user="UX")))
		self.handler.assert_not_called()
		self.assertIn("link your Huf account", self.ephemerals()[0])
		self.assertEqual(self.f.db.sessions[s]["state"], "Pending")
		self.api.update_message.assert_not_called()

	def test_actor_optional_handler_runs_for_unlinked_clicker(self):
		opt = MagicMock(return_value={"text": "Linked."})
		si.register_action_handler("optkind:", opt, requires_actor=False)
		self.addCleanup(si._ACTOR_OPTIONAL.discard, "optkind:")
		s = self.make(kind="optkind:x", intended_slack_user="UX")
		self.run_endpoint(form(click(s, user="UX")))
		opt.assert_called_once()
		self.assertIsNone(opt.call_args.args[2])
		self.assertEqual(self.f.db.sessions[s]["state"], "Consumed")

	def test_actor_optional_still_checks_intended_slack_user(self):
		opt = MagicMock(return_value={"text": "Linked."})
		si.register_action_handler("optkind:", opt, requires_actor=False)
		self.addCleanup(si._ACTOR_OPTIONAL.discard, "optkind:")
		s = self.make(kind="optkind:x", intended_slack_user="UX")
		self.run_endpoint(form(click(s, user="UY")))
		opt.assert_not_called()
		self.assertEqual(self.f.db.sessions[s]["state"], "Pending")

	def test_wrong_clicker_by_user(self):
		s = self.make(intended_user="alice@x.com")
		self.run_endpoint(form(click(s, user="U2")))
		self.handler.assert_not_called()
		self.assertIn("not meant for you", self.ephemerals()[0])
		self.assertEqual(self.f.db.sessions[s]["state"], "Pending")

	def test_wrong_clicker_by_slack_user(self):
		s = self.make(intended_slack_user="U1")
		self.run_endpoint(form(click(s, user="U2")))
		self.handler.assert_not_called()

	def test_right_clicker_passes(self):
		s = self.make(intended_user="alice@x.com", intended_slack_user="U1")
		self.run_endpoint(form(click(s)))
		self.handler.assert_called_once()

	def test_double_click_second_rejected(self):
		s = self.make()
		self.run_endpoint(form(click(s, action_ts="1")))
		self.run_endpoint(form(click(s, user="U2", action_ts="2")))
		self.assertEqual(self.handler.call_count, 1)
		self.assertIn("already handled", self.ephemerals()[0])

	def test_dedupe_same_action_ts(self):
		s = self.make()
		self.run_endpoint(form(click(s)))
		self.run_endpoint(form(click(s)))
		self.assertEqual(self.handler.call_count, 1)
		self.api.post_ephemeral.assert_not_called()

	def test_expired_session(self):
		s = self.make(ttl_seconds=10)
		self.f.clock += timedelta(seconds=11)
		self.run_endpoint(form(click(s)))
		self.handler.assert_not_called()
		self.assertIn("expired", self.ephemerals()[0])
		self.assertEqual(self.f.db.sessions[s]["state"], "Expired")

	def test_cancelled_session(self):
		s = self.make()
		self.f.db.sessions[s]["state"] = "Cancelled"
		self.run_endpoint(form(click(s)))
		self.handler.assert_not_called()
		self.assertIn("cancelled", self.ephemerals()[0])

	def test_unknown_session(self):
		self.run_endpoint(form(click("ghost")))
		self.handler.assert_not_called()
		self.assertIn("no longer available", self.ephemerals()[0])

	def test_value_action_id_mismatch(self):
		s = self.make()
		p = click(s)
		p["actions"][0]["action_id"] = "other"
		self.run_endpoint(form(p))
		self.handler.assert_not_called()

	def test_channel_mismatch_rejected(self):
		s = self.make(channel="C1")
		self.run_endpoint(form(click(s, channel="C2")))
		self.handler.assert_not_called()

	def test_other_gateway_session_rejected(self):
		s = self.make()
		self.f.db.sessions[s]["gateway"] = "other-gw"
		self.run_endpoint(form(click(s)))
		self.handler.assert_not_called()

	def test_no_handler_polite_error_and_session_kept(self):
		s = self.make(kind="mystery")
		self.run_endpoint(form(click(s)))
		self.assertIn("not supported", self.ephemerals()[0])
		self.assertEqual(self.f.db.sessions[s]["state"], "Pending")

	def test_handler_exception_does_not_leak(self):
		self.handler.side_effect = RuntimeError("secret detail")
		s = self.make()
		self.assertEqual(self.run_endpoint(form(click(s))), {})
		self.assertEqual(self.api.update_message.call_args.kwargs["text"], si.MSG_FAILED)
		self.assertNotIn("secret detail", repr(self.f.logged))

	def test_handler_exception_reopens_session_for_retry(self):
		self.handler.side_effect = RuntimeError("boom")
		s = self.make()
		self.run_endpoint(form(click(s)))
		self.assertEqual(self.f.db.sessions[s]["state"], "Pending")
		self.assertIsNone(self.f.db.sessions[s]["consumed_by"])
		self.handler.side_effect = None
		self.handler.return_value = {"text": "ok"}
		self.f.cache.d.clear()  # the Slack-side retry is a new click
		self.run_endpoint(form(click(s)))
		self.assertEqual(self.f.db.sessions[s]["state"], "Consumed")

	def test_release_only_when_consumed_by_this_request(self):
		s = self.make()
		first = si.consume_action_session(s, "a")
		self.assertFalse(si.release_action_session(s, "b"))
		self.assertFalse(si.release_action_session(s, "a", "other-time"))
		self.assertTrue(si.release_action_session(s, "a", first["consumed_at"]))
		self.assertEqual(self.f.db.sessions[s]["state"], "Pending")

	def test_response_url_never_used(self):
		with patch("urllib.request.urlopen") as uo:
			self.run_endpoint(form(click(self.make())))
			uo.assert_not_called()

	def test_dm_ephemeral_without_channel(self):
		p = click("ghost")
		p["container"] = {}
		self.api.conversations_open.return_value = "D1"
		self.run_endpoint(form(p))
		self.api.post_message.assert_called_once()

	def test_unimplemented_shortcut_and_view(self):
		for typ in ("shortcut", "view_submission", "message_action"):
			self.api.reset_mock()
			p = {"type": typ, "callback_id": "x", "user": {"id": "U1", "team_id": "T1"}, "team": {"id": "T1"}}
			self.run_endpoint(form(p))
			self.assertIn("not supported", self.api.post_message.call_args.kwargs["text"])

	def test_registered_shortcut_dispatch(self):
		fn = MagicMock()
		si.register_action_handler("shortcut:run_flow", fn)
		p = {"type": "shortcut", "callback_id": "run_flow", "user": {"id": "U1"}, "team": {"id": "T1"}}
		self.run_endpoint(form(p))
		fn.assert_called_once()
		self.assertIsNone(fn.call_args.args[1])


class TestSessions(Base):
	def test_create_stores_payload_json(self):
		s = self.make(intended_user="alice@x.com")
		row = self.f.db.sessions[s]
		self.assertEqual(json.loads(row["payload"]), {"run": "R1"})
		self.assertEqual(row["state"], "Pending")
		self.assertEqual(row["intended_user"], "alice@x.com")

	def test_atomic_consume_exactly_one_winner(self):
		s = self.make()
		results = [si.consume_action_session(s, u) for u in ("a", "b", "c")]
		self.assertEqual([r["ok"] for r in results], [True, False, False])
		self.assertEqual(self.f.db.sessions[s]["consumed_by"], "a")

	def test_consume_race_stale_read_still_single_winner(self):
		s = self.make()
		# Both consumers observed Pending before either wrote; only the conditional UPDATE decides.
		first = si.consume_action_session(s, "a")
		self.f.db.sessions[s]["state"] = "Consumed"
		second = si.consume_action_session(s, "b")
		self.assertTrue(first["ok"])
		self.assertFalse(second["ok"])
		self.assertEqual(second["reason"], "consumed")

	def test_consume_expired(self):
		s = self.make(ttl_seconds=1)
		self.f.clock += timedelta(seconds=5)
		r = si.consume_action_session(s, "a")
		self.assertEqual(r["reason"], "expired")

	def test_consume_unknown(self):
		self.assertEqual(si.consume_action_session("zzz", "a")["reason"], "unknown")

	def test_registry_longest_prefix(self):
		a, b = MagicMock(), MagicMock()
		si.register_action_handler("feedback", a)
		si.register_action_handler("feedback.thumb", b)
		self.assertIs(si.get_action_handler("feedback.thumb.up"), b)
		self.assertIs(si.get_action_handler("feedback.other"), a)
		self.assertIsNone(si.get_action_handler("nothing"))

	def test_register_validation(self):
		with self.assertRaises(ValueError):
			si.register_action_handler("", lambda *a: None)
		with self.assertRaises(ValueError):
			si.register_action_handler("x", None)


class TestDoctypeJson(unittest.TestCase):
	def setUp(self):
		path = os.path.join(os.path.dirname(__file__), "..", "..", "huf", "doctype", "gateway_action_session",
			"gateway_action_session.json")
		with open(path) as fh:
			self.d = json.load(fh)

	def test_fields(self):
		fields = {f["fieldname"]: f for f in self.d["fields"]}
		for name in ("gateway", "kind", "intended_user", "intended_slack_user", "payload", "state", "expires_at",
			"consumed_by", "consumed_at", "channel", "message_ts"):
			self.assertIn(name, fields)
		self.assertEqual(fields["gateway"]["options"], "Gateway")
		self.assertEqual(fields["payload"]["fieldtype"], "JSON")
		self.assertEqual(fields["state"]["options"].split("\n"), ["Pending", "Consumed", "Expired", "Cancelled"])
		self.assertEqual(set(self.d["field_order"]), set(fields))

	def test_system_manager_only(self):
		self.assertEqual({p["role"] for p in self.d["permissions"]}, {"System Manager"})
		self.assertEqual(self.d["name"], "Gateway Action Session")


if __name__ == "__main__":
	unittest.main()
