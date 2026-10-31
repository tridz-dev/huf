import json
import sys
import types
from types import SimpleNamespace

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

import pathlib as _pl  # noqa: E402

_REPO = _pl.Path(__file__).resolve().parents[3]

from huf.ai.gateways import flow_reply
from huf.ai.tools.gateways import reply as tool


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v


class World:
	"""Minimal frappe stand-in: one Flow Run, one Gateway Event, one Gateway."""

	def __init__(self, run_status="Failed", payload=None, event_flow_run="FR-1", conv="C1"):
		self.runs = {"FR-1": {"trigger_payload": json.dumps(payload if payload is not None else {"gateway_event": "GE-1", "message": "hi"}), "status": run_status}}
		self.agent_runs = {"AR-1": "FR-1"}
		self.event = SimpleNamespace(name="GE-1", gateway="GW-1", flow_run=event_flow_run, conversation_id=conv, thread_id="T1")
		self.gateway = SimpleNamespace(name="GW-1", provider="Slack")
		self.sent = []
		self.cache = FakeCache()
		self.logged = []
		self.flagged = []  # Flow Run.replied_via_tool writes

	def get_value(self, doctype, name, fields=None, as_dict=False):
		if doctype == "Agent Run":
			return self.agent_runs.get(name)
		row = self.runs.get(name)
		return dict(row) if row else None

	def get_doc(self, doctype, name):
		return self.event if doctype == "Gateway Event" else self.gateway


def _fx_world(self):
	monkeypatch = self.monkeypatch
	w = World()
	fake_frappe = SimpleNamespace(
		db=SimpleNamespace(
			get_value=w.get_value,
			exists=lambda doctype, name=None: doctype == "Flow Run" and name in w.runs,
			set_value=lambda *a, **k: w.flagged.append(a),
		),
		get_doc=w.get_doc,
		cache=lambda: w.cache,
		log_error=lambda *a, **k: w.logged.append(a),
		get_traceback=lambda: "Traceback secret internals",
	)
	monkeypatch.setattr(tool, "frappe", fake_frappe)
	monkeypatch.setattr(flow_reply, "frappe", fake_frappe)
	mod = types.ModuleType("huf.ai.gateway_webhook")
	mod.send_gateway_reply = lambda gateway, event, text: w.sent.append((gateway.name, event.conversation_id, event.thread_id, text))
	monkeypatch.setitem(sys.modules, "huf.ai.gateway_webhook", mod)
	return w






































def _doc(status, before_status="Running", has_before=True):
	before = SimpleNamespace(status=before_status) if has_before else None
	return SimpleNamespace(
		name="FR-1", status=status,
		trigger_payload=json.dumps({"gateway_event": "GE-1"}),
		get_doc_before_save=lambda: before,
	)


