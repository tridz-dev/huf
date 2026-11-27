# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""H-W5-03: the ``huf_flow_approval_policy`` hook (audience-size thresholds, approver roles), fail closed.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_approval_policy_hook
"""

import json
from unittest.mock import patch

import frappe

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support.approvers import POLICY_HOOK, check_approver, evaluate_approval_policy
from huf.ai.flow.tests.test_flow_wp11_security import WEBHOOK, WP11Base, _graph, _out

THRESHOLD = 100


def threshold_policy(flow, node, context):
	return {"required": context["data"]["input"]["audience"] > THRESHOLD}


def roles_policy(flow, node, context):
	return {"required": True, "approver_roles": ["Huf Manager", "Blogger"]}


def raising_policy(flow, node, context):
	frappe.throw("boom for ada@example.com")


def skipping_policy(flow, node, context):
	return {"required": False}


def silent_policy(flow, node, context):
	return None


def truthy_policy(flow, node, context):
	return {"required": 0}


def open_role_policy(flow, node, context):
	return {"required": True, "approver_roles": ["All"]}


def mutating_policy(flow, node, context):
	node["config"]["approve_next"] = "no_todo"
	context["data"]["input"]["audience"] = 0
	return None


def _hooks(*names):
	real = frappe.get_hooks

	def fake(hook=None, *args, **kwargs):
		if hook == POLICY_HOOK:
			return [n if "." in n else f"{__name__}.{n}" for n in names]
		return real(hook, *args, **kwargs)

	return patch("frappe.get_hooks", side_effect=fake)


class TestPolicyEvaluation(WP11Base):
	def _evaluate(self, *names, audience=500):
		with _hooks(*names):
			return evaluate_approval_policy("f", {"id": "ask", "config": {}}, {"data": {"input": {"audience": audience}}})

	def test_no_hook_and_no_opinion_keep_the_approval(self):
		for names in ((), ("silent_policy",)):
			policy = self._evaluate(*names)
			self.assertEqual((policy.required, policy.reason, policy.approver_roles), (True, "no_policy", ()))

	def test_one_hook_asking_for_approval_wins(self):
		policy = self._evaluate("skipping_policy", "roles_policy")
		self.assertTrue(policy.required)
		self.assertEqual(policy.approver_roles, ("Huf Manager", "Blogger"))

	def test_every_failure_requires_approval(self):
		for bad in ("raising_policy", "truthy_policy", "open_role_policy", "huf.missing.policy"):
			policy = self._evaluate("skipping_policy", bad)
			self.assertEqual((policy.required, policy.reason), (True, "policy_error"), bad)

	def test_any_of_several_roles_may_decide(self):
		waiting = {"approver_type": "role", "approver_role": "A", "approver_roles": ["A", "B"]}
		self.assertIsNone(check_approver(waiting, "u", ["B"]))
		self.assertIsNotNone(check_approver(waiting, "u", ["C", "All"]))
		self.assertIsNotNone(check_approver(waiting, "u", ["System Manager"]))


class TestApprovalNodeWithPolicy(WP11Base):
	def setUp(self):
		super().setUp()
		self._runs = []

	def tearDown(self):
		frappe.db.rollback()
		for name in self._runs:
			frappe.db.delete("Notification Log", {"document_type": "Agent Flow Run", "document_name": name})
		frappe.db.commit()
		super().tearDown()

	def _run(self, audience, *names):
		def todo(node_id, nxt):
			return {
				"id": node_id,
				"type": "doc.create",
				"config": {"doctype": "ToDo", "fields": {"description": f"{self.marker} {node_id}"}},
				"next": nxt,
			}

		config = {
			"message": "ok?",
			"approver_type": "role",
			"approver_role": "System Manager",
			"approve_next": "yes_todo",
			"reject_next": "no_todo",
		}
		nodes = [
			{"id": "ask", "type": "human.approval", "config": config},
			todo("yes_todo", "yes"),
			todo("no_todo", "no"),
			_out("yes", "approved"),
			_out("no", "rejected"),
		]
		flow_id = self._save(_graph(nodes, WEBHOOK))
		with _hooks(*names):
			run = flow_engine.create_flow_run(flow_id, payload={"audience": audience}, trigger_type="Webhook")
			self._runs.append(run.name)
			flow_engine.run_flow(run.name)
		run.reload()
		return run

	def _todos(self):
		return frappe.get_all("ToDo", filters={"description": ["like", f"{self.marker}%"]}, pluck="description")

	def _assert_parked(self, run, reason):
		self.assertEqual(run.status, "Waiting Approval", run.last_error)
		self.assertEqual(json.loads(run.waiting)["policy_reason"], reason)
		self.assertEqual(self._todos(), [])

	def test_below_threshold_passes_without_waiting(self):
		run = self._run(THRESHOLD, "threshold_policy")
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(self._todos(), [f"{self.marker} yes_todo"])
		decision = json.loads(run.context_json)["__node_outputs__"]["ask"]
		self.assertEqual(
			(decision["decision"], decision["decided_by"], decision["reason"]), ("approved", None, "policy_not_required")
		)

	def test_above_threshold_parks_then_a_person_decides(self):
		run = self._run(THRESHOLD + 1, "threshold_policy")
		self._assert_parked(run, "policy_required")
		frappe.db.commit()
		flow_engine.approve_flow_run(run.name, "approved")
		run.reload()
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(self._todos(), [f"{self.marker} yes_todo"])

	def test_raising_hook_parks_and_logs_no_data(self):
		with patch("frappe.log_error") as log:
			run = self._run(1, "raising_policy")
		self._assert_parked(run, "policy_error")
		self.assertEqual(json.loads(run.waiting)["approver_role"], "System Manager")
		self.assertNotIn("ada@example.com", str(log.call_args_list))

	def test_policy_roles_replace_the_step_approvers(self):
		run = self._run(1, "roles_policy")
		self._assert_parked(run, "policy_required")
		waiting = json.loads(run.waiting)
		self.assertEqual(waiting["approver_roles"], ["Huf Manager", "Blogger"])
		self.assertEqual(waiting["approver_users"], [])
		self.assertIsNotNone(check_approver(waiting, "u", ["System Manager"]))
		self.assertIsNone(check_approver(waiting, "u", ["Blogger"]))

	def test_hook_cannot_change_the_run(self):
		run = self._run(500, "mutating_policy")
		self._assert_parked(run, "no_policy")
		self.assertEqual(json.loads(run.context_json)["input"]["audience"], 500)
