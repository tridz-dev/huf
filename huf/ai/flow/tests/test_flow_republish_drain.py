"""Republish draining (H-W2-18): parked runs finish on their pinned version, new entries take the new one.

G3 (fail closed): ``live_send`` is enabled per version, so a run parked on an older version never sends live
because a newer version switched ``live_send`` on. The 100k parked drain is DEFERRED to the pre-PR gate.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine
from huf.ai.flow.runs.start import start_flow_for_member
from huf.ai.flow.testrun import gate
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.executor import PinnedVersion

PARKED = 20  # the 100k parked drain is deferred (DEV_STANDARD: no load runs)


def v2_graph():
	graph = finished_flow()
	for node in graph["nodes"]:
		if node.get("type") == "condition":
			node["config"]["expression"] = "input['n'] > 2"
	return graph


class TestRepublishDrain(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-drain-{frappe.generate_hash(length=8)}",
				"flow_name": "Drain Flow",
				"status": "Draft",
				"definition_json": "{}",
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow_id = flow.name
		self.v1 = PinnedVersion.pin(finished_flow())
		self.v2 = PinnedVersion.pin(v2_graph())
		self._publish(finished_flow(), live_send=1)
		check = patch("huf.ai.graph.validation.flow_validation.check_runnable")
		check.start()
		self.addCleanup(check.stop)

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _publish(self, graph, live_send=0):
		frappe.db.set_value(
			"Flow Definition",
			self.flow_id,
			{"definition_json": json.dumps(graph), "status": "Active", "live_send": live_send},
		)

	def _parked_run(self, version):
		return frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": self.flow_id,
				"flow_id": self.flow_id,
				"status": "Waiting Timer",
				"trigger_type": "Manual",
				"pinned_fingerprint": version.fingerprint,
				"pinned_definition": version.to_json(),
			}
		).insert(ignore_permissions=True)

	def test_parked_runs_resume_on_their_pinned_version(self):
		runs = [self._parked_run(self.v1) for _ in range(PARKED)]
		self._publish(v2_graph(), live_send=1)
		for run in runs:
			run.reload()
			pinned = engine._pinned_version(run)
			self.assertEqual(pinned.fingerprint, self.v1.fingerprint)
			self.assertEqual(pinned.graph, self.v1.graph)
		self.assertNotEqual(self.v1.fingerprint, self.v2.fingerprint)

	def test_new_entries_use_the_new_version(self):
		self._parked_run(self.v1)
		self._publish(v2_graph())
		with patch("frappe.enqueue"):
			name = start_flow_for_member(self.flow_id, "m-new", {}, enqueue=False)
		self.assertTrue(name)
		run = frappe.get_doc("Agent Flow Run", name)
		self.assertEqual(run.pinned_fingerprint, self.v2.fingerprint)
		self.assertEqual(engine._pinned_version(run).fingerprint, self.v2.fingerprint)

	def test_deleted_definition_fails_unpinned_parked_run_clearly(self):
		run = self._parked_run(self.v1)
		frappe.db.set_value(
			"Agent Flow Run", run.name, {"pinned_definition": None, "pinned_fingerprint": None}
		)
		run.reload()
		frappe.db.delete("Flow Definition", {"name": self.flow_id})
		with self.assertRaises(engine.FlowDefinitionGone):
			engine._pinned_version(run)

	def test_deleted_definition_still_drains_pinned_run_but_never_live(self):
		run = self._parked_run(self.v1)
		frappe.db.delete("Flow Definition", {"name": self.flow_id})
		self.assertEqual(engine._pinned_version(run).fingerprint, self.v1.fingerprint)
		self.assertFalse(gate.is_live(run))


class TestOlderVersionNeverLive(TestRepublishDrain):
	"""G3: a newer version's ``live_send`` never makes a run parked on an older version send for real."""

	def test_run_on_current_version_is_live(self):
		run = self._parked_run(self.v1)
		self.assertTrue(gate.pin_is_current(run))
		self.assertTrue(gate.is_live(run))

	def test_older_version_is_not_live_after_republish_enables_live_send(self):
		old = self._parked_run(self.v1)
		self._publish(v2_graph(), live_send=1)
		new = self._parked_run(self.v2)
		self.assertTrue(gate.live_send_on(self.flow_id))
		self.assertFalse(gate.pin_is_current(old))
		self.assertFalse(gate.is_live(old))
		self.assertTrue(gate.is_live(new))

	def test_pin_check_fails_closed(self):
		run = self._parked_run(self.v1)
		run.pinned_fingerprint = None
		self.assertFalse(gate.is_live(run))
		run.pinned_fingerprint = self.v1.fingerprint
		with patch.object(frappe.db, "get_value", side_effect=RuntimeError("x")):
			self.assertFalse(gate.pin_is_current(run))
		run.flow_id = None
		self.assertFalse(gate.pin_is_current(run))
