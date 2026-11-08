# ruff: noqa: S101
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from huf.ai.external import mailbox, sessions, states
from huf.ai.external.mailbox_logic import DEFAULT_WAIT_SECONDS, MAX_WAIT_SECONDS
from huf.ai.external.tests.fake_frappe import DEFAULT_NOW, FakeFrappe, patch_modules

SESSION = "External Agent Session"
EVENT = "External Agent Event"
CONNECTION = "External Agent Connection"
RUN = "Agent Run"
CONVERSATION = "Agent Conversation"

OWNER = "owner@example.com"
OTHER = "other@example.com"
STRANGER = "stranger@example.com"
AGENT = "agent-1"
CONNECTION_NAME = "CONN-1"
SESSION_NAME = "S1"
RUN_NAME = "RUN-1"
BEARER = "tok-1"
DENIED = "Unknown or closed session"


class FakeClock:
	"""Stands in for the ``time`` module inside ``mailbox``: sleep advances the clock instantly."""

	def __init__(self) -> None:
		self.now = 0.0
		self.sleeps: list[float] = []
		self.on_sleep = None

	def monotonic(self) -> float:
		return self.now

	def sleep(self, seconds: float) -> None:
		self.sleeps.append(seconds)
		self.now += seconds
		if self.on_sleep is not None:
			self.on_sleep(len(self.sleeps))


@pytest.fixture
def fake() -> FakeFrappe:
	return FakeFrappe(user=OWNER)


@pytest.fixture
def env(fake, monkeypatch) -> FakeFrappe:
	patch_modules(monkeypatch, fake)
	# Agent access rules are covered elsewhere; these tests exercise the session lifecycle.
	monkeypatch.setattr(sessions, "assert_agent_access", lambda agent_doc, user=None, **_: None)
	fake.get_doc({"doctype": "Agent", "name": AGENT, "owner": OWNER}).insert()
	seed_connection(fake)
	return fake


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
	fake_clock = FakeClock()
	monkeypatch.setattr(mailbox, "time", fake_clock)
	return fake_clock


def seed_connection(fake: FakeFrappe, *, user=OWNER, enabled=1, mode="Managed") -> None:
	fake.get_doc(
		{
			"doctype": CONNECTION,
			"name": CONNECTION_NAME,
			"user": user,
			"agent": AGENT,
			"enabled": enabled,
			"mode": mode,
		}
	).insert()


def seed_run(fake: FakeFrappe) -> None:
	fake.get_doc({"doctype": RUN, "name": RUN_NAME, "status": "Started"}).insert()


def seed_session(fake: FakeFrappe, *, state=states.ACTIVE, **extra) -> None:
	seed_run(fake)
	values = {
		"doctype": SESSION,
		"name": SESSION_NAME,
		"connection": CONNECTION_NAME,
		"user": OWNER,
		"agent": AGENT,
		"state": state,
		"session_token": BEARER,
		"agent_run": RUN_NAME,
		"last_seq": 0,
		"acked_seq": 0,
		**extra,
	}
	fake.get_doc(values).insert()


def session_row(fake: FakeFrappe, name: str = SESSION_NAME) -> dict:
	return fake.db.rows[SESSION][name]


def events_for(fake: FakeFrappe, session: str = SESSION_NAME) -> list:
	return fake.get_all(EVENT, filters={"session": session}, order_by="seq asc")


# --- mailbox -----------------------------------------------------------------------------------


def test_post_event_assigns_consecutive_seq(env):
	seed_session(env)

	first = mailbox.post_event(SESSION_NAME, "to_agent", "ping", {"n": 1})
	second = mailbox.post_event(SESSION_NAME, "to_agent", "ping", {"n": 2})
	third = mailbox.post_event(SESSION_NAME, "from_agent", "pong")

	assert [first["seq"], second["seq"], third["seq"]] == [1, 2, 3]
	assert first["payload"] == {"n": 1}
	assert third["payload"] == {}
	assert third["direction"] == "from_agent"
	assert first["status"] == "Pending"
	assert session_row(env)["last_seq"] == 3


def test_post_event_returns_stored_event_for_repeated_idempotency_key(env):
	seed_session(env)

	first = mailbox.post_event(SESSION_NAME, "to_agent", "ping", {"n": 1}, idempotency_key="k1")
	again = mailbox.post_event(SESSION_NAME, "to_agent", "ping", {"n": 99}, idempotency_key="k1")

	assert again == first
	assert again["payload"] == {"n": 1}
	assert len(events_for(env)) == 1
	assert session_row(env)["last_seq"] == 1


def test_idempotency_keys_are_scoped_to_a_session(env):
	seed_session(env)
	seed_session(env, name="S2")

	one = mailbox.post_event("S1", "to_agent", "ping", idempotency_key="shared")
	two = mailbox.post_event("S2", "to_agent", "ping", idempotency_key="shared")

	assert one["name"] != two["name"]
	assert two["seq"] == 1


