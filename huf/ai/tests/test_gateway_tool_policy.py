"""Tests for the A8 confirm gate + gateway tool policy (frappe stubbed; fake frappe patched in)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "testing"))
import _stub_env  # noqa: E402

_stub_env.install()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import importlib  # noqa: E402
import types  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from huf.ai.gateways import tool_policy as tp  # noqa: E402


class _FunctionTool:
	def __init__(self, name, description, params_json_schema, on_invoke_tool, strict_json_schema=False):
		self.name = name
		self.on_invoke_tool = on_invoke_tool


def _load_sdk_tools():
	"""Import the real sdk_tools with its heavy imports stubbed; sys.modules is restored afterwards
	so nothing leaks into other test modules."""
	heavy = [
		"huf.ai.conversation_data_tools", "huf.ai.handlers.agent_runner", "huf.ai.handlers.crud",
		"huf.ai.handlers.media", "huf.ai.tools.invocation", "huf.ai.tools.registry", "huf.ai.tools.types",
		"huf.ai.tools.perplexity",
	]
	mods = {n: MagicMock() for n in heavy}
	mods["huf.ai.tools.types"]._GUEST_DOCTYPE_PINNED_TYPES = set()
	mods["huf.ai.tools.types"]._GUEST_REPORT_PINNED_TYPES = set()
	agents = types.ModuleType("agents")
	agents.FunctionTool = _FunctionTool
	mods["agents"] = agents
	with patch.dict(sys.modules, mods):
		sys.modules.pop("huf.ai.sdk_tools", None)
		return importlib.import_module("huf.ai.sdk_tools")


sdk_tools = _load_sdk_tools()

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RUN = "RUN-1"


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v
		self.ttl = getattr(self, "ttl", {})
		self.ttl[k] = expires_in_sec


class FakeDb:
	def __init__(self):
		self.runs = {RUN: "gw:EV-1", "RUN-X": None, "RUN-WEB": "abc"}
		self.events = {"EV-1": {"name": "EV-1", "gateway": "gw1", "conversation_id": "C1"}}
		self.calls = 0

	def get_value(self, doctype, name, fields=None, as_dict=False):
		self.calls += 1
		if doctype == "Agent Run":
			return self.runs.get(name)
		return self.events.get(name)


class FakeFrappe:
	def __init__(self):
		self.cache_obj = FakeCache()
		self.db = FakeDb()
		self.policies = []
		self.session = SimpleNamespace(user="u")

	def cache(self):
		return self.cache_obj

	def get_all(self, doctype, filters=None, fields=None):
		return [p for p in self.policies if p["gateway"] == filters["gateway"]]


def _fx_fk(self):
	monkeypatch = self.monkeypatch
	f = FakeFrappe()
	monkeypatch.setattr(tp, "frappe", f)
	monkeypatch.setattr(tp, "_CONFIRMER", None)
	return f


def pol(gateway="gw1", scope="", mode=tp.ALLOW, tools="", cross=0):
	return {"gateway": gateway, "scope": scope, "mode": mode, "tools": tools, "allow_cross_channel_send": cross}


def denied(out):
	return out is not None and json.loads(out).get("denied") is True


































































# ---------------------------------------------------------------- sdk_tools wrapper
def make_tool(monkeypatch, fk, flag=False):
	calls = []

	def fn(**kw):
		calls.append(kw)
		return {"ok": True}

	monkeypatch.setattr(sdk_tools, "get_function_from_name", lambda *a, **k: fn)
	monkeypatch.setattr(sdk_tools, "_check_tool_permission", lambda *a, **k: {"allowed": True})
	monkeypatch.setattr(sdk_tools, "frappe", SimpleNamespace(session=fk.session, logger=lambda *a: SimpleNamespace(debug=lambda *x: None), get_traceback=lambda: "", log=lambda *a: None))
	tool = sdk_tools.create_function_tool(
		"slack_send_message", "d", "x.y", {"type": "object", "properties": {}}, tool_type="Custom Function",
		requires_confirmation=flag,
	)
	return tool, calls


def invoke(tool, run=RUN, args="{}"):
	return asyncio.run(tool.on_invoke_tool({"agent_run_id": run}, args))
















# ---------------------------------------------------------------- JSON validation
def _load(rel):
	with open(os.path.join(ROOT, rel)) as f:
		return json.load(f)


class TestModule(SupportCase):
	# ---------------------------------------------------------------- context
	def test_non_gateway_run_unaffected(self):
		fk = self.use(_fx_fk)
		assert tp.check_tool_call("any", {}, "RUN-X", True) is None
		assert tp.check_tool_call("any", {}, "RUN-WEB", True) is None
		assert tp.check_tool_call("any", {}, None, True) is None

	def test_context_resolved_and_cached(self):
		fk = self.use(_fx_fk)
		assert tp.resolve_gateway_context(RUN) == {"gateway": "gw1", "channel": "C1", "event": "EV-1"}
		n = fk.db.calls
		tp.resolve_gateway_context(RUN)
		assert fk.db.calls == n

	def test_context_error_with_run_id_fails_closed(self):
		fk = self.use(_fx_fk)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(tp, "resolve_gateway_context", lambda r: (_ for _ in ()).throw(RuntimeError("x")))
		assert denied(tp.check_tool_call("t", {}, RUN, True))
		assert denied(tp.check_tool_call("t", {}, RUN, False))

	def test_context_error_without_run_id_unchanged(self):
		fk = self.use(_fx_fk)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(tp, "resolve_gateway_context", lambda r: (_ for _ in ()).throw(RuntimeError("x")))
		assert tp.check_tool_call("t", {}, None, True) is None

	def test_db_lookup_exception_fails_closed(self):
		fk = self.use(_fx_fk)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(fk.db, "get_value", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
		assert denied(tp.check_tool_call("t", {}, "RUN-NEW", False))

	def test_negative_cache_ttl_is_short(self):
		fk = self.use(_fx_fk)
		assert tp.resolve_gateway_context("RUN-X") is None
		assert fk.cache_obj.ttl["huf_a8_ctx:RUN-X"] <= 60
		tp.resolve_gateway_context(RUN)
		assert fk.cache_obj.ttl["huf_a8_ctx:" + RUN] > 60

	# ---------------------------------------------------------------- S8: new outbound tools
	def test_new_outbound_tools_listed(self):
		assert {"gateway_send", "gateway_reply", "gateway_handoff"} <= tp.SLACK_SEND_TOOLS

	def test_read_then_gateway_send_refused(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_get_channel_history", RUN)
		out = tp.check_tool_call("gateway_send", {"recipient": "user:bob", "text": "x"}, RUN)
		assert denied(out) and json.loads(out)["reason"] == "exfiltration_guard"

	def test_read_then_gateway_handoff_refused(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_search_messages", RUN)
		assert denied(tp.check_tool_call("gateway_handoff", {"summary": "x"}, RUN))

	def test_read_then_gateway_reply_to_origin_allowed(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_search_messages", RUN)
		assert tp.check_tool_call("gateway_reply", {"text": "x"}, RUN) is None

	def test_gateway_send_allowed_by_cross_channel_policy(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(mode=tp.DENY, tools="", cross=1)]
		tp.note_tool_executed("slack_search_messages", RUN)
		assert tp.check_tool_call("gateway_send", {"recipient": "user:bob"}, RUN) is None

	# ---------------------------------------------------------------- confirmation flag
	def test_flag_off_gateway_run_runs(self):
		fk = self.use(_fx_fk)
		assert tp.check_tool_call("t", {}, RUN, False) is None

	def test_flag_on_without_confirmer_refused(self):
		fk = self.use(_fx_fk)
		out = tp.check_tool_call("t", {}, RUN, True)
		assert denied(out) and json.loads(out)["requires_confirmation"] is True

	def test_flag_on_confirmer_gets_call_and_result_returned(self):
		fk = self.use(_fx_fk)
		seen = []
		tp.set_confirmer(lambda ctx, tool, args: seen.append((ctx["gateway"], tool, args)) or {"status": "pending"})
		out = tp.check_tool_call("t", {"a": 1}, RUN, True)
		assert json.loads(out) == {"status": "pending"}
		assert seen == [("gw1", "t", {"a": 1})]

	def test_confirmer_returning_none_refuses(self):
		fk = self.use(_fx_fk)
		tp.set_confirmer(lambda *a: None)
		assert denied(tp.check_tool_call("t", {}, RUN, True))

	def test_confirmer_exception_fails_closed(self):
		fk = self.use(_fx_fk)
		def boom(*a):
			raise RuntimeError("x")

		tp.set_confirmer(boom)
		assert denied(tp.check_tool_call("t", {}, RUN, True))

	# ---------------------------------------------------------------- policy semantics
	def test_no_policy_no_restriction(self):
		fk = self.use(_fx_fk)
		assert tp.get_allowed_tools("gw1", {"conversation_id": "C1"}) is None
		assert tp.is_tool_allowed("gw1", {"conversation_id": "C1"}, "anything")

	def test_allow_list(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(tools="a\nb, c")]
		ev = {"conversation_id": "C1"}
		assert tp.get_allowed_tools("gw1", ev) == {"a", "b", "c"}
		assert tp.is_tool_allowed("gw1", ev, "a") and not tp.is_tool_allowed("gw1", ev, "z")
		assert denied(tp.check_tool_call("z", {}, RUN))
		assert tp.check_tool_call("a", {}, RUN) is None

	def test_deny_list(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(mode=tp.DENY, tools="bad")]
		ev = {"conversation_id": "C1"}
		assert tp.get_allowed_tools("gw1", ev) is None
		assert not tp.is_tool_allowed("gw1", ev, "bad") and tp.is_tool_allowed("gw1", ev, "ok")
		assert denied(tp.check_tool_call("bad", {}, RUN))

	def test_channel_scope_overrides_gateway_wide(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(tools="a"), pol(scope="C1", mode=tp.DENY, tools="a")]
		assert not tp.is_tool_allowed("gw1", {"conversation_id": "C1"}, "a")
		assert tp.is_tool_allowed("gw1", {"conversation_id": "C2"}, "a")
		assert not tp.is_tool_allowed("gw1", {"conversation_id": "C2"}, "b")

	def test_other_gateway_policy_ignored(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(gateway="other", tools="a")]
		assert tp.is_tool_allowed("gw1", {"conversation_id": "C1"}, "z")

	def test_sanitized_name_matches(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(mode=tp.DENY, tools="my tool")]
		assert not tp.is_tool_allowed("gw1", {"conversation_id": "C1"}, "my_tool")

	def test_policy_beats_confirmation_order(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(tools="a")]
		tp.set_confirmer(lambda *a: {"ok": 1})
		assert "not allowed" in json.loads(tp.check_tool_call("z", {}, RUN, True))["error"]

	def test_policy_error_fails_closed(self):
		fk = self.use(_fx_fk)
		monkeypatch = self.monkeypatch
		monkeypatch.setattr(tp, "is_tool_allowed", lambda *a: (_ for _ in ()).throw(RuntimeError("db")))
		assert denied(tp.check_tool_call("t", {}, RUN))

	# ---------------------------------------------------------------- exfil guard
	def test_send_before_read_ok(self):
		fk = self.use(_fx_fk)
		assert tp.check_tool_call("slack_send_message", {"channel": "C9"}, RUN) is None

	def test_read_then_send_other_channel_refused(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_get_channel_history", RUN)
		out = tp.check_tool_call("slack_send_message", {"channel": "C9"}, RUN)
		assert denied(out) and json.loads(out)["reason"] == "exfiltration_guard"

	def test_search_also_arms(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_search_messages", RUN)
		assert denied(tp.check_tool_call("slack_send_thread_reply", {"channel": "C9"}, RUN))

	def test_read_then_send_same_channel_ok(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_search_messages", RUN)
		assert tp.check_tool_call("slack_send_message", {"channel": "C1"}, RUN) is None

	def test_read_then_send_without_channel_refused(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_search_messages", RUN)
		assert denied(tp.check_tool_call("slack_send_message", {}, RUN))

	def test_policy_allows_cross_channel(self):
		fk = self.use(_fx_fk)
		fk.policies = [pol(mode=tp.DENY, tools="", cross=1)]
		tp.note_tool_executed("slack_get_channel_history", RUN)
		assert tp.check_tool_call("slack_send_message", {"channel": "C9"}, RUN) is None

	def test_guard_is_per_run(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_get_channel_history", RUN)
		fk.db.runs["RUN-2"] = "gw:EV-1"
		assert tp.check_tool_call("slack_send_message", {"channel": "C9"}, "RUN-2") is None

	def test_non_read_tool_does_not_arm_and_non_gateway_ignored(self):
		fk = self.use(_fx_fk)
		tp.note_tool_executed("slack_list_channels", RUN)
		tp.note_tool_executed("slack_search_messages", "RUN-X")
		assert tp.check_tool_call("slack_send_message", {"channel": "C9"}, RUN) is None

	def test_wrapper_flag_off_executes(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, False)
		assert json.loads(invoke(tool)) == {"ok": True} and len(calls) == 1

	def test_wrapper_flag_on_gateway_not_executed(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, True)
		assert denied(invoke(tool)) and calls == []

	def test_wrapper_flag_on_non_gateway_executes(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, True)
		assert json.loads(invoke(tool, "RUN-X")) == {"ok": True} and len(calls) == 1

	def test_wrapper_no_run_context_executes(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, True)
		assert json.loads(asyncio.run(tool.on_invoke_tool(None, "{}"))) == {"ok": True}

	def test_wrapper_llm_cannot_spoof_run_id(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, True)
		out = invoke(tool, RUN, json.dumps({"agent_run_id": "RUN-X"}))
		assert denied(out) and calls == []

	def test_wrapper_read_then_send_blocked(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, False)
		tp.note_tool_executed("slack_get_channel_history", RUN)
		assert denied(invoke(tool, RUN, json.dumps({"channel": "C9"}))) and calls == []

	def test_wrapper_marks_read_after_execution(self):
		monkeypatch = self.monkeypatch
		fk = self.use(_fx_fk)
		tool, calls = make_tool(monkeypatch, fk, False)
		tool.name  # noqa: B018
		monkeypatch.setattr(tp, "SLACK_READ_TOOLS", frozenset({"slack_send_message"}))
		invoke(tool)
		assert fk.cache_obj.get_value(f"{tp._READ_PREFIX}{RUN}") == 1

	def test_field_order_matches_fields(self):
		for rel in [
		"huf/huf/doctype/agent_tool_function/agent_tool_function.json",
		"huf/huf/doctype/gateway_tool_policy/gateway_tool_policy.json",
	]:
			with self.subTest(rel=rel):
				d = _load(rel)
				names = [f["fieldname"] for f in d["fields"] if f["fieldtype"] != "Section Break" or f["fieldname"]]
				assert len(set(d["field_order"])) == len(d["field_order"])
				assert set(d["field_order"]) == {f["fieldname"] for f in d["fields"]}
				assert names

	def test_requires_confirmation_field_shape(self):
		d = _load("huf/huf/doctype/agent_tool_function/agent_tool_function.json")
		f = next(x for x in d["fields"] if x["fieldname"] == "requires_confirmation")
		assert f["fieldtype"] == "Check" and str(f["default"]) == "0"
		assert d["field_order"].index("requires_confirmation") == d["field_order"].index("allowed_for_guest") + 1

	def test_policy_doctype_system_manager_only(self):
		d = _load("huf/huf/doctype/gateway_tool_policy/gateway_tool_policy.json")
		assert {p["role"] for p in d["permissions"]} == {"System Manager"}
