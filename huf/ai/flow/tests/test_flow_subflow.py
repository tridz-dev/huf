"""``flow.call`` node (flow/nodes/subflow.py): fire-and-forget, wait-for-child, failure, depth, cancel cascade."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.nodes import send
from huf.ai.flow.runs import park
from huf.ai.flow.support import step_keys
from huf.ai.flow.nodes.subflow import MAX_DEPTH, exec_flow_call
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import GraphContext


def _flow(prefix, status, definition):
	doc = frappe.get_doc(
		{
			"doctype": "Flow Definition",
			"flow_id": f"_test-{prefix}-{frappe.generate_hash(length=8)}",
			"flow_name": f"Subflow {prefix}",
			"status": status,
			"definition_json": json.dumps(definition),
		}
	)
	doc.flags.ignore_validate = True
	return doc.insert(ignore_permissions=True)


class TestSubflow(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.parent_flow = _flow("parent", "Draft", {"nodes": [{"id": "c1", "type": "flow.call"}]})
		self.child_flow = _flow("child", "Active", finished_flow())
		self.draft_flow = _flow("draft", "Draft", finished_flow())
		self.parent = self._run(self.parent_flow)
		self.node = {"id": "c1", "type": "flow.call", "next": "n2"}

	def tearDown(self):
		frappe.set_user("Administrator")
		for flow in (self.parent_flow, self.child_flow, self.draft_flow):
			frappe.db.delete("Flow Member State", {"flow": flow.name})
			frappe.db.delete("Agent Flow Run", {"flow_id": flow.name})
			frappe.delete_doc("Flow Definition", flow.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, flow, status="Running", parent_run=None):
		return frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": flow.name,
				"flow_id": flow.name,
				"status": status,
				"trigger_type": "Manual",
				"parent_run": parent_run,
			}
		).insert(ignore_permissions=True)

	def _call(self, run=None, **config):
		node = {**self.node, "config": config}
		return exec_flow_call(run or self.parent, node, config, {}, GraphContext({}))

	def _children(self):
		return frappe.get_all("Agent Flow Run", filters={"parent_run": self.parent.name}, fields=["name", "status", "parent_node"])

	def _child_of(self, member_key=None, data=None, **config):
		if member_key:
			self.parent.db_set("member_key", member_key)
		config = {"flow_id": self.child_flow.name, **config}
		with patch("frappe.enqueue"):
			out = exec_flow_call(self.parent, {**self.node, "config": config}, config, {}, GraphContext(data or {}))
		self.assertEqual(out["status"], "success", out)
		return frappe.get_doc("Agent Flow Run", out["output"]["run"])

	def test_child_is_about_the_parents_member(self):
		child = self._child_of(member_key="cust-1")
		self.assertEqual(child.member_key, "cust-1")
		self.assertEqual(flow_engine.load_context(child.context_json).data.get("_huf_split"), None)
		result = self._send(child, flow_engine.load_context(child.context_json), "$member", "service", resolve=send.recipient_binder.RecipientUnbound())
		self.assertEqual(self.resolve.call_args.args[1], "cust-1")
		self.assertEqual(result["output"]["status"], "blocked")

	def test_no_member_parent_keeps_the_session_user(self):
		self.assertEqual(self._child_of().member_key, "Administrator")

	def test_held_out_parent_holds_out_the_child(self):
		flag = {"holdout": True, "bucket": 5, "node_id": "sp1"}
		child = self._child_of(member_key="cust-1", data={"_huf_split": flag}, input={"n": 3, "_huf_split": {"holdout": False}})
		data = flow_engine.load_context(child.context_json).data
		self.assertEqual((data["_huf_split"], data["n"]), (flag, 3))
		result = self._send(child, flow_engine.load_context(child.context_json), "+919876543210", "marketing")
		self.resolve.assert_not_called()
		self.assertEqual(result["output"], {"status": "blocked", "reason": "holdout_no_contact"})

	def _send(self, run, ctx, recipient, category, resolve=None):
		"""One send step of ``run`` up to the guard chain, which neither case here may reach."""
		node = step_keys.with_key({"id": "s1", "type": "send.message", "next": "n2"}, frappe.generate_hash())
		config = {"gateway": "gw", "recipient": recipient, "template": "promo", "category": category}
		with patch.object(flow_engine, "_context_of", return_value=ctx), patch.object(flow_engine, "_persist_context"), \
			patch.object(send, "channel_of", return_value="whatsapp"), patch.object(send.guard, "evaluate") as evaluate, \
			patch.object(send.recipient_binder, "resolve", side_effect=resolve) as self.resolve:
			result = send.exec_send_message(run, node, config, {})
		evaluate.assert_not_called()
		return result

	def _wait_for_child(self):
		with patch("frappe.enqueue") as enq:
			out = self._call(flow_id=self.child_flow.name, mode="wait")
		return out, self._children()[0]["name"], enq

	def _reload(self):
		return frappe.get_doc("Agent Flow Run", self.parent.name)

	def test_fire_and_forget_starts_child(self):
		with patch("frappe.enqueue") as enq:
			out = self._call(flow_id=self.child_flow.name, input={"n": 3})
		self.assertEqual(out["status"], "success")
		(child,) = self._children()
		self.assertEqual(child["parent_node"], "c1")
		self.assertEqual(out["output"]["run"], child["name"])
		enq.assert_called_once()
		self.assertEqual(self._reload().status, "Running")  # the parent carries on
		# a fire-and-forget child never wakes anybody
		with patch("frappe.enqueue"):
			flow_engine._complete_flow_run(frappe.get_doc("Agent Flow Run", child["name"]))
		self.assertEqual(self._reload().status, "Running")

	def test_wait_parks_until_child_done(self):
		out, child, enq = self._wait_for_child()
		self.assertEqual(out.status if hasattr(out, "status") else None, "paused")
		parent = self._reload()
		self.assertEqual(parent.status, "Waiting Timer")
		self.assertEqual(json.loads(parent.waiting)["reason"], "child")
		enq.assert_called_once()  # only the child was enqueued, after the parent parked
		with patch("frappe.enqueue"):
			flow_engine._complete_flow_run(frappe.get_doc("Agent Flow Run", child))
		parent = self._reload()
		self.assertEqual(parent.status, "Running")
		self.assertEqual(json.loads(parent.waiting)["woke"]["reason"], "child_done")
		again = self._call(run=parent, flow_id=self.child_flow.name, mode="wait")
		self.assertEqual(again["status"], "success")
		self.assertIn("output", again)
		self.assertEqual(len(self._children()), 1)  # re-entry never starts a second child

	def test_child_done_while_parent_lock_held_is_not_lost(self):
		from huf.ai.flow.runs.park import wake_due_waits

		_out, child, _enq = self._wait_for_child()
		with patch("frappe.enqueue"), patch("huf.ai.flow.engine._acquire_run_lock", return_value=False):
			flow_engine._complete_flow_run(frappe.get_doc("Agent Flow Run", child))
		parent = self._reload()
		self.assertEqual(parent.status, "Waiting Timer")
		self.assertIsNotNone(parent.resume_at)  # handed to the sweeper
		with patch("frappe.enqueue"):
			self.assertIn(parent.name, wake_due_waits(now=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=1)))
		again = self._call(run=self._reload(), flow_id=self.child_flow.name, mode="wait")
		self.assertEqual(again["status"], "success")

	def test_child_failure_routes_on_error(self):
		_out, child, _enq = self._wait_for_child()
		with patch("frappe.enqueue"):
			flow_engine._fail_flow_run(frappe.get_doc("Agent Flow Run", child), "Child blew up")
		again = self._call(run=self._reload(), flow_id=self.child_flow.name, mode="wait")
		self.assertEqual(again["status"], "failed")
		self.assertIn("Child blew up", again["error"])

	def test_depth_limit(self):
		run = self.parent
		for _ in range(MAX_DEPTH):
			run = self._run(self.parent_flow, parent_run=run.name)
		out = self._call(run=run, flow_id=self.child_flow.name)
		self.assertEqual(out["status"], "failed")
		self.assertIn("levels deep", out["error"])
		shallow = self._call(run=self._run(self.parent_flow, parent_run=self.parent.name), flow_id=self.child_flow.name)
		self.assertEqual(shallow["status"], "success")

	def test_unpublished_child_refused(self):
		out = self._call(flow_id=self.draft_flow.name)
		self.assertEqual(out["status"], "failed")
		self.assertIn("not published", out["error"])
		self.assertEqual(self._children(), [])

	def test_self_call_refused(self):
		out = self._call(flow_id=self.parent_flow.name)
		self.assertEqual(out["status"], "failed")
		self.assertIn("cannot run itself", out["error"])

	def test_cancel_parent_cancels_child_waiting(self):
		_out, child, _enq = self._wait_for_child()
		self.assertEqual(frappe.db.get_value("Agent Flow Run", child, "status"), "Queued")
		self.assertTrue(park.cancel_run(self.parent.name, "Administrator"))
		self.assertEqual(self._reload().status, "Cancelled")
		self.assertEqual(frappe.db.get_value("Agent Flow Run", child, "status"), "Cancelled")
