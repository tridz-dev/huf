# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""FU-APPROVER-VETO: the ``huf_flow_approver_veto`` hook refuses a decider before the run is claimed, fail closed.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_approver_veto_hook
"""

import time
from unittest.mock import patch

import frappe

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support import approver_veto
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out

SEEN = []


def allowing(request):
	SEEN.append(request)
	return False


def vetoing(request):
	return True


def silent(request):
	return None


def falsy(request):
	return 0


def raising(request):
	frappe.throw("boom for ada@example.com")


def slow(request):
	time.sleep(1.1)
	return False


def _hooks(*names):
	real = frappe.get_hooks

	def fake(hook=None, *args, **kwargs):
		if hook == approver_veto.HOOK:
			return {"huf": [n if "." in n else f"{__name__}.{n}" for n in names]} if names else []
		return real(hook, *args, **kwargs)

	return patch("frappe.get_hooks", side_effect=fake)


class TestApproverVeto(WP11Base):
	def setUp(self):
		super().setUp()
		self._runs = []
		SEEN.clear()

	def tearDown(self):
		frappe.db.rollback()
		for name in self._runs:
			frappe.db.delete("Notification Log", {"document_type": "Agent Flow Run", "document_name": name})
		frappe.db.commit()
		super().tearDown()

	def _parked(self, owner_app="huf"):
		nodes = [
			{
				"id": "ask",
				"type": "human.approval",
				"config": {
					"message": "ok?",
					"approver_type": "role",
					"approver_role": "System Manager",
					"approve_next": "yes",
					"reject_next": "no",
				},
			},
			_out("yes", "approved"),
			_out("no", "rejected"),
		]
		flow_id = self._save(_graph(nodes, WEBHOOK))
		run = flow_engine.create_flow_run(flow_id, payload={}, trigger_type="Webhook")
		self._runs.append(run.name)
		flow_engine.run_flow(run.name)
		if owner_app:
			# No second installed app is needed: huf stands in as the owning app.
			frappe.db.set_value("Agent Flow Run", run.name, "owner_app", owner_app, update_modified=False)
		frappe.db.commit()
		run.reload()
		self.assertEqual(run.status, "Waiting Approval", run.last_error)
		return run

	def _assert_refused_everywhere(self, run, *names):
		before = (run.status, run.current_node_id, run.waiting, run.context_json)
		with _hooks(*names):
			for decide in (
				lambda: flow_engine.approve_flow_run(run.name, "approved"),
				lambda: flow_engine.approve_flow_run(run.name, "rejected"),
				lambda: flow_api.approve_flow_run(run.name),
				lambda: flow_api.reject_flow_run(run.name),
			):
				with self.assertRaises(frappe.PermissionError):
					decide()
			self.assertFalse(flow_api.handle_approve_flow_run(run.name)["success"])
			with self.assertRaises(frappe.PermissionError):
				flow_engine.resume_flow_run(run.name)
		run.reload()
		self.assertEqual((run.status, run.current_node_id, run.waiting, run.context_json), before)

	def test_veto_refuses_every_decision_path_before_the_claim(self):
		run = self._parked()
		with patch.object(flow_engine, "_transition_run") as claim:
			self._assert_refused_everywhere(run, "vetoing")
		claim.assert_not_called()

	def test_every_failure_refuses(self):
		run = self._parked()
		for bad in ("silent", "falsy", "raising", "huf.missing.veto"):
			self._assert_refused_everywhere(run, "allowing", bad)
		with patch.object(approver_veto, "_timeout_seconds", return_value=1):
			self._assert_refused_everywhere(run, "slow")

	def test_no_veto_lets_the_decision_through(self):
		run = self._parked()
		with _hooks("allowing"):
			flow_api.approve_flow_run(run.name)
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(
			SEEN[-1],
			{
				"flow_id": run.flow_definition or run.flow_id,
				"flow_run": run.name,
				"node_id": "ask",
				"user": "Administrator",
				"decision": "approved",
				"test_run": False,
			},
		)

	def test_veto_never_grants(self):
		run = self._parked()
		with _hooks("allowing"), patch.object(
			flow_engine, "check_approver", return_value="not an approver"
		), self.assertRaises(frappe.PermissionError):
			flow_engine.approve_flow_run(run.name, "approved")
		self.assertEqual(SEEN, [])

	def test_native_flows_are_never_asked(self):
		run = self._parked(owner_app=None)
		with _hooks("vetoing"):
			flow_engine.approve_flow_run(run.name, "approved")
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
