# ruff: noqa: S101
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from huf.ai.external import dispatch, mailbox
from huf.ai.external.core import jsonrpc, states
from huf.ai.external.core.capabilities import capability_names
from huf.ai.external.tests.fake_frappe import FakeFrappe, patch_modules

SESSION = "External Agent Session"
EVENT = "External Agent Event"
RUN = "Agent Run"
TOKEN = "tok-dispatch-secret-9f2c41"  # noqa: S105 - fixture value, never a real credential
SEVEN_TOOLS = [
	"huf_discover",
	"huf_context",
	"huf_invoke",
	"huf_surface",
	"huf_wait",
	"huf_report",
	"huf_complete",
]


@pytest.fixture
def fake(monkeypatch) -> FakeFrappe:
	fake = FakeFrappe()
	patch_modules(monkeypatch, fake)
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
	return fake


@pytest.fixture
def session(fake):
	return fake.get_doc(SESSION, "S1")


def call(session, name: str, arguments=None, request_id: int = 1) -> dict:
	params: dict = {"name": name}
	if arguments is not None:
		params["arguments"] = arguments
	request = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": params}
	return dispatch.handle_rpc(request, session)


def tool_text(response: dict) -> dict:
	return json.loads(response["result"]["content"][0]["text"])


def events_of(fake: FakeFrappe, event_type: str) -> list[dict]:
	return [row for row in fake.db.rows.get(EVENT, {}).values() if row["event_type"] == event_type]


def session_row(fake: FakeFrappe) -> dict:
	return fake.db.rows[SESSION]["S1"]


def test_initialize_reports_protocol_and_tools_without_leaking_the_token(session):
	response = dispatch.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, session)

	result = response["result"]
	assert response["id"] == 1
	assert result["protocolVersion"] == dispatch.PROTOCOL_VERSION
	assert "tools" in result["capabilities"]
	assert result["serverInfo"] == dispatch.SERVER_INFO
	assert TOKEN not in json.dumps(response)
	assert TOKEN not in json.dumps(result)


def test_notifications_get_no_response_and_do_not_run_handlers(fake, session):
	assert dispatch.handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, session) is None
	# A tools/call without an id is a notification too: it must not execute the tool.
	notice = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "huf_wait"}}
	assert dispatch.handle_rpc(notice, session) is None
	assert session_row(fake)["state"] == states.ACTIVE


def test_ping_returns_empty_result(session):
	response = dispatch.handle_rpc({"jsonrpc": "2.0", "id": "p-1", "method": "ping"}, session)
	assert response == {"jsonrpc": "2.0", "id": "p-1", "result": {}}


def test_tools_list_offers_exactly_the_seven_capabilities(session):
	response = dispatch.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session)

	names = [tool["name"] for tool in response["result"]["tools"]]
	assert names == capability_names()
	assert sorted(names) == sorted(SEVEN_TOOLS)


def test_unknown_tool_name_is_invalid_params(session):
	response = call(session, "huf_delete_everything")

	assert response["error"]["code"] == jsonrpc.INVALID_PARAMS


@pytest.mark.parametrize("arguments", [["x"], "text", 7, True])
def test_non_object_arguments_are_invalid_params(session, arguments):
	response = call(session, "huf_discover", arguments)

	assert response["error"]["code"] == jsonrpc.INVALID_PARAMS
	assert "result" not in response


@pytest.mark.parametrize("arguments", [[], 0, False, ""])
def test_falsy_non_object_arguments_are_invalid_params(session, arguments):
	response = call(session, "huf_discover", arguments)

	assert response["error"]["code"] == jsonrpc.INVALID_PARAMS


def test_unknown_method_is_method_not_found(session):
	response = dispatch.handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "resources/list"}, session)

	assert response["error"]["code"] == jsonrpc.METHOD_NOT_FOUND


