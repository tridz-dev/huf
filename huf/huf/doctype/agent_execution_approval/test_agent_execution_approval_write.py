# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""An Agent Execution Approval authorises code to run, so only server code and the approve/reject endpoints may create
or change one. Every forging case goes through the real generic document APIs.

Run with:
    bench --site <site> run-tests --app huf --module huf.huf.doctype.agent_execution_approval.test_agent_execution_approval_write
"""

import json
from unittest.mock import patch

import frappe
from frappe import client
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.tools.code_execution import stash_pending_execution
from huf.huf.doctype.agent_execution_approval.agent_execution_approval import (
	approve_execution,
	reject_execution,
)
from huf.testing.factories import make_user

APPROVAL = "Agent Execution Approval"
CALL = "Agent Tool Call"
ENQUEUE = "huf.ai.tools.code_execution.enqueue_execution"


class TestExecutionApprovalWrite(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.manager = self._user("Huf Manager")
		self.requester = self._user("Huf Manager")
		self.call = self._insert({"doctype": CALL, "tool": "run_python", "status": "Queued"})
		self.name = self._park(self.requester)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Agent User", {"parenttype": APPROVAL, "parent": ("in", self._approvals())})
		frappe.db.delete(APPROVAL, {"agent_tool_call": self.call})
		frappe.db.delete(CALL, {"name": self.call})
		for user in self._docs:
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _approvals(self):
		return frappe.get_all(APPROVAL, {"agent_tool_call": self.call}, pluck="name") or [""]

	def _insert(self, values):
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def _user(self, role):
		user = make_user(roles=[role])
		self._docs.append(user.name)
		return user.name

	def _values(self, **extra):
		return {
			"doctype": APPROVAL,
			"agent_tool_call": self.call,
			"status": "Pending",
			"expires_on": add_to_date(now_datetime(), hours=1),
			**extra,
		}

	def _park(self, requester):
		name = self._insert(self._values(requested_by=requester))
		stash_pending_execution(name, code="print(1)", profile_snapshot={"limits": {}}, acting_user=requester)
		return name

	def _snapshot(self):
		return frappe.get_doc(APPROVAL, self.name).as_dict()

	def _forged(self, **extra):
		return {**self._snapshot(), "status": "Approved", **extra}

	def _refused(self, call):
		for user in (self.requester, self.manager, "Administrator"):
			frappe.set_user(user)
			with self.subTest(user=user), self.assertRaises(frappe.PermissionError):
				call()
			frappe.set_user("Administrator")

	def test_generic_writes_cannot_record_or_steer_a_decision(self):
		before = self._snapshot()
		forged = {
			"status": "Approved",
			"decided_by": self.manager,
			"requested_by": "",
			"approver_role": "Huf Manager",
			"expires_on": "2099-01-01 00:00:00",
			"code_ref": "forged",
		}
		for field, value in forged.items():
			with self.subTest(field=field):
				self._refused(lambda: client.set_value(APPROVAL, self.name, field, value))
		self._refused(lambda: client.save(frappe.as_json(self._forged())))
		self._refused(lambda: savedocs(frappe.as_json(self._forged()), "Save"))
		self._refused(
			lambda: client.set_value(APPROVAL, self.name, {"flags": {"ignore_permissions": 1, "decision_write": 1}, "status": "Approved"})
		)
		frappe.set_user(self.requester)
		out = client.bulk_update(json.dumps([{"doctype": APPROVAL, "docname": self.name, "status": "Approved"}]))
		frappe.set_user("Administrator")
		self.assertEqual(len(out["failed_docs"]), 1)
		self.assertEqual(self._snapshot(), before)

	def test_generic_apis_cannot_add_an_approver(self):
		row = {"doctype": "Agent User", "parenttype": APPROVAL, "parentfield": "approver_users", "parent": self.name, "user": self.manager}
		self._refused(lambda: client.insert(dict(row)))
		self.assertEqual(frappe.get_doc(APPROVAL, self.name).approver_users, [])

	def test_generic_insert_cannot_create_an_approval(self):
		for status in ("Approved", "Pending"):
			with self.subTest(status=status):
				self._refused(lambda: client.insert(self._values(status=status)))
		self._refused(lambda: client.insert_many(json.dumps([self._values(status="Approved")], default=str)))
		self._refused(lambda: savedocs(frappe.as_json({**self._values(status="Approved"), "__islocal": 1}), "Save"))
		self.assertEqual(self._approvals(), [self.name])

	def test_rename_cannot_move_an_approval(self):
		self._refused(lambda: client.rename_doc(APPROVAL, self.name, f"forged-{frappe.generate_hash(length=6)}"))
		self.assertTrue(frappe.db.exists(APPROVAL, self.name))

	def test_self_approval_is_still_refused(self):
		frappe.set_user(self.requester)
		with self.assertRaises(frappe.PermissionError):
			approve_execution(self.name)
		self.assertEqual(frappe.db.get_value(APPROVAL, self.name, "status"), "Pending")

	def test_approve_endpoint_still_decides(self):
		frappe.set_user(self.manager)
		with patch(ENQUEUE) as enqueue:
			self.assertEqual(approve_execution(self.name, "ok")["status"], "Approved")
		enqueue.assert_called_once()
		self.assertEqual(frappe.db.get_value(APPROVAL, self.name, "decided_by"), self.manager)

	def test_reject_endpoint_still_decides(self):
		frappe.set_user(self.manager)
		self.assertEqual(reject_execution(self.name, "no")["status"], "Rejected")
		self.assertEqual(frappe.db.get_value(APPROVAL, self.name, "decided_by"), self.manager)

	def test_expiry_still_lapses(self):
		frappe.db.set_value(APPROVAL, self.name, "expires_on", "2020-01-01 00:00:00")
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			approve_execution(self.name)
		self.assertEqual(frappe.db.get_value(APPROVAL, self.name, "status"), "Expired")
