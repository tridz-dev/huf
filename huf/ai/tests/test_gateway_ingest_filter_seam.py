"""Seam tests for the REAL gateway_service.ingest_gateway_event pre_ingest_filter handling.

Covers: raw_payload passed to filters, silent drop vs. reasoned Rejected event,
ON_EVENT_REJECTED firing, reason-flag hygiene and dedupe-before-filters.
Only persistence edges are faked.
"""

from __future__ import annotations

import datetime as _dt
import importlib
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.tests.unit_support import MonkeyPatch, SupportCase  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "testing"))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import frappe  # noqa: E402

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
try:
	gs = importlib.import_module("huf.ai.gateway_service")
	hooks = importlib.import_module("huf.ai.gateways.hooks")
finally:
	frappe.whitelist = _orig_whitelist
	for _name in _added:
		sys.modules.pop(_name, None)
	if not _had_gs:
		sys.modules.pop("huf.ai.gateway_service", None)

GATEWAY = "gw-main"
CTX = {"sender_id": "U1", "conversation_id": "C1", "thread_id": "T1", "message_text": "hello"}
RAW = {"tenant": "t-123", "k": "v"}


class TestIngestFilterSeam(SupportCase):
	def setUp(self):
		hooks.clear()
		self.stored = {}
		self.events = []
		self.admitted = []
		self.routed = []
		self.rejected = []
		gateway = SimpleNamespace(name=GATEWAY, is_enabled=1, provider="Slack")

		def get_value(doctype, filters, field=None, *a, **k):
			return self.stored.get(filters["idempotency_key"])

		def make_event(doc):
			ev = MagicMock(name="event")
			ev.name = f"EVT-{len(self.events) + 1}"
			ev.insert.side_effect = lambda **kw: self.stored.__setitem__(doc["idempotency_key"], ev.name)
			self.events.append(ev)
			return ev

		def get_doc(arg, name=None, *a, **k):
			return make_event(arg) if isinstance(arg, dict) else gateway

		def admission(gw, context):
			self.admitted.append(dict(context))
			return True, ""

		def route(gw_name, context):
			self.routed.append(dict(context))
			return {"status": "Queued", "target_type": "Agent", "agent": "A1", "binding": None}

		self.gateway = gateway
		patches = [
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe, "enqueue"),
			patch.object(gs, "now_datetime", side_effect=_dt.datetime.now),
			patch.object(gs, "_admission", side_effect=admission),
			patch.object(gs, "resolve_gateway_route", side_effect=route),
			patch.object(hooks, "register_all"),
		]
		for p in patches:
			p.start()
		self._patches = patches
		frappe.flags.gateway_filter_reason = None
		hooks.register(hooks.ON_EVENT_REJECTED, lambda *a: self.rejected.append(a))

	def tearDown(self):
		for p in self._patches:
			p.stop()
		hooks.clear()
		frappe.flags.gateway_filter_reason = None

	def _ingest(self, eid="e1", raw=RAW):
		return gs.ingest_gateway_event(GATEWAY, eid, dict(CTX), verified_sender=True, raw_payload=raw)

	def test_filter_receives_raw_payload_and_original_context(self):
		seen = []
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: seen.append((gw, ctx)) or True)
		self._ingest()
		gw, ctx = seen[0]
		assert gw is self.gateway
		assert ctx["raw_payload"] == RAW
		for k, v in CTX.items():
			assert ctx[k] == v

	def test_raw_payload_none_is_passed_as_none(self):
		seen = []
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: seen.append(ctx) or True)
		self._ingest(raw=None)
		assert "raw_payload" in seen[0] and seen[0]["raw_payload"] is None

	def test_filter_false_without_reason_is_silent_drop(self):
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: False)
		assert self._ingest() == {"filtered": True}
		assert self.events == [] and self.rejected == [] and self.admitted == []

	def test_filter_false_with_reason_creates_rejected_event(self):
		def flt(gw, ctx):
			frappe.flags.gateway_filter_reason = "wrong tenant"
			return False

		hooks.register(hooks.PRE_INGEST_FILTER, flt)
		res = self._ingest()
		assert res == {"event_name": "EVT-1", "status": "Rejected"}
		assert len(self.events) == 1
		ev = self.events[0]
		ev.insert.assert_called_once()
		ev.db_set.assert_called_once_with({"status": "Rejected", "error_message": "wrong tenant"})
		assert self.rejected == [(self.gateway, ev, "Rejected", "wrong tenant")]
		assert self.admitted == [] and self.routed == []

	def test_reason_flag_cleared_after_rejection(self):
		calls = []

		def flt(gw, ctx):
			calls.append(1)
			if len(calls) == 1:
				frappe.flags.gateway_filter_reason = "first only"
			return False

		hooks.register(hooks.PRE_INGEST_FILTER, flt)
		assert self._ingest("e1")["status"] == "Rejected"
		assert frappe.flags.gateway_filter_reason is None
		assert self._ingest("e2") == {"filtered": True}
		assert len(self.events) == 1

	def test_stale_reason_flag_does_not_leak_into_new_event(self):
		frappe.flags.gateway_filter_reason = "stale"
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: False)
		assert self._ingest() == {"filtered": True}

	def test_non_string_or_empty_reason_ignored(self):
		for bad in ("", 123, ["x"], {"r": 1}, True):
			def flt(gw, ctx, bad=bad):
				frappe.flags.gateway_filter_reason = bad
				return False

			hooks.clear()
			hooks.register(hooks.ON_EVENT_REJECTED, lambda *a: self.rejected.append(a))
			hooks.register(hooks.PRE_INGEST_FILTER, flt)
			assert self._ingest(f"id-{bad!r}") == {"filtered": True}
			assert frappe.flags.gateway_filter_reason is None
		assert self.events == [] and self.rejected == []

	def test_reason_set_but_filter_passes_is_ignored(self):
		def flt(gw, ctx):
			frappe.flags.gateway_filter_reason = "ignored"
			return True

		hooks.register(hooks.PRE_INGEST_FILTER, flt)
		res = self._ingest()
		assert res["event_name"] == "EVT-1" and res.get("status") == "Queued"
		assert self.rejected == []

	def test_all_true_filters_take_normal_path(self):
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: True)
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: None)
		res = self._ingest()
		assert res["event_name"] == "EVT-1" and res["status"] == "Queued"
		assert len(self.admitted) == 1 and len(self.routed) == 1
		assert "raw_payload" not in self.admitted[0]
		assert self.rejected == []

	def test_duplicate_dedupes_before_filters_run(self):
		calls = []
		hooks.register(hooks.PRE_INGEST_FILTER, lambda gw, ctx: calls.append(1) or True)
		first = self._ingest("dup")
		res = self._ingest("dup")
		assert res == {"duplicate": True, "event_name": first["event_name"]}
		assert len(calls) == 1