class TestModule(SupportCase):
	def test_tool_sends_only_to_origin(self):
		world = self.use(_fx_world)
		out = json.loads(tool.handle_gateway_reply("hello", flow_run_id="FR-1"))
		assert out["success"] is True
		assert world.sent == [("GW-1", "C1", "T1", "hello")]
		assert world.flagged == [("Flow Run", "FR-1", "replied_via_tool", 1)]

	def test_tool_resolves_via_agent_run(self):
		world = self.use(_fx_world)
		assert json.loads(tool.handle_gateway_reply("hi", agent_run_id="AR-1"))["success"] is True
		assert len(world.sent) == 1

	def test_tool_ignores_destination_arguments(self):
		world = self.use(_fx_world)
		tool.handle_gateway_reply("hi", flow_run_id="FR-1", conversation_id="OTHER", channel="X", gateway="Y")
		assert world.sent[0][1] == "C1"

	def test_tool_refuses_without_gateway_context(self):
		world = self.use(_fx_world)
		out = json.loads(tool.handle_gateway_reply("hi"))
		assert out["success"] is False and world.sent == []

	def test_tool_refuses_non_gateway_run(self):
		world = self.use(_fx_world)
		world.runs["FR-1"]["trigger_payload"] = json.dumps({"message": "x"})
		assert json.loads(tool.handle_gateway_reply("hi", flow_run_id="FR-1"))["success"] is False
		assert world.sent == []

	def test_tool_refuses_when_event_not_linked_to_run(self):
		world = self.use(_fx_world)
		world.event.flow_run = "FR-OTHER"
		assert json.loads(tool.handle_gateway_reply("hi", flow_run_id="FR-1"))["success"] is False
		assert world.sent == []

	def test_tool_refuses_bad_payload_json(self):
		world = self.use(_fx_world)
		world.runs["FR-1"]["trigger_payload"] = "{not json"
		assert json.loads(tool.handle_gateway_reply("hi", flow_run_id="FR-1"))["success"] is False

	def test_tool_empty_text_refused(self):
		world = self.use(_fx_world)
		assert json.loads(tool.handle_gateway_reply("   ", flow_run_id="FR-1"))["success"] is False
		assert world.sent == []

	def test_length_cap(self):
		world = self.use(_fx_world)
		tool.handle_gateway_reply("a" * 10000, flow_run_id="FR-1")
		assert len(world.sent[0][3]) == tool.MAX_REPLY_CHARS

	def test_escaping_blocks_mass_mentions(self):
		s = tool.safe_text("<!channel> <@U1> a & b")
		assert "<" not in s and ">" not in s
		assert "&lt;!channel&gt;" in s and "&amp;" in s

	def test_tool_never_raises_and_hides_internals(self):
		world = self.use(_fx_world)
		monkeypatch = self.monkeypatch
		def boom(*a, **k):
			raise RuntimeError("token xoxb-secret")

		sys.modules["huf.ai.gateway_webhook"].send_gateway_reply = boom
		raw = tool.handle_gateway_reply("hi", flow_run_id="FR-1")
		assert "xoxb" not in raw and json.loads(raw)["success"] is False

	def test_tool_returns_json_string(self):
		world = self.use(_fx_world)
		assert isinstance(tool.handle_gateway_reply("x", flow_run_id="FR-1"), str)

	def test_tool_definition_shape(self):
		d = tool.GATEWAY_REPLY_TOOLS[0]
		assert d["tool_name"] == "gateway_reply" and d["function_path"].endswith("handle_gateway_reply")
		assert {p["fieldname"] for p in d["parameters"]} == {"text", "flow_run_id"}

	def test_failure_notice_sent_once(self):
		world = self.use(_fx_world)
		assert flow_reply.notify_flow_failure("FR-1") is True
		assert flow_reply.notify_flow_failure("FR-1") is False
		assert len(world.sent) == 1

	def test_failure_notice_has_no_internal_text(self):
		world = self.use(_fx_world)
		flow_reply.notify_flow_failure("FR-1")
		text = world.sent[0][3]
		assert text == "Something went wrong. Ref GE-1."
		assert "Traceback" not in text

	def test_non_gateway_failed_run_ignored(self):
		world = self.use(_fx_world)
		world.runs["FR-1"]["trigger_payload"] = json.dumps({"x": 1})
		assert flow_reply.notify_flow_failure("FR-1") is False
		assert world.sent == []

	def test_non_failed_run_ignored(self):
		world = self.use(_fx_world)
		world.runs["FR-1"]["status"] = "Running"
		assert flow_reply.notify_flow_failure("FR-1") is False

	def test_failure_notice_never_raises(self):
		world = self.use(_fx_world)
		sys.modules["huf.ai.gateway_webhook"].send_gateway_reply = lambda *a: 1 / 0
		assert flow_reply.notify_flow_failure("FR-1") is False
		assert flow_reply.notify_flow_failure(None) is False

	def test_transition_to_failed_triggers(self):
		world = self.use(_fx_world)
		flow_reply.on_flow_run_update(_doc("Failed"))
		assert len(world.sent) == 1

	def test_already_failed_does_not_retrigger(self):
		world = self.use(_fx_world)
		flow_reply.on_flow_run_update(_doc("Failed", before_status="Failed"))
		assert world.sent == []

	def test_other_status_ignored(self):
		world = self.use(_fx_world)
		flow_reply.on_flow_run_update(_doc("Success"))
		assert world.sent == []

	def test_doc_event_never_raises(self):
		world = self.use(_fx_world)
		flow_reply.on_flow_run_update(object())
		flow_reply.on_flow_run_update(None)

	def test_hooks_registered(self):
		src = open(_REPO / "huf/hooks.py").read()
		assert "huf.ai.gateways.flow_reply.on_flow_run_update" in src
		assert "huf.ai.tools.gateways.reply.GATEWAY_REPLY_TOOLS" in src