def test_fetch_pending_returns_only_to_agent_events_above_acked_in_order(env):
	seed_session(env)
	mailbox.post_event(SESSION_NAME, "to_agent", "a")
	mailbox.post_event(SESSION_NAME, "from_agent", "reply")
	mailbox.post_event(SESSION_NAME, "to_agent", "b")
	mailbox.post_event(SESSION_NAME, "to_agent", "c")
	mailbox.ack(SESSION_NAME, 1)

	events = mailbox.fetch_pending(SESSION_NAME)

	assert [event["seq"] for event in events] == [3, 4]
	assert [event["event_type"] for event in events] == ["b", "c"]
	assert {event["status"] for event in events} == {"Delivered"}
	stored = {row["seq"]: row["status"] for row in events_for(env)}
	assert stored == {1: "Acked", 2: "Pending", 3: "Delivered", 4: "Delivered"}


def test_fetch_pending_respects_limit_and_redelivers_until_acked(env):
	seed_session(env)
	for n in range(3):
		mailbox.post_event(SESSION_NAME, "to_agent", "ping", {"n": n})

	assert [event["seq"] for event in mailbox.fetch_pending(SESSION_NAME, limit=2)] == [1, 2]
	assert [event["seq"] for event in mailbox.fetch_pending(SESSION_NAME, limit=2)] == [1, 2]
	mailbox.ack(SESSION_NAME, 2)
	assert [event["seq"] for event in mailbox.fetch_pending(SESSION_NAME)] == [3]


def test_ack_is_clamped_to_last_seq_and_never_decreases(env):
	seed_session(env)
	for _ in range(3):
		mailbox.post_event(SESSION_NAME, "to_agent", "ping")

	assert mailbox.ack(SESSION_NAME, 2) == 2
	assert mailbox.ack(SESSION_NAME, 1) == 2
	assert mailbox.ack(SESSION_NAME, 0) == 2
	assert session_row(env)["acked_seq"] == 2
	assert mailbox.ack(SESSION_NAME, 99) == 3
	assert session_row(env)["acked_seq"] == 3
	assert {row["status"] for row in events_for(env)} == {"Acked"}


def test_ack_on_session_without_events_stays_at_zero(env):
	seed_session(env)

	assert mailbox.ack(SESSION_NAME, 5) == 0
	assert session_row(env)["acked_seq"] == 0


def test_wait_for_events_returns_immediately_when_events_exist(env, clock):
	seed_session(env)
	mailbox.post_event(SESSION_NAME, "to_agent", "a")
	mailbox.post_event(SESSION_NAME, "to_agent", "b")

	events = mailbox.wait_for_events(SESSION_NAME, timeout_seconds=5)

	assert [event["seq"] for event in events] == [1, 2]
	assert clock.sleeps == []


def test_wait_for_events_returns_empty_after_clamped_timeout(env, clock):
	seed_session(env)

	assert mailbox.wait_for_events(SESSION_NAME, timeout_seconds=999) == []
	assert clock.sleeps == [1] * MAX_WAIT_SECONDS
	assert clock.now == MAX_WAIT_SECONDS


def test_wait_for_events_uses_default_timeout_when_none_given(env, clock):
	seed_session(env)

	assert mailbox.wait_for_events(SESSION_NAME) == []
	assert clock.now == DEFAULT_WAIT_SECONDS


def test_wait_for_events_with_zero_timeout_polls_once(env, clock):
	seed_session(env)

	assert mailbox.wait_for_events(SESSION_NAME, timeout_seconds=0) == []
	assert clock.sleeps == []


def test_wait_for_events_returns_event_posted_during_the_wait(env, clock):
	seed_session(env)

	def post_on_second_sleep(sleep_count: int) -> None:
		if sleep_count == 2:
			mailbox.post_event(SESSION_NAME, "to_agent", "late")

	clock.on_sleep = post_on_second_sleep

	events = mailbox.wait_for_events(SESSION_NAME, timeout_seconds=5)

	assert [event["event_type"] for event in events] == ["late"]
	assert clock.sleeps == [1, 1]


# --- sessions: lifecycle -------------------------------------------------------------------------


def test_create_session_builds_conversation_run_and_session_for_owner(env):
	result = sessions.create_session(CONNECTION_NAME, native_session_id="native-1")

	session = session_row(env, result["session"])
	assert session["user"] == OWNER
	assert session["agent"] == AGENT
	assert session["state"] == states.ACTIVE
	assert session["visibility_mode"] == sessions.VISIBILITY_MANAGED
	assert session["session_token"] == result["token"]
	assert len(result["token"]) >= 40
	assert session["native_session_id"] == "native-1"
	assert session["conversation"] == result["conversation"]
	assert session["agent_run"] == result["agent_run"]

	conversation = env.db.rows[CONVERSATION][result["conversation"]]
	assert conversation["agent"] == AGENT
	assert conversation["channel"] == "external_agent"
	assert conversation["external_id"] == CONNECTION_NAME

	run = env.db.rows[RUN][result["agent_run"]]
	assert run["conversation"] == result["conversation"]
	assert run["status"] == "Started"


