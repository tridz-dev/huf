# ruff: noqa: S101
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from huf.ai.agent import access
from huf.ai.external import approvals, invoke, states
from huf.ai.external.tests.fake_frappe import FakeFrappe, patch_modules

APPROVAL = "External Action Approval"
SESSION = "External Agent Session"
EVENT = "External Agent Event"
CONNECTION = "External Agent Connection"

USER = "agent-user@example.com"
STRANGER = "stranger@example.com"
CONN = "CONN-1"
AGENT = "AGENT-1"
SESSION_NAME = "SESS-1"
RUN = "RUN-1"
CONVERSATION = "CONV-1"

ALLOW = "Allow"
APPROVE = "Requires Approval"
DENY = "Deny"

# Tool docs as resolve_tool_doc would return them, keyed by the model-facing tool name.
TOOLS = {
	"get_customer": {"name": "ATF-GET", "tool_name": "get_customer", "types": "Get Document"},
	"update_customer": {"name": "ATF-UPDATE", "tool_name": "update_customer", "types": "Update Document"},
	"send_mail": {"name": "ATF-MAIL", "tool_name": "send_mail", "types": "Send Email"},
	"run_script": {"name": "ATF-SCRIPT", "tool_name": "run_script", "types": "Code Execution"},
	"sub_agent": {"name": "ATF-SUBAGENT", "tool_name": "sub_agent", "types": "Run Agent"},
	"unlisted_read": {"name": "ATF-UNLISTED", "tool_name": "unlisted_read", "types": "Get Document"},
}
# Tools linked to the agent through Agent Tool child rows. "unlisted_read" is deliberately absent.
AGENT_TOOL_NAMES = ("ATF-GET", "ATF-UPDATE", "ATF-MAIL", "ATF-SCRIPT", "ATF-SUBAGENT")


class ToolResult:
	def __init__(self, data: dict) -> None:
		self.success = True
		self.data = data

	def as_dict(self) -> dict:
		return {"data": self.data}


class ToolStub:
	"""Stands in for invoke_tool_sync. Records every call and can be told to fail the next one."""

	def __init__(self) -> None:
		self.calls: list[dict] = []
		self.fail_next = False

	def __call__(self, tool_name, args, ctx=None, telemetry=False):
		self.calls.append({"tool": tool_name, "args": dict(args), "ctx": ctx})
		if self.fail_next:
			self.fail_next = False
			raise RuntimeError("backend unavailable")  # noqa: TRY003
		return ToolResult({"tool": tool_name})


def seed(fake: FakeFrappe, *, read: str = ALLOW, write: str = APPROVE, communicate: str = DENY) -> None:
	fake.get_doc(
		{
			"doctype": CONNECTION,
			"name": CONN,
			"user": USER,
			"agent": AGENT,
			"enabled": 1,
			"mode": "Managed",
			"read_policy": read,
			"write_policy": write,
			"communicate_policy": communicate,
		}
	).insert()
	fake.get_doc(
		{
			"doctype": "Agent",
			"name": AGENT,
			"owner": USER,
			"allow_all_users": 1,
			"allowed_users": [],
			"allowed_roles": [],
		}
	).insert()
	for docname in AGENT_TOOL_NAMES:
		fake.get_doc(
			{
				"doctype": "Agent Tool",
				"parent": AGENT,
				"parenttype": "Agent",
				"parentfield": "agent_tool",
				"tool": docname,
			}
		).insert()
	fake.get_doc(
		{
			"doctype": SESSION,
			"name": SESSION_NAME,
			"connection": CONN,
			"user": USER,
			"agent": AGENT,
			"conversation": CONVERSATION,
			"agent_run": RUN,
			"state": states.ACTIVE,
			"last_seq": 0,
			"acked_seq": 0,
		}
	).insert()


@pytest.fixture
def fake(monkeypatch) -> FakeFrappe:
	frappe_fake = FakeFrappe(user=USER)
	patch_modules(monkeypatch, frappe_fake)
	monkeypatch.setattr(access, "frappe", frappe_fake)
	seed(frappe_fake)
	return frappe_fake


@pytest.fixture
def stub(monkeypatch) -> ToolStub:
	tool_stub = ToolStub()
	monkeypatch.setattr(invoke, "invoke_tool_sync", tool_stub)
	monkeypatch.setattr(invoke, "resolve_tool_doc", lambda name: _resolve(name))
	monkeypatch.setattr(
		invoke, "check_tool_permission", lambda tool_type, allowed_for_guest=False: {"allowed": True}
	)
	return tool_stub


def _resolve(name: str) -> dict | None:
	tool = TOOLS.get(name)
	if tool is None:
		return None
	return {**tool, "function_path": None, "function_name": None, "agent": None}


def call(fake: FakeFrappe, tool: str, args: dict | None = None, call_id: str | None = None) -> dict:
	session_doc = fake.get_doc(SESSION, SESSION_NAME)
	return invoke.external_invoke(session_doc, tool, args, client_call_id=call_id)


def approval_status(fake: FakeFrappe, name: str) -> str:
	return fake.db.get_value(APPROVAL, name, "status")


