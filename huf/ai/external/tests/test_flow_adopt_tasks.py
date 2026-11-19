# ruff: noqa: S101
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from huf.ai.external import mailbox, sessions
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
OTHER_CONNECTION = "CONN-2"
TOKEN = "tok-adopt-secret"  # noqa: S105 - fixture value, never a real credential


@pytest.fixture
def fake(monkeypatch) -> FakeFrappe:
	fake = FakeFrappe(user=OWNER)
	patch_modules(monkeypatch, fake)
	# Agent access rules are covered elsewhere; these tests exercise task adoption.
	monkeypatch.setattr(sessions, "assert_agent_access", lambda agent_doc, user=None, **_: None)
	fake.get_doc({"doctype": "Agent", "name": AGENT, "owner": OWNER}).insert()
	seed_connection(fake, CONNECTION_NAME)
	return fake


def seed_connection(fake: FakeFrappe, name: str, *, user=OWNER) -> None:
	fake.get_doc(
		{
			"doctype": CONNECTION,
			"name": name,
			"user": user,
			"agent": AGENT,
			"enabled": 1,
			"mode": "Managed",
		}
	).insert()


def seed_session(
	fake: FakeFrappe, name: str, *, state: str, connection: str = CONNECTION_NAME, user: str = OWNER
) -> None:
	fake.get_doc({"doctype": RUN, "name": f"RUN-{name}", "status": "Started"}).insert()
	fake.get_doc(
		{
			"doctype": SESSION,
			"name": name,
			"connection": connection,
			"user": user,
			"agent": AGENT,
			"state": state,
			"session_token": TOKEN,
			"agent_run": f"RUN-{name}",
			"last_seq": 0,
			"acked_seq": 0,
		}
	).insert()


def open_new_session(fake: FakeFrappe) -> str:
	"""Create a session the way ``initialize`` does, with the doctype defaults the fake lacks."""
	name = sessions.create_session(CONNECTION_NAME)["session"]
	fake.db.set_value(SESSION, name, {"acked_seq": 0, "last_seq": 0})
	return name


def post_task(fake: FakeFrappe, session: str, prompt: str, status: str = "Pending") -> str:
	event = mailbox.post_event(
		session,
		"to_agent",
		"task_assigned",
		{"prompt": prompt, "assigned_by": OWNER},
	)
	if status != "Pending":
		fake.db.set_value(EVENT, event["name"], "status", status)
	return event["name"]


def events_for(fake: FakeFrappe, session: str) -> list[dict]:
	rows = fake.get_all(EVENT, filters={"session": session}, order_by="seq asc")
	return [{**row, "payload": json.loads(row["payload"] or "{}")} for row in rows]


def statuses_for(fake: FakeFrappe, session: str) -> list[str]:
	return [event["status"] for event in events_for(fake, session)]


def prompts_for(fake: FakeFrappe, session: str) -> list[str]:
	return [event["payload"].get("prompt") for event in events_for(fake, session)]


def test_unacked_task_from_older_open_session_moves_into_new_session(fake):
	seed_session(fake, "OLD", state=states.ACTIVE)
	post_task(fake, "OLD", "Summarise the open invoices.")
	new = open_new_session(fake)

	adopted = sessions.adopt_pending_tasks(CONNECTION_NAME, new)

	assert adopted == 1
	delivered = mailbox.fetch_pending(new)
	assert [event["event_type"] for event in delivered] == ["task_assigned"]
	assert delivered[0]["payload"] == {"prompt": "Summarise the open invoices.", "assigned_by": OWNER}
	assert statuses_for(fake, "OLD") == ["Acked"]
	assert mailbox.fetch_pending("OLD") == []


def test_delivered_but_unacked_task_is_adopted_too(fake):
	seed_session(fake, "OLD", state=states.WAITING_INPUT)
	post_task(fake, "OLD", "Reconcile the ledger.", status="Delivered")
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 1
	assert prompts_for(fake, new) == ["Reconcile the ledger."]
	assert statuses_for(fake, "OLD") == ["Acked"]


def test_non_task_events_are_not_adopted(fake):
	seed_session(fake, "OLD", state=states.ACTIVE)
	mailbox.post_event("OLD", "to_agent", "session_cancelled", {"reason": "cancelled"})
	mailbox.post_event("OLD", "from_agent", "task_assigned", {"prompt": "not ours"})
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 0

	assert events_for(fake, new) == []
	assert statuses_for(fake, "OLD") == ["Pending", "Pending"]


def test_acked_tasks_are_not_adopted(fake):
	seed_session(fake, "OLD", state=states.ACTIVE)
	post_task(fake, "OLD", "already finished", status="Acked")
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 0

	assert events_for(fake, new) == []
	assert statuses_for(fake, "OLD") == ["Acked"]


def test_other_connections_users_and_terminal_sessions_are_untouched(fake):
	seed_connection(fake, OTHER_CONNECTION)
	seed_session(fake, "OTHER-CONN", state=states.ACTIVE, connection=OTHER_CONNECTION)
	post_task(fake, "OTHER-CONN", "other connection task")
	seed_session(fake, "STRANGER-S", state=states.ACTIVE, user=STRANGER)
	post_task(fake, "STRANGER-S", "another user's task")
	seed_session(fake, "DONE", state=states.COMPLETED)
	post_task(fake, "DONE", "finished session task")
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 0

	assert events_for(fake, new) == []
	assert statuses_for(fake, "OTHER-CONN") == ["Pending"]
	assert statuses_for(fake, "STRANGER-S") == ["Pending"]
	assert statuses_for(fake, "DONE") == ["Pending"]


def test_second_call_adopts_nothing(fake):
	seed_session(fake, "OLD", state=states.ACTIVE)
	post_task(fake, "OLD", "only once")
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 1
	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 0

	assert prompts_for(fake, new) == ["only once"]
	assert statuses_for(fake, "OLD") == ["Acked"]


def test_adoption_is_idempotent_when_the_old_event_was_not_acked(fake):
	# A previous call may have posted the copy and failed before acknowledging the original.
	seed_session(fake, "OLD", state=states.ACTIVE)
	original = post_task(fake, "OLD", "retry me")
	new = open_new_session(fake)
	mailbox.post_event(
		new,
		"to_agent",
		"task_assigned",
		{"prompt": "retry me", "assigned_by": OWNER},
		idempotency_key=f"adopted-{original}",
	)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 1

	assert prompts_for(fake, new) == ["retry me"]
	assert statuses_for(fake, "OLD") == ["Acked"]


def test_cap_limits_each_call_to_twenty_tasks(fake):
	seed_session(fake, "OLD", state=states.ACTIVE)
	for index in range(25):
		post_task(fake, "OLD", f"task {index}")
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 20
	assert statuses_for(fake, "OLD").count("Pending") == 5
	assert len(events_for(fake, new)) == 20

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 5
	assert statuses_for(fake, "OLD").count("Pending") == 0
	assert len(events_for(fake, new)) == 25


def test_tasks_are_adopted_oldest_first(fake):
	seed_session(fake, "OLD-1", state=states.ACTIVE)
	seed_session(fake, "OLD-2", state=states.ACTIVE)
	late = post_task(fake, "OLD-2", "late")
	early = post_task(fake, "OLD-1", "early")
	fake.db.set_value(EVENT, late, "creation", fake.now + timedelta(minutes=2))
	fake.db.set_value(EVENT, early, "creation", fake.now + timedelta(minutes=1))
	new = open_new_session(fake)

	assert sessions.adopt_pending_tasks(CONNECTION_NAME, new) == 2

	assert prompts_for(fake, new) == ["early", "late"]
