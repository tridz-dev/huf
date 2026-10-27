import json
import sys
import types
from types import SimpleNamespace

import pytest

from huf.ai.gateways import recipients as rcp
from huf.ai.tools import gateway_handoff as tool
from huf.ai.tools import gateway_reply as reply_tool
from huf.ai.tools import gateway_send as send_tool


class PermErr(Exception):
	pass


class FakeCache:
	def __init__(self):
		self.d = {}

	def get_value(self, k):
		return self.d.get(k)

	def set_value(self, k, v, expires_in_sec=None):
		self.d[k] = v

	def delete_value(self, k):
		self.d.pop(k, None)


class FakeApi:
	def __init__(self, w):
		self.w = w

	def conversations_open(self, users):
		return "D" + users[0]

	def post_message(self, channel, text=None, **kw):
		self.w.posts.append((channel, text))


class FakeDoc:
	def __init__(self, w, data):
		self.w, self.data = w, data
		self.name = None

	def insert(self):
		if self.w.insert_error:
			raise self.w.insert_error
		self.name = f"TODO-{len(self.w.todos) + 1}"
		self.w.todos.append({**self.data, "name": self.name})
		return self


class World:
	def __init__(self):
		self.users = {"alice@x.com": 1, "bob@x.com": 1, "carol@x.com": 1, "off@x.com": 0}
		self.names = {"alice@x.com": "Alice A", "bob@x.com": "Bob B"}
		self.links = {"alice@x.com": "UALICE"}
		self.roles = {"Support": ["alice@x.com", "bob@x.com", "off@x.com"]}
		self.todos = []
		self.posts = []
		self.acks = []
		self.logged = []
		self.can_create = True
		self.insert_error = None
		self.origin = True
		self.cache = FakeCache()
		self.event = SimpleNamespace(name="GE-1", gateway="GW-1", conversation_id="C1", thread_id="T1")
		self.gateway = SimpleNamespace(name="GW-1", provider="Slack")

	def get_value(self, doctype, name, fields=None, *a, **k):
		if doctype == "User":
			if fields == "enabled":
				return self.users.get(name)
			if fields == "full_name":
				return self.names.get(name)
		return None

	def get_all(self, doctype, filters=None, pluck=None, limit=None, **kw):
		if doctype == "Has Role":
			return list(self.roles.get(filters["role"], []))
		if doctype == "Gateway Identity Link":
			sid = self.links.get(filters.get("user"))
			return [sid] if sid else []
		if doctype == "ToDo":
			return [t["name"] for t in self.todos
				if t.get("reference_name") == filters["reference_name"]
				and t["allocated_to"] == filters["allocated_to"] and t["status"] == filters["status"]]
		return []


@pytest.fixture
def world(monkeypatch):
	w = World()
	fake = SimpleNamespace(
		db=SimpleNamespace(get_value=w.get_value, exists=lambda *a, **k: True),
		get_all=w.get_all,
		get_doc=lambda d: FakeDoc(w, d),
		has_permission=lambda *a, **k: w.can_create,
		cache=lambda: w.cache,
		log_error=lambda *a, **k: w.logged.append(a),
		get_traceback=lambda: "Traceback secret",
		PermissionError=PermErr,
		session=SimpleNamespace(user="runner@x.com"),
	)
	for mod in (tool, send_tool, rcp, reply_tool):
		monkeypatch.setattr(mod, "frappe", fake)
	monkeypatch.setattr(rcp, "slack_id_for_user", lambda gw, user: w.links.get(user))
	monkeypatch.setattr(send_tool, "get_slack_api", lambda gw: FakeApi(w))
	monkeypatch.setattr(tool._reply, "resolve_origin",
		lambda fr=None, ar=None: (w.gateway, w.event, "FR-1") if w.origin else None)
	mod = types.ModuleType("huf.ai.gateway_webhook")
	mod.send_gateway_reply = lambda gw, ev, text: w.acks.append((ev.conversation_id, text))
	monkeypatch.setitem(sys.modules, "huf.ai.gateway_webhook", mod)
	return w


def run(**kw):
	kw.setdefault("assignee", {"user": "alice@x.com"})
	kw.setdefault("summary", "Customer wants a refund")
	return json.loads(tool.handle_gateway_handoff(**kw))


def test_tool_definition():
	t = tool.GATEWAY_HANDOFF_TOOLS[0]
	assert t["tool_name"] == "gateway_handoff"
	assert t["function_path"] == "huf.ai.tools.gateway_handoff.handle_gateway_handoff"