def test_create_session_uses_connected_visibility_for_non_managed_connection(env):
	env.db.set_value(CONNECTION, CONNECTION_NAME, "mode", "Self-hosted")

	result = sessions.create_session(CONNECTION_NAME)

	assert session_row(env, result["session"])["visibility_mode"] == sessions.VISIBILITY_CONNECTED


def test_create_session_refuses_another_user_and_creates_nothing(env):
	env.session.user = OTHER

	with pytest.raises(FakeFrappe.PermissionError):
		sessions.create_session(CONNECTION_NAME)

	assert env.db.count(SESSION) == 0
	assert env.db.count(CONVERSATION) == 0
	assert env.db.count(RUN) == 0


def test_create_session_refuses_disabled_connection_and_creates_nothing(env):
	env.db.set_value(CONNECTION, CONNECTION_NAME, "enabled", 0)

	with pytest.raises(FakeFrappe.PermissionError):
		sessions.create_session(CONNECTION_NAME)

	assert env.db.count(SESSION) == 0
	assert env.db.count(CONVERSATION) == 0


@pytest.mark.parametrize("state", [states.COMPLETED, states.FAILED, states.CANCELLED])
def test_get_session_for_token_refuses_terminal_sessions(env, state):
	seed_session(env, state=state)

	with pytest.raises(FakeFrappe.PermissionError, match=DENIED):
		sessions.get_session_for_token(BEARER)


def test_get_session_for_token_returns_session_for_owner(env):
	seed_session(env)

	session = sessions.get_session_for_token(BEARER)

	assert session.name == SESSION_NAME
	assert session.state == states.ACTIVE


def test_get_session_for_token_refuses_wrong_user(env):
	seed_session(env)
	env.session.user = OTHER

	with pytest.raises(FakeFrappe.PermissionError, match=DENIED):
		sessions.get_session_for_token(BEARER)


@pytest.mark.parametrize("token", ["", "unknown-token"])
def test_get_session_for_token_refuses_missing_or_unknown_token(env, token):
	seed_session(env)

	with pytest.raises(FakeFrappe.PermissionError, match=DENIED):
		sessions.get_session_for_token(token)


def test_get_session_for_token_refuses_disabled_connection(env):
	seed_session(env)
	env.db.set_value(CONNECTION, CONNECTION_NAME, "enabled", 0)

	with pytest.raises(FakeFrappe.PermissionError, match=DENIED):
		sessions.get_session_for_token(BEARER)


def test_get_session_for_token_refuses_when_agent_access_is_lost(env, monkeypatch):
	seed_session(env)

	def deny(agent_doc, user=None, **_):
		raise FakeFrappe.PermissionError("no access")  # noqa: TRY003

	monkeypatch.setattr(sessions, "assert_agent_access", deny)

	with pytest.raises(FakeFrappe.PermissionError, match=DENIED):
		sessions.get_session_for_token(BEARER)


@pytest.mark.parametrize("src", states.ALL_STATES)
def test_transition_follows_the_state_machine(env, src):
	seed_session(env, state=src)

	for dst in states.ALL_STATES:
		env.db.set_value(SESSION, SESSION_NAME, "state", src)
		if states.can_transition(src, dst):
			sessions.transition(SESSION_NAME, dst)
			assert session_row(env)["state"] == dst
		else:
			with pytest.raises(FakeFrappe.ValidationError, match="Cannot change session"):
				sessions.transition(SESSION_NAME, dst)
			assert session_row(env)["state"] == src


@pytest.mark.parametrize(
	("dst", "run_status", "error_message"),
	[
		(states.COMPLETED, "Success", None),
		(states.FAILED, "Failed", None),
		(states.CANCELLED, "Failed", "Cancelled"),
	],
)
def test_terminal_transition_closes_the_run(env, dst, run_status, error_message):
	seed_session(env)

	sessions.transition(SESSION_NAME, dst)

	session = session_row(env)
	assert session["ended_at"] == DEFAULT_NOW
	run = env.db.rows[RUN][RUN_NAME]
	assert run["status"] == run_status
	assert run["end_time"] == DEFAULT_NOW
	assert run.get("error_message") == error_message


def test_non_terminal_transition_leaves_run_and_end_time_alone(env):
	seed_session(env)

	sessions.transition(SESSION_NAME, states.WAITING_INPUT)

	assert session_row(env).get("ended_at") is None
	assert env.db.rows[RUN][RUN_NAME]["status"] == "Started"


