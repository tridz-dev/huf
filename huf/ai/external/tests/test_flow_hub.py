# ruff: noqa: S101
from __future__ import annotations

import json

import pytest

from huf.ai.external import dispatch, hub
from huf.ai.external.core import jsonrpc, states
from huf.ai.external.tests.fake_frappe import FakeFrappe, patch_modules

SESSION = "External Agent Session"
CONNECTION = "External Agent Connection"
RUN = "Agent Run"
TOKEN = "tok-hub-secret-4d1e07"  # noqa: S105 - fixture value, never a real credential
SEVEN_TOOLS = {
	"huf_discover",
	"huf_context",
	"huf_invoke",
	"huf_surface",
	"huf_wait",
	"huf_report",
	"huf_complete",
}
SIX_BUILD_TOOLS = {
	"huf_find_agents",
	"huf_find_tools",
	"huf_find_tables",
	"huf_create_agent",
	"huf_create_tool",
	"huf_create_table",
}


@pytest.fixture
def fake(monkeypatch) -> FakeFrappe:
	fake = FakeFrappe()
	patch_modules(monkeypatch, fake)
	return fake


def make_session(fake: FakeFrappe, hub_tier):
	fake.get_doc({"doctype": CONNECTION, "name": "C1", "hub_tier": hub_tier}).insert()
	fake.get_doc(
		{
			"doctype": SESSION,
			"name": "S1",
			"state": states.ACTIVE,
			"connection": "C1",
			"user": fake.session.user,
			"agent": "A1",
			"conversation": "CONV1",
			"agent_run": "R1",
			"session_token": TOKEN,
			"last_seq": 0,
			"acked_seq": 0,
		}
	).insert()
	fake.get_doc({"doctype": RUN, "name": "R1", "status": "Started", "response": None}).insert()
	return fake.get_doc(SESSION, "S1")


@pytest.fixture
def hub_calls(monkeypatch) -> list[dict]:
	"""Replace hub.dispatch_hub with a recorder that answers ok. Tests may swap in another stub."""
	calls: list[dict] = []

	def stub(name, arguments, session_doc, tier):
		calls.append({"name": name, "arguments": arguments, "session_doc": session_doc, "tier": tier})
		return {"status": "ok", "result": {}}

	monkeypatch.setattr(hub, "dispatch_hub", stub)
	return calls


def call(session, name: str, arguments=None, request_id: int = 1) -> dict:
	params: dict = {"name": name}
	if arguments is not None:
		params["arguments"] = arguments
	request = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": params}
	return dispatch.handle_rpc(request, session)


def list_names(session) -> list[str]:
	response = dispatch.handle_rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/list"}, session)
	return [tool["name"] for tool in response["result"]["tools"]]


def tool_text(response: dict) -> dict:
	return json.loads(response["result"]["content"][0]["text"])


def test_tier_off_lists_only_the_seven_base_tools(fake):
	session = make_session(fake, "Off")

	assert set(list_names(session)) == SEVEN_TOOLS


def test_tier_off_hub_call_gets_the_same_error_as_a_missing_tool(fake, hub_calls):
	session = make_session(fake, "Off")

	hidden = call(session, "huf_find_agents", {"query": "invoices"})
	missing = call(session, "huf_no_such_tool", {"query": "invoices"})

	assert hidden["error"]["code"] == jsonrpc.INVALID_PARAMS
	assert hidden["error"] == missing["error"]
	assert hub_calls == []


def test_tier_build_lists_thirteen_tools(fake):
	session = make_session(fake, "Build")

	names = list_names(session)

	assert len(names) == 13
	assert set(names) == SEVEN_TOOLS | SIX_BUILD_TOOLS


def test_tier_build_find_agents_reaches_dispatch_with_the_build_tier(fake, hub_calls):
	session = make_session(fake, "Build")

	response = call(session, "huf_find_agents", {"query": "invoices", "limit": 3})

	assert "error" not in response
	assert response["result"]["isError"] is False
	assert tool_text(response) == {"status": "ok", "result": {}}
	assert len(hub_calls) == 1
	assert hub_calls[0]["name"] == "huf_find_agents"
	assert hub_calls[0]["tier"] == "Build"
	assert hub_calls[0]["arguments"] == {"query": "invoices", "limit": 3}