def test_user_assignee_creates_todo(world):
	out = run()
	assert out["success"] is True and out["todos"] == ["TODO-1"]
	todo = world.todos[0]
	assert todo["allocated_to"] == "alice@x.com"
	assert todo["reference_type"] == "Gateway Event" and todo["reference_name"] == "GE-1"
	assert "Customer wants a refund" in todo["description"]


def test_json_shape(world):
	out = run()
	assert set(["success", "todos", "notified", "skipped"]) <= set(out)


def test_role_creates_one_per_enabled_user(world):
	out = run(assignee={"role": "Support"})
	assert sorted(t["allocated_to"] for t in world.todos) == ["alice@x.com", "bob@x.com"]
	assert len(out["todos"]) == 2
	assert any(s["recipient"] == "off@x.com" for s in out["skipped"])


def test_role_cap(world):
	world.roles["Big"] = [f"u{i}@x.com" for i in range(8)]
	world.users.update({f"u{i}@x.com": 1 for i in range(8)})
	out = run(assignee={"role": "Big"})
	assert len(out["todos"]) == 5
	assert sum("cap" in s["reason"] for s in out["skipped"]) == 3


def test_empty_role(world):
	out = run(assignee={"role": "Nobody"})
	assert out["success"] is False and world.todos == []


def test_unsupported_assignee_kind(world):
	out = run(assignee={"channel": "C123"})
	assert out["success"] is False and world.todos == []


def test_bad_assignee_json(world):
	assert run(assignee="not json")["success"] is False


def test_disabled_user_rejected(world):
	assert run(assignee={"user": "off@x.com"})["success"] is False


def test_permission_denied_up_front(world):
	world.can_create = False
	out = run()
	assert out["success"] is False and "permission" in out["error"] and world.todos == []


def test_permission_error_on_insert(world):
	world.insert_error = PermErr()
	out = run()
	assert out["success"] is False and out["todos"] == []
	assert out["skipped"][0]["reason"].startswith("no permission")


def test_dedupe_existing_todo_for_event(world):
	run()
	again = run()
	assert len(world.todos) == 1
	assert again["todos"] == [] and again["success"] is True
	assert "already handed off" in again["skipped"][0]["reason"]


def test_dedupe_cache_without_event(world):
	world.origin = False
	run()
	run()
	assert len(world.todos) == 1


def test_failed_insert_releases_claim(world):
	world.insert_error = RuntimeError("db")
	run()
	world.insert_error = None
	assert run()["todos"] == ["TODO-1"]


def test_notify_linked(world):
	out = run()
	assert out["notified"] == ["alice@x.com"]
	assert world.posts[0][0] == "DUALICE" and "TODO-1" in world.posts[0][1]


def test_notify_unlinked_skipped(world):
	out = run(assignee={"user": "bob@x.com"})
	assert out["notified"] == [] and len(out["todos"]) == 1
	assert "no linked Slack identity" in out["skipped"][0]["reason"]
	assert world.posts == []


def test_ack_in_thread(world):
	out = run()
	assert out["acknowledged"] is True
	conv, text = world.acks[0]
	assert conv == "C1" and "Alice A" in text and "TODO-1" in text


def test_ack_does_not_leak_message_body(world):
	run(reason="secret reason")
	assert "secret reason" not in world.acks[0][1]


def test_no_gateway_context_todo_only(world):
	world.origin = False
	out = run()
	assert out["todos"] == ["TODO-1"] and out["notified"] == []
	assert world.acks == [] and world.posts == []
	assert "reference_type" not in world.todos[0]


def test_no_ack_when_nothing_created(world):
	world.can_create = False
	run()
	assert world.acks == []


def test_summary_and_reason_capped(world):
	run(summary="s" * 2000, reason="r" * 2000)
	desc = world.todos[0]["description"]
	assert len(desc) < tool.MAX_SUMMARY_CHARS + tool.MAX_REASON_CHARS + 100
	assert desc.count("...") == 2


def test_slack_text_escaped(world):
	run(summary="<!channel> hi <@U1> & co")
	text = world.posts[0][1]
	assert "<!channel>" not in text and "&lt;!channel&gt;" in text and "&amp;" in text


def test_due_date(world):
	run(due_in_days=3)
	assert world.todos[0]["date"]
	run(assignee={"user": "bob@x.com"}, due_in_days="bad")
	assert "date" not in world.todos[1]


def test_empty_summary(world):
	out = run(summary="   ")
	assert out["success"] is False and world.todos == []


def test_never_raises(world, monkeypatch):
	monkeypatch.setattr(tool, "_assignees", lambda a: 1 / 0)
	out = json.loads(tool.handle_gateway_handoff({"user": "a"}, "x"))
	assert out["success"] is False and "Traceback" not in json.dumps(out)
	assert world.logged
