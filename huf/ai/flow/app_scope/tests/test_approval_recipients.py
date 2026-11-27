"""FU-APPROVER-SCOPE: an app flow's approval is announced only to users who may approve that flow.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_approval_recipients
"""

import json
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow.app_scope import access
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.support import approval_notifications as notif
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger
from huf.ai.gateways import approvals as slack

A_FLOW, NATIVE_FLOW = "test-fuas-a", "test-fuas-native"
ROLE = "FUAS App Approver"
PERMITTED, RESTRICTED = "fuas-permitted@example.com", "fuas-restricted@example.com"
NO_ROLE = "fuas-norole@example.com"
NARROW = f"{__name__}.narrow"


def narrow(request):
	return request["user"] != RESTRICTED


def raising_narrow(request):
	if request["user"] == RESTRICTED:
		raise RuntimeError("boom")
	return True


def _grants():
	roles = frozenset({ROLE})
	return {"huf": {"view": roles, "edit": frozenset(), "test": frozenset(), "approve": roles}}


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)


class TestApprovalRecipients(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert()
		_user(PERMITTED, ROLE)
		_user(RESTRICTED, ROLE)
		_user(NO_ROLE, "Desk User")
		for patcher in (
			mock.patch.object(access, "app_grants", side_effect=_grants),
			mock.patch.object(access, "narrowers", return_value=[NARROW]),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.addCleanup(frappe.set_user, "Administrator")
		flows = (A_FLOW, NATIVE_FLOW)
		frappe.db.delete("Agent Flow Run", {"flow_definition": ("in", flows)})
		frappe.db.delete("Flow Definition", {"name": ("in", flows)})
		defn = _graph([_trigger("end"), _end()])
		create_app_flow("huf", A_FLOW, "FUAS A", defn)
		frappe.get_doc(
			{"doctype": "Flow Definition", "flow_id": NATIVE_FLOW, "flow_name": "FUAS native",
			 "status": "Draft", "definition_json": frappe.as_json(defn)}
		).insert(ignore_permissions=True)  # fmt: skip

	def _run(self, flow, waiting):
		return frappe.get_doc(
			{"doctype": "Agent Flow Run", "flow_definition": flow, "flow_id": flow,
			 "status": "Waiting Approval", "waiting": json.dumps(waiting)}
		).insert(ignore_permissions=True)  # fmt: skip

	def _told(self, flow, waiting):
		"""(bell recipients, email recipients, Slack recipients, error log calls)."""
		run = self._run(flow, waiting)
		with (
			mock.patch.object(notif, "enqueue_create_notification") as bell,
			mock.patch.object(notif, "is_email_notifications_enabled", return_value=True),
			mock.patch.object(notif.frappe, "sendmail") as mail,
			mock.patch.object(notif.frappe, "log_error") as log,
		):
			notif._send_approval_notifications(run, {}, {}, waiting)
		with mock.patch.object(slack, "_notify", return_value=0) as card:
			slack.notify_flow_run_approvers(run)
		return (
			{c.args[0] for c in bell.call_args_list},
			{c.kwargs["recipients"][0] for c in mail.call_args_list},
			set(card.call_args.args[2]),
			log.call_args_list,
		)

	def test_role_approvers_are_narrowed_on_all_channels(self):
		bell, mail, card, _ = self._told(A_FLOW, {"approver_type": "role", "approver_role": ROLE})
		self.assertEqual((bell, mail, card), ({PERMITTED}, {PERMITTED}, {PERMITTED}))

	def test_user_approvers_are_narrowed_on_all_channels(self):
		waiting = {"approver_type": "user", "approver_users": [PERMITTED, RESTRICTED, NO_ROLE]}
		bell, mail, card, _ = self._told(A_FLOW, waiting)
		self.assertEqual((bell, mail, card), ({PERMITTED}, {PERMITTED}, {PERMITTED}))

	def test_raising_check_drops_only_that_user(self):
		with mock.patch.object(access, "narrowers", return_value=[f"{__name__}.raising_narrow"]):
			bell, _, card, _ = self._told(A_FLOW, {"approver_type": "role", "approver_role": ROLE})
		self.assertEqual((bell, card), ({PERMITTED}, {PERMITTED}))
		with mock.patch.object(access, "flow_access", side_effect=RuntimeError("boom")):
			self.assertEqual(access.approval_recipients(self._run(A_FLOW, {}), [PERMITTED]), [])

	def test_nobody_left_logs_ids_and_notifies_nobody(self):
		waiting = {"approver_type": "user", "approver_users": [RESTRICTED]}
		bell, mail, card, log = self._told(A_FLOW, waiting)
		self.assertEqual((bell, mail, card), (set(), set(), set()))
		self.assertEqual(len(log), 1)
		self.assertTrue(log[0].kwargs["message"].startswith("No approvers found for flow run "))

	def test_native_flow_is_unchanged(self):
		waiting = {"approver_type": "user", "approver_users": [PERMITTED, RESTRICTED, NO_ROLE]}
		everyone = {PERMITTED, RESTRICTED, NO_ROLE}
		bell, mail, card, _ = self._told(NATIVE_FLOW, waiting)
		self.assertEqual((bell, mail, card), (everyone, everyone, everyone))

	def test_restricted_approver_cannot_decide_or_list(self):
		run = self._run(A_FLOW, {"approver_type": "role", "approver_role": ROLE})
		frappe.set_user(RESTRICTED)
		for call in (flow_api.approve_flow_run, flow_api.reject_flow_run):
			with self.assertRaises(frappe.PermissionError):
				call(run.name)
		with self.assertRaises(frappe.PermissionError):
			flow_api.get_pending_approvals(flow_id=A_FLOW)
		with self.assertRaises(frappe.PermissionError):
			flow_api.get_pending_approvals()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Agent Flow Run", run.name, "status"), "Waiting Approval")