def test_tier_build_hides_admin_only_build_app(fake, hub_calls):
	session = make_session(fake, "Build")

	response = call(session, "huf_build_app", {"action": "create", "spec": {}})

	assert response["error"]["code"] == jsonrpc.INVALID_PARAMS
	assert response["error"] == call(session, "huf_no_such_tool")["error"]
	assert hub_calls == []


def test_tier_admin_lists_fourteen_tools_and_reaches_build_app(fake, hub_calls):
	session = make_session(fake, "Admin")

	assert len(list_names(session)) == 14
	assert "huf_build_app" in list_names(session)

	response = call(session, "huf_build_app", {"action": "create", "spec": {"title": "Ledger"}})

	assert response["result"]["isError"] is False
	assert len(hub_calls) == 1
	assert hub_calls[0]["name"] == "huf_build_app"
	assert hub_calls[0]["tier"] == "Admin"


@pytest.mark.parametrize("stored", ["Bogus", "", "admin", ["Build"]])
def test_invalid_stored_tier_is_treated_as_off(fake, hub_calls, stored):
	session = make_session(fake, stored)

	assert set(list_names(session)) == SEVEN_TOOLS
	response = call(session, "huf_find_agents", {"query": "x"})

	assert response["error"]["code"] == jsonrpc.INVALID_PARAMS
	assert hub_calls == []


def test_missing_connection_tier_is_treated_as_off(fake, hub_calls):
	session = make_session(fake, None)

	assert set(list_names(session)) == SEVEN_TOOLS
	assert call(session, "huf_find_tools", {})["error"]["code"] == jsonrpc.INVALID_PARAMS
	assert hub_calls == []


def test_model_arguments_never_replace_the_authorised_session(fake, hub_calls):
	session = make_session(fake, "Admin")

	call(
		session,
		"huf_find_agents",
		{"query": "x", "user": "attacker@example.com", "agent": "A-OTHER", "session": "S2"},
	)

	assert len(hub_calls) == 1
	assert hub_calls[0]["session_doc"] is session
	assert hub_calls[0]["session_doc"].user == fake.session.user
	assert hub_calls[0]["session_doc"].agent == "A1"


def test_approval_required_keeps_is_error_false(fake, hub_calls, monkeypatch):
	session = make_session(fake, "Build")
	pending = {"status": "approval_required", "approval": {"name": "APR-1"}, "action_class": "write"}
	monkeypatch.setattr(hub, "dispatch_hub", lambda *_args: pending)

	response = call(session, "huf_create_agent", {"name": "Helper", "instructions": "Be brief."})

	assert response["result"]["isError"] is False
	assert tool_text(response) == pending


@pytest.mark.parametrize("status", ["error", "denied"])
def test_error_and_denied_statuses_set_is_error(fake, monkeypatch, status):
	session = make_session(fake, "Build")
	monkeypatch.setattr(hub, "dispatch_hub", lambda *_args: {"status": status, "error": "x"})

	response = call(session, "huf_find_tables", {})

	assert response["result"]["isError"] is True


def test_hub_permission_error_yields_generic_denial_and_rolls_back(fake, monkeypatch):
	session = make_session(fake, "Build")

	def refuse(*_args):
		raise FakeFrappe.PermissionError("internal detail: role missing")  # noqa: TRY003

	monkeypatch.setattr(hub, "dispatch_hub", refuse)
	before = fake.db.rollbacks

	response = call(session, "huf_create_tool", {"spec": {}})

	assert response["result"]["isError"] is True
	assert tool_text(response) == {"status": "denied", "error": "Not permitted"}
	assert "internal detail" not in json.dumps(response)
	assert fake.db.rollbacks == before + 1


def test_hub_unexpected_exception_yields_generic_error_and_logs(fake, monkeypatch):
	session = make_session(fake, "Build")

	def explode(*_args):
		raise RuntimeError("database password is hunter2")  # noqa: TRY003

	monkeypatch.setattr(hub, "dispatch_hub", explode)
	before = fake.db.rollbacks

	response = call(session, "huf_create_table", {"spec": {}})

	assert response["result"]["isError"] is True
	assert tool_text(response) == {"status": "error", "error": "Internal error"}
	assert "hunter2" not in json.dumps(response)
	assert fake.db.rollbacks == before + 1
	assert fake.error_logs and fake.error_logs[-1]["title"] == "External agent MCP tool failed"
