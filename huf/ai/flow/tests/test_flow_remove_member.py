"""``remove_member`` stops every unfinished run of the member, Running ones too, and nothing sends afterwards."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import guard
from huf.ai.flow import engine
from huf.ai.flow.nodes import retry, send, subflow
from huf.ai.flow.runs import member
from huf.ai.flow.support import step_keys
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import GraphContext

NODE = {"id": "s1", "type": "send.message", "next": "n2"}
CONFIG = {"gateway": "gw", "recipient": "+91 98765 43210", "template": "promo", "category": "marketing"}


class TestRemoveMemberStopsRuns(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = "_test-remove-" + frappe.generate_hash(length=8)

	def tearDown(self):
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		frappe.db.commit()

	def _run(self, status="Running", key="m1"):
		doc = frappe.get_doc(
			{"doctype": "Agent Flow Run", "flow_id": self.flow_id, "status": status, "trigger_type": "Manual", "member_key": key}
		)
		doc.flags.ignore_links = doc.flags.ignore_mandatory = True
		return doc.insert(ignore_permissions=True)

	def _status(self, run):
		return frappe.db.get_value("Agent Flow Run", run.name, "status")

	def _remove(self):
		member.upsert_member(self.flow_id, "m1", None)
		self.assertTrue(member.remove_member(self.flow_id, "m1"))

	def test_every_unfinished_run_is_cancelled(self):
		runs = [self._run(status) for status in ("Running", "Queued", "Waiting Timer", "Waiting Approval")]
		done, other = self._run("Success"), self._run("Running", key="m2")
		self._remove()
		self.assertEqual([self._status(run) for run in runs], ["Cancelled"] * 4)
		self.assertEqual(self._status(done), "Success")
		self.assertEqual(self._status(other), "Running")

	def _child_flow(self):
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": "_test-remove-child-" + frappe.generate_hash(length=8),
				"flow_name": "Remove member child",
				"status": "Active",
				"definition_json": json.dumps(finished_flow()),
			}
		)
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.db.commit)
		self.addCleanup(frappe.delete_doc, "Flow Definition", doc.name, ignore_permissions=True, force=True)
		self.addCleanup(frappe.db.delete, "Agent Flow Run", {"flow_id": doc.name})
		return doc.name

	def _wait_for_child(self):
		"""A run parked by the real ``flow.call`` step, and the child it waits for."""
		parent = self._run()
		config = {"flow_id": self._child_flow(), "mode": "wait"}
		with patch("frappe.enqueue"), patch.object(engine, "_persist_context"):
			outcome = subflow.exec_flow_call(parent, {"id": "c1", "config": config}, config, {}, GraphContext({}))
		self.assertTrue(outcome.is_paused)
		return parent, frappe.get_doc("Agent Flow Run", frappe.db.get_value("Agent Flow Run", {"parent_run": parent.name}))

	def test_a_run_parked_for_a_retry_is_cancelled(self):
		run = self._run()
		node = {"id": "t1", "type": "tool.call", "config": {"retry": {"attempts": 3}}}
		with patch.object(engine, "_context_of"), patch.object(engine, "_persist_context"):
			outcome = retry.run_with_retry(run, node, {}, lambda: {"status": "failed", "error": "boom"})
		self.assertTrue(outcome.is_paused)
		self.assertEqual(frappe.db.get_value("Agent Flow Run", run.name, "member_key"), "m1")
		self._remove()
		self.assertEqual(self._status(run), "Cancelled")

	def test_a_run_waiting_for_a_sub_flow_is_cancelled_with_its_child(self):
		parent, child = self._wait_for_child()
		self._remove()
		self.assertEqual([self._status(parent), self._status(child)], ["Cancelled"] * 2)

	def test_a_running_sub_flow_child_is_cancelled_too(self):
		parent, child = self._wait_for_child()
		frappe.db.set_value("Agent Flow Run", child.name, "status", "Running")
		self._remove()
		self.assertEqual([self._status(parent), self._status(child)], ["Cancelled"] * 2)

	def test_worker_holding_the_run_queues_no_send(self):
		stale = self._run()  # what a worker read before the removal: status Running
		self._remove()
		transport = MagicMock(return_value=None)
		with (
			patch.object(guard, "evaluate", return_value=guard.GuardResult(True, None, None, None)),
			patch.object(send, "_enqueue", transport),
			patch.object(send, "channel_of", return_value="whatsapp"),
			patch("huf.ai.flow.testrun.gate.is_live", return_value=True),
			patch.object(send, "is_live", return_value=True),
			patch.object(engine, "_persist_context"),
		):
			node = step_keys.with_key(NODE, frappe.generate_hash())
			result = send.exec_send_message(stale, node, dict(CONFIG), {})
		transport.assert_not_called()
		self.assertEqual(result["output"], {"status": "blocked", "reason": "run_cancelled"})

	def test_worker_starts_no_further_step(self):
		stale = self._run()
		self._remove()
		spec = SimpleNamespace(id="n2", type="output", raw={"id": "n2", "type": "output", "config": {}})
		with patch.object(engine, "_execute_node") as execute, patch.object(engine, "_with_step_key", return_value=spec.raw):
			outcome = engine._make_node_handler(stale, {})(spec, None, None)
		execute.assert_not_called()
		self.assertTrue(outcome.is_paused)
		self.assertEqual(self._status(stale), "Cancelled")

	def test_a_run_that_cannot_be_stopped_keeps_the_member(self):
		self._run()
		member.upsert_member(self.flow_id, "m1", None)
		with patch("huf.ai.flow.runs.park.cancel_run", return_value=False), self.assertRaises(frappe.ValidationError):
			member.remove_member(self.flow_id, "m1")
		self.assertIsNotNone(member.get_member(self.flow_id, "m1"))