def test_transition_of_unknown_session_raises_does_not_exist(env):
	with pytest.raises(FakeFrappe.DoesNotExistError):
		sessions.transition("missing", states.COMPLETED)


def test_cancel_session_by_stranger_is_refused_and_changes_nothing(env):
	seed_session(env)
	env.session.user = STRANGER

	with pytest.raises(FakeFrappe.PermissionError):
		sessions.cancel_session(SESSION_NAME)

	assert session_row(env)["state"] == states.ACTIVE
	assert events_for(env) == []


def test_cancel_session_by_owner_cancels_and_posts_event(env):
	seed_session(env)

	sessions.cancel_session(SESSION_NAME)

	assert session_row(env)["state"] == states.CANCELLED
	assert env.db.rows[RUN][RUN_NAME]["error_message"] == "Cancelled"
	events = events_for(env)
	assert len(events) == 1
	event = events[0]
	assert event["event_type"] == "session_cancelled"
	assert event["direction"] == "to_agent"
	assert event["idempotency_key"] == f"cancel-{SESSION_NAME}"
	assert json.loads(event["payload"]) == {"reason": "cancelled"}


def test_cancel_session_twice_posts_one_event(env):
	seed_session(env)

	sessions.cancel_session(SESSION_NAME)
	sessions.cancel_session(SESSION_NAME)

	assert len(events_for(env)) == 1


def test_cancel_session_on_terminal_session_is_a_no_op(env):
	seed_session(env, state=states.COMPLETED)

	sessions.cancel_session(SESSION_NAME)

	assert session_row(env)["state"] == states.COMPLETED
	assert events_for(env) == []


def test_renew_lease_refuses_second_owner_while_lease_is_live(env):
	seed_session(env)
	sessions.renew_lease(SESSION_NAME, "runtime-a", ttl_seconds=60)
	assert session_row(env)["lease_owner"] == "runtime-a"

	with pytest.raises(FakeFrappe.PermissionError, match="another runtime"):
		sessions.renew_lease(SESSION_NAME, "runtime-b")

	assert session_row(env)["lease_owner"] == "runtime-a"
	sessions.renew_lease(SESSION_NAME, "runtime-a", ttl_seconds=60)
	assert session_row(env)["lease_expires"] == DEFAULT_NOW + timedelta(seconds=60)


def test_renew_lease_allows_second_owner_after_lease_lapses(env):
	seed_session(env)
	sessions.renew_lease(SESSION_NAME, "runtime-a", ttl_seconds=60)

	env.now = DEFAULT_NOW + timedelta(minutes=2)
	sessions.renew_lease(SESSION_NAME, "runtime-b")

	assert session_row(env)["lease_owner"] == "runtime-b"


def test_renew_lease_refuses_terminal_session(env):
	seed_session(env, state=states.FAILED)

	with pytest.raises(FakeFrappe.PermissionError):
		sessions.renew_lease(SESSION_NAME, "runtime-a")


def test_renew_lease_on_runtime_offline_session_reactivates_it(env):
	seed_session(env, state=states.RUNTIME_OFFLINE)

	sessions.renew_lease(SESSION_NAME, "runtime-a")

	assert session_row(env)["state"] == states.ACTIVE


def test_expire_stale_leases_moves_lapsed_sessions_to_runtime_offline(env):
	past = DEFAULT_NOW - timedelta(minutes=1)
	future = DEFAULT_NOW + timedelta(minutes=1)
	seed_session(env, name="ACTIVE-LAPSED", state=states.ACTIVE, lease_expires=past)
	seed_session(env, name="INPUT-LAPSED", state=states.WAITING_INPUT, lease_expires=past)
	seed_session(env, name="APPROVAL-LAPSED", state=states.WAITING_APPROVAL, lease_expires=past)
	seed_session(env, name="ACTIVE-LIVE", state=states.ACTIVE, lease_expires=future)
	seed_session(env, name="NO-LEASE", state=states.ACTIVE, lease_expires=None)
	seed_session(env, name="DONE-LAPSED", state=states.COMPLETED, lease_expires=past)

	sessions.expire_stale_leases()

	assert session_row(env, "ACTIVE-LAPSED")["state"] == states.RUNTIME_OFFLINE
	assert session_row(env, "INPUT-LAPSED")["state"] == states.RUNTIME_OFFLINE
	assert session_row(env, "APPROVAL-LAPSED")["state"] == states.RUNTIME_OFFLINE
	assert session_row(env, "ACTIVE-LIVE")["state"] == states.ACTIVE
	assert session_row(env, "NO-LEASE")["state"] == states.ACTIVE
	assert session_row(env, "DONE-LAPSED")["state"] == states.COMPLETED