# --- T16: REAL composition (ingest -> call_filters -> real Teams filters) ---------------------

import copy  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

_TEAMS_FIX = Path(__file__).parent / "fixtures" / "teams"
_HOME = "00000000-0000-0000-0000-00000000aaaa"
_FOREIGN = "00000000-0000-0000-0000-00000000ffff"


def _teams_activity(text, tenant=_HOME, fixture="personal_message", kind="message"):
	act = json.loads((_TEAMS_FIX / f"{fixture}.json").read_text())
	act["text"] = text
	act["channelData"]["tenant"]["id"] = tenant
	act["conversation"]["tenantId"] = tenant
	act["huf_kind"] = kind
	return act


class TestTeamsFilterComposition(SupportCase):
	_ingest = TestIngestFilterSeam._ingest

	def setUp(self):
		TestIngestFilterSeam.setUp(self)
		self.gateway.provider = "Microsoft Teams"
		self.order = []
		self.tokens = []
		self.outbox = []
		self.pm = MonkeyPatch()
		self.tt = importlib.import_module("huf.ai.gateways.teams.tenant")
		self.th = importlib.import_module("huf.ai.gateways.teams.messaging.help")
		self.ta = importlib.import_module("huf.ai.gateways.teams.actions")
		self.tr = importlib.import_module("huf.ai.gateways.teams.refs")
		hooks.clear()
		hooks.register(hooks.ON_EVENT_REJECTED, lambda *a: self.rejected.append(a))
		for mod in (self.tt, self.th, self.ta, self.tr):
			mod.register()
		self.pm.setattr(self.tt, "get_allowed_tenants", lambda gw: [_HOME])
		self.pm.setattr(self.th.teams_outbox, "enqueue", lambda *a, **k: self.outbox.append(a) or "n1")
		self.pm.setattr(self.th.teams_identity, "_prompt_token", lambda *a: self.tokens.append(a) or "TOK")
		self.pm.setattr(self.th.teams_identity, "resolve_user", lambda *a: None)
		self.pm.setattr(self.th.teams_identity, "link_url", lambda t: "https://huf.test/link?token=" + t)
		self.pm.setattr(self.tr, "upsert_reference", lambda *a, **k: self.order.append("upsert"))
		self.pm.setattr(self.ta, "_handle", lambda *a, **k: self.order.append("card") or {})
		self.pm.setattr(self.ta.frappe, "local", SimpleNamespace(), raising=False)

	def tearDown(self):
		self.pm.undo()
		TestIngestFilterSeam.tearDown(self)

	def _teams(self, eid, text, **kw):
		raw = _teams_activity(text, **kw)
		return gs.ingest_gateway_event(
			GATEWAY, eid, {**CTX, "message_text": text}, verified_sender=True, raw_payload=raw
		)

	def test_foreign_tenant_command_gets_no_reply_no_token_and_is_rejected(self):
		for text in ["connect", "help", "status"]:
			with self.subTest(text=text):
				self.reset_fixtures()
				res = self._teams("x-" + text, text, tenant=_FOREIGN)
				assert res == {"event_name": "EVT-1", "status": "Rejected"}
				assert self.outbox == [] and self.tokens == []
				assert self.events[0].db_set.call_args[0][0] == {
					"status": "Rejected", "error_message": "tenant_not_allowed"}
				assert self.rejected[0][3] == "tenant_not_allowed"

	def test_allowed_tenant_command_still_answered(self):
		self.pm.setattr(self.th, "_snapshot", lambda gw, meta: {"service_url": "https://x"})
		res = self._teams("ok1", "help")
		assert res == {"filtered": True}  # command handled: dropped from routing
		assert len(self.outbox) == 1

	def test_foreign_tenant_card_action_never_reaches_handler(self):
		res = self._teams("c1", "", tenant=_FOREIGN, fixture="invoke_card_action", kind="card_action")
		assert res["status"] == "Rejected"
		assert "card" not in self.order

	def test_foreign_tenant_install_creates_nothing(self):
		res = self._teams("i1", "", tenant=_FOREIGN, fixture="installation_add", kind="install")
		assert res["status"] == "Rejected" and "upsert" not in self.order

	def test_stop_at_first_false_call_order(self):
		seen = []
		hooks.clear()
		hooks.register(hooks.PRE_INGEST_FILTER, lambda g, c: seen.append("a") or True, priority=10)
		hooks.register(hooks.PRE_INGEST_FILTER, lambda g, c: seen.append("b") or False, priority=20)
		hooks.register(hooks.PRE_INGEST_FILTER, lambda g, c: seen.append("c") or True, priority=30)
		assert self._ingest("o1") == {"filtered": True}
		assert seen == ["a", "b"]

	def test_raising_filter_drops_event_fail_closed(self):
		def boom(g, c):
			raise RuntimeError("settings down secret=abc")

		hooks.clear()
		hooks.register(hooks.ON_EVENT_REJECTED, lambda *a: self.rejected.append(a))
		later = []
		hooks.register(hooks.PRE_INGEST_FILTER, boom, priority=10)
		hooks.register(hooks.PRE_INGEST_FILTER, lambda g, c: later.append(1) or True, priority=20)
		res = self._ingest("r1")
		assert res["status"] == "Rejected" and later == []
		assert self.rejected[0][3] == "filter_error"
		assert admitted_none(self)

	def test_raising_filter_keeps_specific_reason(self):
		def flt(g, c):
			frappe.flags.gateway_filter_reason = "specific"
			raise RuntimeError("x")

		hooks.clear()
		hooks.register(hooks.PRE_INGEST_FILTER, flt)
		assert self._ingest("r2")["status"] == "Rejected"
		assert self.events[0].db_set.call_args[0][0]["error_message"] == "specific"


def admitted_none(case):
	return case.admitted == [] and case.routed == []
