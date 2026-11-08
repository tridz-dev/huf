# ruff: noqa: S101
from __future__ import annotations

import pytest

from huf.ai.external.tests.fake_frappe import FakeFrappe, FakeRow, patch_modules

EVENT = "External Agent Event"
SESSION = "External Agent Session"


@pytest.fixture
def fake() -> FakeFrappe:
	return FakeFrappe()


def test_insert_then_get_value_and_get_doc_round_trip(fake):
	fake.get_doc({"doctype": "Agent", "name": "agent-1", "title": "Support", "disabled": 0}).insert()
	auto = fake.get_doc({"doctype": "Agent", "title": "Generated"}).insert()

	assert len(auto.name) == 10
	assert fake.db.get_value("Agent", "agent-1", "title") == "Support"
	assert fake.db.get_value("Agent", {"title": "Support"}, ["title", "disabled"]) == ("Support", 0)
	row = fake.db.get_value("Agent", "agent-1", ["title", "disabled"], as_dict=True)
	assert isinstance(row, FakeRow)
	assert (row.title, row.disabled) == ("Support", 0)
	assert fake.get_doc("Agent", "agent-1").title == "Support"
	assert fake.db.get_value("Agent", "missing") is None
	with pytest.raises(FakeFrappe.DoesNotExistError):
		fake.get_doc("Agent", "missing")


def test_get_all_applies_operators_order_limit_and_pluck(fake):
	for seq in range(1, 6):
		fake.get_doc({"doctype": EVENT, "session": "S1", "seq": seq, "direction": "to_agent"}).insert()
	fake.get_doc({"doctype": EVENT, "session": "S2", "seq": 9, "direction": "to_agent"}).insert()

	rows = fake.get_all(
		EVENT,
		filters={"session": "S1", "seq": [">", 1]},
		fields=["seq"],
		order_by="seq desc",
		limit_page_length=2,
	)
	assert [row.seq for row in rows] == [5, 4]
	assert fake.get_all(EVENT, filters=[["session", "=", "S1"], ["seq", "<=", 2]], pluck="seq") == [1, 2]
	assert fake.get_all(EVENT, filters={"seq": ["in", [9, 10]]}, pluck="session") == ["S2"]
	assert fake.get_all(EVENT, filters=[["idempotency_key", "is", "set"]], pluck="name") == []


def test_for_update_is_recorded_and_commit_rollback_are_counted(fake):
	fake.get_doc({"doctype": SESSION, "name": "S1", "last_seq": 4}).insert()

	assert fake.db.get_value(SESSION, "S1", ["last_seq"], for_update=True) == 4
	assert fake.db.locks == [(SESSION, "S1")]
	fake.db.commit()
	fake.db.commit()
	fake.db.rollback()
	assert (fake.db.commits, fake.db.rollbacks) == (2, 1)


def test_session_and_seq_are_unique_for_external_agent_events(fake):
	fake.get_doc({"doctype": EVENT, "session": "S1", "seq": 1}).insert()

	with pytest.raises(FakeFrappe.ValidationError):
		fake.get_doc({"doctype": EVENT, "session": "S1", "seq": 1}).insert(ignore_permissions=True)
	fake.get_doc({"doctype": EVENT, "session": "S2", "seq": 1}).insert()
	assert fake.db.count(EVENT, {"seq": 1}) == 2


def test_sql_statements_from_modules_apply_to_the_store(fake):
	fake.get_doc(
		{
			"doctype": EVENT,
			"name": "E1",
			"session": "S1",
			"seq": 1,
			"direction": "to_agent",
			"status": "Pending",
			"idempotency_key": "k1",
		}
	).insert()
	fake.get_doc(
		{
			"doctype": EVENT,
			"name": "E2",
			"session": "S1",
			"seq": 2,
			"direction": "to_agent",
			"status": "Delivered",
			"idempotency_key": "k2",
		}
	).insert()

	found = fake.db.sql(
		"select name from `tabExternal Agent Event` where session=%s and idempotency_key=%s limit 1 for update",
		("S1", "k1"),
	)
	assert found == [("E1",)]
	max_seq = fake.db.sql(
		"""
		SELECT MAX(`seq`) FROM `tabExternal Agent Event`
		WHERE `session` = %s AND `direction` = %s AND `status` = %s
		""",
		("S1", "to_agent", "Delivered"),
	)
	assert max_seq == [(2,)]
	fake.db.sql(
		"""
		UPDATE `tabExternal Agent Event`
		SET `status` = %s
		WHERE `session` = %s AND `direction` = %s AND `seq` <= %s AND `status` <> %s
		""",
		("Acked", "S1", "to_agent", 2, "Acked"),
	)
	assert fake.db.count(EVENT, {"status": "Acked"}) == 2


def test_unsupported_sql_is_rejected(fake):
	with pytest.raises(NotImplementedError, match="unsupported SQL"):
		fake.db.sql("select 1")


def test_throw_uses_requested_exception_class_and_hierarchy_holds(fake):
	with pytest.raises(FakeFrappe.PermissionError, match="nope"):
		fake.throw("nope", FakeFrappe.PermissionError)
	with pytest.raises(FakeFrappe.ValidationError):
		fake.throw("bad")
	for exc in (
		FakeFrappe.PermissionError,
		FakeFrappe.ValidationError,
		FakeFrappe.DoesNotExistError,
		FakeFrappe.AuthenticationError,
	):
		assert issubclass(exc, FakeFrappe.FrappeError)


def test_mailbox_round_trip_runs_against_the_fake(fake, monkeypatch):
	from huf.ai.external import mailbox

	patch_modules(monkeypatch, fake)
	assert mailbox.frappe is fake

	fake.get_doc({"doctype": SESSION, "name": "S1", "last_seq": 0, "acked_seq": 0}).insert()
	first = mailbox.post_event("S1", "to_agent", "ping", {"n": 1}, idempotency_key="k1")
	again = mailbox.post_event("S1", "to_agent", "ping", {"n": 1}, idempotency_key="k1")
	second = mailbox.post_event("S1", "to_agent", "ping", {"n": 2})

	assert (first["seq"], again["name"], second["seq"]) == (1, first["name"], 2)
	assert fake.db.count(EVENT) == 2
	events = mailbox.fetch_pending("S1")
	assert [event["seq"] for event in events] == [1, 2]
	assert {event["status"] for event in events} == {"Delivered"}
	assert mailbox.ack("S1", 2) == 2
	assert fake.db.get_value(SESSION, "S1", "acked_seq") == 2
	assert fake.db.count(EVENT, {"status": "Acked"}) == 2
