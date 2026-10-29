# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-21 role consistency: Approve / Reject are only offered to people the server lets decide (B26), and a Huf Role that
grants flow editing the user's Frappe roles cannot honour says so (B28).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux23_roles
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf import permissions
from huf.ai.flow import api as flow_api
from huf.testing.factories import make_user


class TestApprovalDecisionRights(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow_id = f"_test-ux23-{frappe.generate_hash(length=8)}"
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": self.flow_id,
				"flow_name": "UX23 Rights Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "n1", "type": "human.approval", "_label": "Approve the order"}]}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", flow.name))
		self.flow_doc = flow.name

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _waiting_run(self, waiting):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow_doc,
				"flow_id": self.flow_id,
				"status": "Waiting Approval",
				"trigger_type": "Manual",
				"started_at": now_datetime(),
				"waiting": json.dumps(waiting),
			}
		)
		run.insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))
		return run.name

	def _user(self, *roles):
		user = make_user(roles=roles)
		self._docs.append(("User", user.name))
		return user.name

	def test_user_outside_the_approver_role_is_not_offered_the_decision(self):
		run = self._waiting_run({"type": "approval", "approver_type": "role", "approver_role": "System Manager"})
		frappe.set_user(self._user("Huf Manager"))
		detail = flow_api.get_flow_run(run)
		self.assertFalse(detail["can_decide"])
		self.assertIn("System Manager", detail["cannot_decide_reason"])

	def test_user_in_the_approver_role_is_offered_the_decision(self):
		run = self._waiting_run({"type": "approval", "approver_type": "role", "approver_role": "Huf Manager"})
		frappe.set_user(self._user("Huf Manager"))
		detail = flow_api.get_flow_run(run)
		self.assertTrue(detail["can_decide"])
		self.assertIsNone(detail["cannot_decide_reason"])

	def test_named_approvers_only(self):
		email = self._user("Huf Manager")
		run = self._waiting_run({"type": "approval", "approver_type": "user", "approver_users": ["someone-else@example.com"]})
		frappe.set_user(email)
		self.assertFalse(flow_api.get_flow_run(run)["can_decide"])
		frappe.set_user("Administrator")
		run2 = self._waiting_run({"type": "approval", "approver_type": "user", "approver_users": [email]})
		frappe.set_user(email)
		self.assertTrue(flow_api.get_flow_run(run2)["can_decide"])

	def test_a_finished_run_has_nothing_to_decide(self):
		run = self._waiting_run({"type": "approval", "approver_type": "role", "approver_role": "Huf Manager"})
		frappe.db.set_value("Flow Run", run, "status", "Success")
		frappe.set_user(self._user("Huf Manager"))
		detail = flow_api.get_flow_run(run)
		self.assertFalse(detail["can_decide"])
		self.assertIsNone(detail["cannot_decide_reason"])


class TestWithheldFlowCapabilities(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._cleanup):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user_with_role(self, frappe_role):
		"""A Huf User whose Huf Role grants flow editing; `frappe_role` is the Frappe role the Huf Role maps to."""
		email = make_user(roles=("Huf User",)).name
		self._cleanup.append(("User", email))
		role = frappe.get_doc(
			{
				"doctype": "Huf Role",
				"role_name": f"ux23-{frappe.generate_hash(length=5)}",
				"frappe_role": frappe_role,
				"permissions": [{"capability": c} for c in ("flows.use", "flows.create", "flows.manage")],
			}
		).insert(ignore_permissions=True)
		self._cleanup.append(("Huf Role", role.name))
		frappe.get_doc({"doctype": "Huf User Role", "user": email, "huf_role": role.name, "enabled": 1}).insert(ignore_permissions=True)
		self._cleanup.append(("Huf User Role", email))
		frappe.cache().delete_value(f"huf_user_capabilities::{email}")
		return email

	def test_role_whose_frappe_role_cannot_write_flows_reports_what_it_withheld(self):
		frappe.set_user(self._user_with_role("Huf User"))
		me = permissions.get_me()
		self.assertIn("flows.use", me["capabilities"])
		self.assertNotIn("flows.create", me["capabilities"])
		self.assertNotIn("flows.manage", me["capabilities"])
		self.assertEqual(sorted(me["withheld_capabilities"]), ["flows.create", "flows.manage"])

	def test_role_mapped_to_a_frappe_role_that_can_write_flows_keeps_both(self):
		frappe.set_user(self._user_with_role("Huf Manager"))
		me = permissions.get_me()
		self.assertIn("flows.create", me["capabilities"])
		self.assertIn("flows.manage", me["capabilities"])
		self.assertEqual(me["withheld_capabilities"], [])