def session_state(fake: FakeFrappe) -> str:
	return fake.db.get_value(SESSION, SESSION_NAME, "state")


def approval_count(fake: FakeFrappe) -> int:
	return fake.db.count(APPROVAL)


UPDATE_ARGS = {"name": "CUST-1", "status": "Open"}


def test_read_tool_executes_and_model_identity_never_reaches_the_tool(fake, stub):
	result = call(
		fake,
		"get_customer",
		{
			"name": "CUST-1",
			"user": "Administrator",
			"agent_run_id": "forged-run",
			"Agent-Run-Id": "forged-run-2",
			"ignore_permissions": True,
			"conversation_id": "forged-conv",
		},
		call_id="r1",
	)

	assert result["status"] == "ok"
	assert result["action_class"] == "read"
	assert result["data"] == {"tool": "get_customer"}
	assert len(stub.calls) == 1
	received = stub.calls[0]["args"]
	assert received["name"] == "CUST-1"
	for removed in ("user", "ignore_permissions"):
		assert removed not in received
	assert received["agent_run_id"] == RUN
	assert received["conversation_id"] == CONVERSATION
	assert received["agent_name"] == AGENT
	assert isinstance(received["call_id"], str)
	assert len(received["call_id"]) == 40
	ctx = stub.calls[0]["ctx"]
	assert ctx.user == USER
	assert ctx.agent_run_id == RUN
	assert approval_count(fake) == 0


def test_write_tool_requires_approval_and_is_not_executed(fake, stub):
	first = call(fake, "update_customer", UPDATE_ARGS, call_id="w1")
	second = call(fake, "update_customer", UPDATE_ARGS, call_id="w2")

	assert first["status"] == "approval_required"
	assert first["action_class"] == "write"
	assert second["status"] == "approval_required"
	assert second["approval"] == first["approval"]
	assert approval_count(fake) == 1
	assert approval_status(fake, first["approval"]) == "Pending"
	assert stub.calls == []
	assert session_state(fake) == states.WAITING_APPROVAL


def test_approved_call_executes_once_and_consumes_the_approval(fake, stub):
	pending = call(fake, "update_customer", UPDATE_ARGS, call_id="a1")
	decided = approvals.decide_approval(pending["approval"], approve=True)
	assert decided["status"] == "Approved"
	assert session_state(fake) == states.ACTIVE

	executed = call(fake, "update_customer", UPDATE_ARGS, call_id="a2")

	assert executed["status"] == "ok"
	assert len(stub.calls) == 1
	assert approval_status(fake, pending["approval"]) == "Consumed"

	again = call(fake, "update_customer", UPDATE_ARGS, call_id="a3")
	assert again["status"] == "approval_required"
	assert again["approval"] != pending["approval"]
	assert approval_count(fake) == 2
	assert len(stub.calls) == 1


def test_changed_arguments_need_a_fresh_approval(fake, stub):
	first = call(fake, "update_customer", {"name": "C-4", "status": "A"}, call_id="c1")
	approvals.decide_approval(first["approval"], approve=True)

	changed = call(fake, "update_customer", {"name": "C-4", "status": "B"}, call_id="c2")

	assert changed["status"] == "approval_required"
	assert changed["approval"] != first["approval"]
	assert approval_status(fake, first["approval"]) == "Approved"
	assert stub.calls == []

	original = call(fake, "update_customer", {"name": "C-4", "status": "A"}, call_id="c3")
	assert original["status"] == "ok"
	assert approval_status(fake, first["approval"]) == "Consumed"
	assert len(stub.calls) == 1


def test_rejected_approval_keeps_the_call_blocked(fake, stub):
	first = call(fake, "update_customer", UPDATE_ARGS, call_id="j1")
	decided = approvals.decide_approval(first["approval"], approve=False, comment="no")
	assert decided["status"] == "Rejected"

	retry = call(fake, "update_customer", UPDATE_ARGS, call_id="j2")

	assert retry["status"] == "approval_required"
	assert approval_status(fake, first["approval"]) == "Rejected"
	assert stub.calls == []


def test_deny_policy_returns_denied_without_an_approval(fake, stub):
	result = call(fake, "send_mail", {"to": "x@example.com"}, call_id="d1")

	assert result["status"] == "denied"
	assert result["action_class"] == "communicate"
	assert approval_count(fake) == 0
	assert stub.calls == []


def test_unknown_tool_is_refused_before_execution(fake, stub):
	result = call(fake, "does_not_exist", {}, call_id="u1")

	# Unknown names report an error (not a policy denial); the point is that nothing runs.
	assert result["status"] == "error"
	assert result["error"] == invoke.UNKNOWN_TOOL_ERROR
	assert stub.calls == []


def test_tool_not_linked_to_the_agent_is_denied(fake, stub):
	result = call(fake, "unlisted_read", {"name": "CUST-1"}, call_id="n1")

	assert result["status"] == "denied"
	assert stub.calls == []


