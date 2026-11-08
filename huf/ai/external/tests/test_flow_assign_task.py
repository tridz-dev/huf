# ruff: noqa: S101
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from huf.ai.external import dispatch, mailbox, sessions
from huf.ai.external.core import states
from huf.ai.external.tests.fake_frappe import FakeFrappe, patch_modules

SESSION = "External Agent Session"
EVENT = "External Agent Event"
CONNECTION = "External Agent Connection"
RUN = "Agent Run"

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"
AGENT = "agent-1"
CONNECTION_NAME = "CONN-1"
TOKEN = "tok-assign-secret"  # noqa: S105 - fixture value, never a real credential


@pytest.fixture
def fake(monkeypatch) -> FakeFrappe:
	fake = FakeFrappe(user=OWNER)
	patch_modules(monkeypatch, fake)
	# Agent access rules are covered elsewhere; these tests exercise task assignment.
	monkeypatch.setattr(sessions, "assert_agent_access", lambda agent_doc, user=None, **_: None)
	fake.get_doc({"doctype": "Agent", "name": AGENT, "owner": OWNER}).insert()
	seed_connection(fake)
	return fake


@pytest.fixture
def instant_wait(monkeypatch):
	monkeypatch.setattr(
		mailbox,
		"time",
		SimpleNamespace(monotonic=time.monotonic, sleep=lambda _seconds: None),
	)


def seed_connection(fake: FakeFrappe, *, user=OWNER, enabled=1) -> None:
	fake.get_doc(
		{
			"doctype": CONNECTION,
			"name": CONNECTION_NAME,
			"user": user,
			"agent": AGENT,
			"enabled": enabled,
			"mode": "Managed",
		}
	).insert()


def seed_session(fake: FakeFrappe, name: str, *, state: str) -> None:
	fake.get_doc({"doctype": RUN, "name": f"RUN-{name}", "status": "Started"}).insert()
	fake.get_doc(
		{
			"doctype": SESSION,
			"name": name,
			"connection": CONNECTION_NAME,
			"user": OWNER,
			"agent": AGENT,
			"state": state,
			"session_token": TOKEN,
			"agent_run": f"RUN-{name}",
			"last_seq": 0,
			"acked_seq": 0,
		}
	).insert()


def session_names(fake: FakeFrappe) -> list[str]:
	return sorted(fake.db.rows.get(SESSION, {}))


def events_for(fake: FakeFrappe, session: str) -> list[dict]:
	rows = fake.get_all(EVENT, filters={"session": session}, order_by="seq asc")
	# The fake stores payloads as JSON text; the mailbox decodes them when it returns events.
	return [{**row, "payload": json.loads(row["payload"] or "{}")} for row in rows]


def test_assign_creates_session_and_task_event_when_none_open(fake):
	result = sessions.assign_task(CONNECTION_NAME, "  Summarise the open invoices.  ")

	assert result["seq"] == 1
	assert session_names(fake) == [result["session"]]
	row = fake.db.rows[SESSION][result["session"]]
	assert row["state"] == states.ACTIVE
	assert row["user"] == OWNER

	events = events_for(fake, result["session"])
	assert len(events) == 1
	assert events[0]["direction"] == "to_agent"
	assert events[0]["event_type"] == "task_assigned"
	assert events[0]["payload"] == {"prompt": "Summarise the open invoices.", "assigned_by": OWNER}


def test_assign_reuses_open_session_and_increments_seq(fake):
	first = sessions.assign_task(CONNECTION_NAME, "first task")
	second = sessions.assign_task(CONNECTION_NAME, "second task")

	assert second["session"] == first["session"]
	assert (first["seq"], second["seq"]) == (1, 2)
	assert len(session_names(fake)) == 1
	assert [event["payload"]["prompt"] for event in events_for(fake, first["session"])] == [
		"first task",
		"second task",
	]


def test_assign_does_not_reuse_terminal_sessions(fake):
	seed_session(fake, "OLD", state=states.COMPLETED)

	result = sessions.assign_task(CONNECTION_NAME, "fresh task")

	assert result["session"] != "OLD"
	assert result["seq"] == 1
	assert len(session_names(fake)) == 2
	assert events_for(fake, "OLD") == []


def test_assign_reuses_open_session_even_when_waiting(fake):
	seed_session(fake, "WAIT", state=states.WAITING_INPUT)

	result = sessions.assign_task(CONNECTION_NAME, "task")

	assert result["session"] == "WAIT"
	assert result["seq"] == 1


def test_assign_refuses_a_stranger_and_creates_nothing(fake):
	fake.session.user = STRANGER

	with pytest.raises(FakeFrappe.PermissionError):
		sessions.assign_task(CONNECTION_NAME, "task")

	assert session_names(fake) == []
	assert fake.db.rows.get(EVENT, {}) == {}


def test_assign_refuses_disabled_connection_and_creates_nothing(fake):
	fake.db.set_value(CONNECTION, CONNECTION_NAME, "enabled", 0)

	with pytest.raises(FakeFrappe.PermissionError):
		sessions.assign_task(CONNECTION_NAME, "task")

	assert session_names(fake) == []


def test_assign_refuses_unknown_connection(fake):
	with pytest.raises(FakeFrappe.PermissionError):
		sessions.assign_task("CONN-MISSING", "task")

	assert session_names(fake) == []


@pytest.mark.parametrize("prompt", ["", "   \n\t ", "x" * 8001, None, 42])
def test_assign_rejects_empty_overlong_or_non_text_prompts(fake, prompt):
	with pytest.raises(FakeFrappe.ValidationError):
		sessions.assign_task(CONNECTION_NAME, prompt)

	assert session_names(fake) == []


def test_assign_accepts_a_prompt_at_the_length_limit(fake):
	result = sessions.assign_task(CONNECTION_NAME, "x" * 8000)

	assert result["seq"] == 1
	assert len(events_for(fake, result["session"])[0]["payload"]["prompt"]) == 8000


def test_huf_wait_returns_the_assigned_task(fake, instant_wait):
	result = sessions.assign_task(CONNECTION_NAME, "Reconcile the ledger.")
	# The doctype default for acked_seq; the fake does not apply field defaults on insert.
	fake.db.set_value(SESSION, result["session"], "acked_seq", 0)
	session_doc = fake.get_doc(SESSION, result["session"])
	request = {
		"jsonrpc": "2.0",
		"id": 7,
		"method": "tools/call",
		"params": {"name": "huf_wait", "arguments": {"timeout_seconds": 3}},
	}

	response = dispatch.handle_rpc(request, session_doc)

	payload = _tool_text(response)
	assert response["result"]["isError"] is False
	assert payload["timed_out"] is False
	assert [event["event_type"] for event in payload["events"]] == ["task_assigned"]
	assert payload["events"][0]["payload"] == {"prompt": "Reconcile the ledger.", "assigned_by": OWNER}
	assert fake.db.rows[SESSION][result["session"]]["state"] == states.ACTIVE


def _tool_text(response: dict) -> dict:
	return json.loads(response["result"]["content"][0]["text"])
