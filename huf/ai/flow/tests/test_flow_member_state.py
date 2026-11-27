"""Flow Member State: per-member journey variables, the ``member.*`` reference root and ``member.set``."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.runs import member
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import GraphContext
from huf.huf.doctype.flow_member_state.flow_member_state import on_doctype_update
from huf.patches.v1 import dedupe_flow_member_state


class TestFlowMemberState(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-member-{frappe.generate_hash(length=8)}",
				"flow_name": "Member Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "n1", "type": "output", "config": {}}]}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow = flow
		self.flow_id = flow.name

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		if frappe.db.exists("Flow Definition", self.flow_id):
			frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, status="Running", key="a"):
		return frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": self.flow_id,
				"flow_id": self.flow_id,
				"status": status,
				"trigger_type": "Manual",
				"member_key": key,
			}
		).insert(ignore_permissions=True)

	def test_resolve_whatsapp_sender_normalised(self):
		a = member.resolve_member_key("Gateway", {"sender_id": "+1 (555) 010-0100"}, "Guest")
		b = member.resolve_member_key("Gateway", {"sender_id": "15550100100"}, "Guest")
		self.assertEqual(a, b)
		self.assertEqual(a, "15550100100")
		self.assertEqual(member.resolve_member_key("Doc Event", {"_trigger": {"doctype": "ToDo", "docname": "T1"}}, "x"), "ToDo:T1")
		self.assertEqual(member.resolve_member_key("Manual", {}, "alice@example.com"), "alice@example.com")

	def test_no_member_when_unresolvable(self):
		self.assertIsNone(member.resolve_member_key("Webhook", {"a": 1}, "Guest"))
		self.assertIsNone(member.resolve_member_key("Schedule", {}, "Administrator"))
		self.assertIsNone(member.resolve_member_key("Gateway", {}, "Guest"))
		self.assertIsNone(member.resolve_member_key("Manual", {}, "Guest"))

	def test_upsert_unique_per_flow(self):
		n1 = member.upsert_member(self.flow_id, "k1", None)
		n2 = member.upsert_member(self.flow_id, "k1", None)
		self.assertEqual(n1, n2)
		self.assertEqual(n1, member.member_name(self.flow_id, "k1"))
		self.assertEqual(frappe.db.count("Flow Member State", {"flow": self.flow_id}), 1)
		self.assertEqual(member.get_member(self.flow_id, "k1")["run_count"], 2)
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": "Flow Member State", "flow": self.flow_id, "member_key": "k1"}).insert(ignore_permissions=True)

	def test_indexes_present(self):
		for index in ("unique_flow_member_key", "flow_status_index", "member_key_index"):
			self.assertTrue(frappe.db.has_index("tabFlow Member State", index), index)

	def test_dedupe_patch_merges_duplicates_then_unique_index_holds(self):
		frappe.db.commit()
		frappe.db.sql_ddl("alter table `tabFlow Member State` drop index `unique_flow_member_key`")
		try:
			canonical = member.member_name(self.flow_id, "k1")
			self._seed_row(canonical, "k1", "2026-01-01 00:00:00", 2, {"a": 1, "b": 1}, "n1")
			self._seed_row(f"dup-{self.flow_id}"[:140], "k1", "2026-02-01 00:00:00", 3, {"b": 2}, "n2")
			self._seed_row(f"solo-{self.flow_id}"[:140], "k2", "2026-01-01 00:00:00", 1, {}, "n1")
			dedupe_flow_member_state.execute()
			dedupe_flow_member_state.execute()  # safe to run again
			self.assertEqual(frappe.db.count("Flow Member State", {"flow": self.flow_id, "member_key": "k1"}), 1)
			self.assertEqual(frappe.db.count("Flow Member State", {"flow": self.flow_id}), 2)
			row = member.get_member(self.flow_id, "k1")  # the survivor carries the canonical name
			self.assertEqual(row["run_count"], 5)
			self.assertEqual(str(row["last_event_at"]), "2026-02-01 00:00:00")
			self.assertEqual(str(row["entered_at"]), "2026-01-01 00:00:00")
			self.assertEqual(row["vars"], {"a": 1, "b": 2})
			self.assertEqual([h["node"] for h in row["history"]], ["n1", "n2"])
		finally:
			frappe.db.commit()
			on_doctype_update()
		self.assertTrue(frappe.db.has_index("tabFlow Member State", "unique_flow_member_key"))
		with self.assertRaises(Exception) as caught:
			self._seed_row(f"again-{self.flow_id}"[:140], "k1", "2026-03-01 00:00:00", 1, {}, "n1")
		self.assertTrue(frappe.db.is_unique_key_violation(caught.exception), caught.exception)

	def _seed_row(self, name, key, at, run_count, variables, node):
		frappe.db.sql(
			"insert into `tabFlow Member State` (name, creation, modified, flow, member_key, status, entered_at,"
			" last_event_at, run_count, vars_json, history_json) values (%s, %s, %s, %s, %s, 'Active', %s, %s, %s, %s, %s)",
			(name, at, at, self.flow_id, key, at, at, run_count, json.dumps(variables), json.dumps([{"node": node, "at": at}])),
		)

	def test_waiting_status_remembers_the_step_and_other_statuses_forget_it(self):
		member.upsert_member(self.flow_id, "k1", None)
		member.set_status(self.flow_id, "k1", "Waiting", "wait_step")
		self.assertEqual(member.get_member(self.flow_id, "k1")["current_node_id"], "wait_step")
		member.set_status(self.flow_id, "k1", "Active")
		self.assertFalse(member.get_member(self.flow_id, "k1")["current_node_id"])

	def test_member_root_resolves_in_templates(self):
		member.upsert_member(self.flow_id, "k1", None)
		member.set_vars(self.flow_id, "k1", {"plan": "gold"})
		run = self._run(key="k1")
		ctx = flow_engine._build_run_context(run, _no_version())
		self.assertEqual(ctx.context.resolve({"$from": "member.vars.plan"}), "gold")
		self.assertEqual(ctx.context.resolve({"$from": "member.status"}), "Active")

	def test_member_set_persists_no_ttl(self):
		member.upsert_member(self.flow_id, "k1", None)
		run = self._run(key="k1")
		ctx = GraphContext({"x": "hello"})
		ctx.member = {"vars": {}}
		out = flow_engine._exec_member_set(
			run, {"id": "m1"}, {"vars": {"greeting": {"$from": "input.x"}, "n": 3}},
			flow_engine.FlowRunContext(context=ctx),
		)
		self.assertEqual(out["status"], "success")
		self.assertEqual(member.get_vars(self.flow_id, "k1"), {"greeting": "hello", "n": 3})
		self.assertEqual(ctx.member["vars"]["n"], 3)
		self.assertEqual(frappe.db.get_value("Flow Member State", member.member_name(self.flow_id, "k1"), "vars_json") is not None, True)
		self.assertEqual(member.get_member(self.flow_id, "k1")["history"][-1]["node"], "m1")

	def test_member_set_without_member_fails(self):
		run = self._run(key=None)
		out = flow_engine._exec_member_set(run, {"id": "m1"}, {"vars": {"a": 1}}, flow_engine.FlowRunContext(context=GraphContext({})))
		self.assertEqual(out["status"], "failed")

	def test_vars_cap_64kb(self):
		member.upsert_member(self.flow_id, "k1", None)
		with self.assertRaises(member.FlowMemberError):
			member.set_vars(self.flow_id, "k1", {"big": "x" * (member.MAX_VARS_BYTES + 1)})
		self.assertEqual(member.get_vars(self.flow_id, "k1"), {})

	def test_history_capped(self):
		member.upsert_member(self.flow_id, "k1", None)
		for i in range(member.MAX_HISTORY + 5):
			member.record_history(self.flow_id, "k1", f"n{i}", None)
		hist = member.get_member(self.flow_id, "k1")["history"]
		self.assertEqual(len(hist), member.MAX_HISTORY)
		self.assertEqual(hist[-1]["node"], f"n{member.MAX_HISTORY + 4}")

	def test_remove_member_cancels_waiting_run(self):
		run = self._run(status="Waiting User", key="k1")
		member.upsert_member(self.flow_id, "k1", run.name)
		self.assertTrue(member.remove_member(self.flow_id, "k1"))
		self.assertEqual(frappe.db.get_value("Agent Flow Run", run.name, "status"), "Cancelled")
		self.assertIsNone(member.get_member(self.flow_id, "k1"))
		self.assertFalse(member.remove_member(self.flow_id, "k1"))

	def test_purge_inactive(self):
		member.upsert_member(self.flow_id, "old", None)
		member.upsert_member(self.flow_id, "new", None)
		frappe.db.set_value("Flow Member State", member.member_name(self.flow_id, "old"), "last_event_at", "2000-01-01 00:00:00")
		self.assertGreaterEqual(member.purge_inactive(30), 1)
		self.assertIsNone(member.get_member(self.flow_id, "old"))
		self.assertIsNotNone(member.get_member(self.flow_id, "new"))

	def test_create_flow_run_sets_member_key(self):
		self.flow.db_set("definition_json", json.dumps(finished_flow()))
		run = flow_engine.create_flow_run(self.flow_id, {}, "Manual", ignore_permissions=True)
		self.assertEqual(run.member_key, "Administrator")
		self.assertEqual(member.get_member(self.flow_id, "Administrator")["active_flow_run"], run.name)
		test_run = flow_engine.create_flow_run(self.flow_id, {}, "Manual", ignore_permissions=True, mode="test")
		self.assertFalse(test_run.member_key)
		self.assertEqual(member.get_member(self.flow_id, "Administrator")["run_count"], 1)


def _no_version():
	from huf.ai.flow.engine import PinnedVersion

	return PinnedVersion.pin({"nodes": [{"id": "n1", "type": "output", "config": {}}]})