def test_disabled_connection_is_denied(fake, stub):
	fake.db.set_value(CONNECTION, CONN, "enabled", 0)

	result = call(fake, "get_customer", {"name": "CUST-1"}, call_id="x1")

	assert result["status"] == "denied"
	assert stub.calls == []


def test_different_session_user_is_denied(fake, stub):
	fake.session.user = STRANGER

	result = call(fake, "get_customer", {"name": "CUST-1"}, call_id="o1")

	assert result["status"] == "denied"
	assert stub.calls == []


@pytest.mark.parametrize("tool", ["run_script", "sub_agent"])
def test_code_execution_and_run_agent_are_denied_even_when_policy_allows(fake, stub, tool):
	fake.db.set_value(
		CONNECTION, CONN, {"read_policy": ALLOW, "write_policy": ALLOW, "communicate_policy": ALLOW}
	)

	result = call(fake, tool, {}, call_id="b1")

	assert result["status"] == "denied"
	assert approval_count(fake) == 0
	assert stub.calls == []


def test_replay_with_same_client_call_id_returns_stored_result_without_rerunning(fake, stub):
	first = call(fake, "get_customer", {"name": "CUST-1"}, call_id="dup")
	second = call(fake, "get_customer", {"name": "CUST-1"}, call_id="dup")

	assert first["status"] == "ok"
	assert second["replayed"] is True
	assert second["data"] == first["data"]
	assert len(stub.calls) == 1


def test_replay_of_an_approved_write_does_not_consume_or_rerun(fake, stub):
	pending = call(fake, "update_customer", UPDATE_ARGS, call_id="p0")
	approvals.decide_approval(pending["approval"], approve=True)

	first = call(fake, "update_customer", UPDATE_ARGS, call_id="p1")
	replay = call(fake, "update_customer", UPDATE_ARGS, call_id="p1")

	assert first["status"] == "ok"
	assert replay["replayed"] is True
	assert replay["data"] == first["data"]
	assert len(stub.calls) == 1
	assert approval_status(fake, pending["approval"]) == "Consumed"
	assert approval_count(fake) == 1


def test_stranger_cannot_decide_an_approval_but_a_system_manager_can(fake, stub):
	pending = call(fake, "update_customer", UPDATE_ARGS, call_id="s1")

	fake.session.user = STRANGER
	with pytest.raises(FakeFrappe.PermissionError):
		approvals.decide_approval(pending["approval"], approve=True)
	assert approval_status(fake, pending["approval"]) == "Pending"

	fake.roles[STRANGER] = ["System Manager"]
	decided = approvals.decide_approval(pending["approval"], approve=True)
	assert decided["status"] == "Approved"


def test_expire_pending_approvals_expires_old_ones_and_notifies_the_agent(fake, stub):
	start = fake.now
	first = call(fake, "update_customer", {"name": "C-5", "status": "A"}, call_id="e1")
	fake.now = start + timedelta(minutes=20)
	second = call(fake, "update_customer", {"name": "C-5", "status": "B"}, call_id="e2")

	fake.now = start + timedelta(minutes=31)
	approvals.expire_pending_approvals()

	assert approval_status(fake, first["approval"]) == "Expired"
	assert approval_status(fake, second["approval"]) == "Pending"
	assert session_state(fake) == states.WAITING_APPROVAL

	fake.now = start + timedelta(minutes=51)
	approvals.expire_pending_approvals()

	assert approval_status(fake, second["approval"]) == "Expired"
	assert session_state(fake) == states.ACTIVE
	events = fake.get_all(EVENT, filters={"session": SESSION_NAME, "event_type": "approval_decided"})
	notified = sorted(
		(json.loads(row.payload)["approval"], json.loads(row.payload)["status"]) for row in events
	)
	assert notified == sorted([(first["approval"], "Expired"), (second["approval"], "Expired")])
	assert stub.calls == []


def test_consume_restore_after_failed_execution_makes_the_approval_usable_again(fake, stub):
	pending = call(fake, "update_customer", UPDATE_ARGS, call_id="f0")
	approvals.decide_approval(pending["approval"], approve=True)

	stub.fail_next = True
	failed = call(fake, "update_customer", UPDATE_ARGS, call_id="f1")

	assert failed["status"] == "error"
	assert failed["error"] == invoke.EXECUTION_ERROR
	assert len(stub.calls) == 1
	assert approval_status(fake, pending["approval"]) == "Approved"

	retried = call(fake, "update_customer", UPDATE_ARGS, call_id="f2")

	assert retried["status"] == "ok"
	assert len(stub.calls) == 2
	assert approval_status(fake, pending["approval"]) == "Consumed"
	assert approval_count(fake) == 1


def test_deciding_an_expired_approval_still_returns_the_session_to_active(fake, stub):
	start = fake.now
	pending = call(fake, "update_customer", UPDATE_ARGS, call_id="x0")

	fake.now = start + timedelta(minutes=31)
	with pytest.raises(FakeFrappe.ValidationError):
		approvals.decide_approval(pending["approval"], approve=True)
	approvals.expire_pending_approvals()

	assert approval_status(fake, pending["approval"]) == "Expired"
	assert session_state(fake) == states.ACTIVE
	assert stub.calls == []
