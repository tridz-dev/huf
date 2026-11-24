"""Flow Member State: per-member journey variables, the ``member.*`` reference root and ``member.set``."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine, member
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import GraphContext


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
		frappe.db.delete("Flow Run", {"flow_id": self.flow_id})
		if frappe.db.exists("Flow Definition", self.flow_id):
			frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, status="Running", key="a"):
		return frappe.get_doc(
			{
				"doctype": "Flow Run",
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
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Cancelled")
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