@pytest.mark.parametrize("kind", ["progress", "observation", "artifact"])
def test_report_posts_from_agent_event_with_the_given_kind(fake, session, kind):
	response = call(
		session,
		"huf_report",
		{"message": "halfway", "kind": kind, "data": {"step": 2}},
	)

	assert response["result"]["isError"] is False
	assert tool_text(response) == {"status": "ok"}
	reports = events_of(fake, "report")
	assert len(reports) == 1
	assert reports[0]["direction"] == "from_agent"
	assert json.loads(reports[0]["payload"]) == {"kind": kind, "message": "halfway", "data": {"step": 2}}
	assert session_row(fake)["last_seq"] == 1


def test_complete_success_sets_completed_and_stores_run_response(fake, session):
	response = call(session, "huf_complete", {"status": "success", "result": "All done"})

	assert response["result"]["isError"] is False
	assert tool_text(response) == {"status": "ok"}
	assert session_row(fake)["state"] == states.COMPLETED
	assert fake.db.rows[RUN]["R1"]["response"] == "All done"
	assert fake.db.rows[RUN]["R1"]["status"] == "Success"
	completions = events_of(fake, "complete")
	assert len(completions) == 1
	assert json.loads(completions[0]["payload"]) == {"status": "success", "result": "All done"}


@pytest.mark.parametrize(
	("state", "expected_status"),
	[
		# Not terminal, but the graph does not allow Waiting for Approval -> Completed.
		(states.WAITING_APPROVAL, "error"),
		# Terminal: the lease renewal refuses the session before the handler runs.
		(states.COMPLETED, "denied"),
	],
)
def test_complete_from_a_disallowed_state_errors_without_writing_an_event(
	fake, session, state, expected_status
):
	fake.db.set_value(SESSION, "S1", "state", state)

	response = call(session, "huf_complete", {"status": "success", "result": "late"})

	assert response["result"]["isError"] is True
	assert tool_text(response)["status"] == expected_status
	assert events_of(fake, "complete") == []
	assert fake.db.rows[RUN]["R1"]["response"] is None
	assert session_row(fake)["state"] == state


def test_surface_rejects_an_overlong_surface_id(fake, session):
	response = call(
		session,
		"huf_surface",
		{"action": "create", "spec": {"type": "card"}, "surface_id": "x" * 65},
	)

	assert response["result"]["isError"] is True
	assert tool_text(response) == {"status": "error", "error": "Invalid surface_id"}
	assert events_of(fake, "surface") == []
	assert fake.realtime_calls == []


def test_surface_accepts_a_64_character_surface_id(fake, session):
	surface_id = "s" * 64

	response = call(
		session,
		"huf_surface",
		{"action": "update", "spec": {"type": "card"}, "surface_id": surface_id},
	)

	assert response["result"]["isError"] is False
	assert tool_text(response) == {"status": "ok", "surface_id": surface_id}
	assert len(events_of(fake, "surface")) == 1
	assert len(fake.realtime_calls) == 1


@pytest.mark.parametrize("action", ["delete", "", None])
def test_surface_rejects_a_bad_action(fake, session, action):
	response = call(session, "huf_surface", {"action": action, "spec": {"type": "card"}})

	assert response["result"]["isError"] is True
	assert tool_text(response) == {"status": "error", "error": "action must be create or update"}
	assert events_of(fake, "surface") == []
	assert fake.realtime_calls == []


@pytest.fixture
def instant_wait(monkeypatch):
	"""Make the wait loop's clock and sleep deterministic: no real sleeping."""
	monkeypatch.setattr(
		mailbox,
		"time",
		SimpleNamespace(monotonic=time.monotonic, sleep=lambda _seconds: None),
	)


@pytest.mark.parametrize("start_state", [states.ACTIVE, states.WAITING_INPUT])
def test_wait_returns_queued_user_messages_and_ends_active(fake, session, instant_wait, start_state):
	fake.db.set_value(SESSION, "S1", "state", start_state)
	mailbox.post_event("S1", "to_agent", "user_message", {"text": "first"})
	mailbox.post_event("S1", "to_agent", "user_message", {"text": "second"})

	response = call(session, "huf_wait", {"timeout_seconds": 3})

	payload = tool_text(response)
	assert response["result"]["isError"] is False
	assert payload["status"] == "ok"
	assert payload["timed_out"] is False
	assert [event["event_type"] for event in payload["events"]] == ["user_message", "user_message"]
	assert [event["payload"]["text"] for event in payload["events"]] == ["first", "second"]
	assert all(event["direction"] == "to_agent" for event in payload["events"])
	assert {row["status"] for row in fake.db.rows[EVENT].values()} == {"Delivered"}
	assert session_row(fake)["state"] == states.ACTIVE


def test_wait_with_nothing_queued_reports_timed_out_and_stays_active(fake, session, instant_wait):
	response = call(session, "huf_wait", {"timeout_seconds": 0})

	assert tool_text(response) == {"status": "ok", "events": [], "timed_out": True}
	assert session_row(fake)["state"] == states.ACTIVE


def test_invoke_forwards_arguments_and_ignores_identity_keys_at_top_level(fake, session, monkeypatch):
	captured: dict = {}

	def fake_invoke(session_doc, tool_name, args, client_call_id=None):
		captured.update(
			session_doc=session_doc,
			tool_name=tool_name,
			args=args,
			client_call_id=client_call_id,
		)
		return {"status": "ok", "result": "sent"}

	monkeypatch.setattr(dispatch, "external_invoke", fake_invoke)

	response = call(
		session,
		"huf_invoke",
		{
			"tool_name": "send_email",
			"arguments": {"to": "a@example.com", "body": "hi"},
			"client_call_id": "call-1",
			"user": "victim@example.com",
			"agent": "other-agent",
			"agent_run": "R-other",
		},
	)

	assert captured["session_doc"] is session
	assert captured["tool_name"] == "send_email"
	assert captured["args"] == {"to": "a@example.com", "body": "hi"}
	assert captured["client_call_id"] == "call-1"
	assert response["result"]["isError"] is False
	assert tool_text(response) == {"status": "ok", "result": "sent"}


def test_invoke_rejects_falsy_non_object_arguments(session, monkeypatch):
	monkeypatch.setattr(dispatch, "external_invoke", lambda *_a, **_k: {"status": "ok"})

	response = call(session, "huf_invoke", {"tool_name": "send_email", "arguments": []})

	assert tool_text(response)["status"] == "error"


def test_permission_error_yields_generic_denial_and_rolls_back(fake, session, monkeypatch):
	def refuse(*_args, **_kwargs):
		raise FakeFrappe.PermissionError("internal detail: session S1 belongs to another user")  # noqa: TRY003

	monkeypatch.setattr(dispatch, "external_invoke", refuse)
	before = fake.db.rollbacks

	response = call(session, "huf_invoke", {"tool_name": "send_email", "arguments": {}})

	assert response["result"]["isError"] is True
	assert tool_text(response) == {"status": "denied", "error": "Not permitted"}
	assert "internal detail" not in json.dumps(response)
	assert fake.db.rollbacks == before + 1


def test_unexpected_exception_yields_generic_error_logs_and_rolls_back(fake, session, monkeypatch):
	def explode(*_args, **_kwargs):
		raise RuntimeError("database password is hunter2")  # noqa: TRY003

	monkeypatch.setattr(dispatch, "external_invoke", explode)
	before = fake.db.rollbacks

	response = call(session, "huf_invoke", {"tool_name": "send_email", "arguments": {}})

	assert response["result"]["isError"] is True
	assert tool_text(response) == {"status": "error", "error": "Internal error"}
	assert "hunter2" not in json.dumps(response)
	assert fake.db.rollbacks == before + 1
	assert fake.error_logs and fake.error_logs[-1]["title"] == "External agent MCP tool failed"
