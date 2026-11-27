"""FIX-sec-read-followups: approval card for non-deciders, User Permissions and narrowing on app run lists and
pending approvals, masked member keys.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_read_followups
"""

from unittest import mock

import frappe

from huf.ai.flow import api, engine
from huf.ai.flow.app_scope import access, runs_api
from huf.ai.flow.app_scope.access import flow_access
from huf.ai.flow.app_scope.tests import test_app_read as base
from huf.ai.flow.runs import member, members_api

NAME = "Zelda Quillfeather"


def no_approve(request):
	return request["action"] != "approve"


class TestReadFollowups(base.AppReadFixture):
	def _park_for_approval(self, run, approver):
		waiting = {
			"type": "approval",
			"node_id": "end",
			"approver_type": "user",
			"approver_users": [approver],
			"message": f"Refund {NAME} on {base.PHONE}",
			"headline": f"Refund for {NAME}",
			"card_title": f"Refund for {NAME}",
			"context_summary": f"Customer: {NAME}",
			"facts": [{"label": "Who", "value": NAME}, {"label": "Phone", "value": base.PHONE}],
		}
		frappe.db.set_value(
			"Agent Flow Run", run, {"status": "Waiting Approval", "waiting": frappe.as_json(waiting)}
		)

	def _pending(self, flow):
		return [p["flow_run_id"] for p in api.get_pending_approvals(flow_id=flow)]

	# --- approval card ------------------------------------------------------------------------------------

	def test_card_is_masked_for_a_user_who_cannot_decide(self):
		self._park_for_approval(self.runs[base.FLOW_1], base.USER_APPROVER)
		frappe.set_user(base.USER)
		detail = api.get_flow_run(self.runs[base.FLOW_1])
		self.assertFalse(detail["can_decide"])
		self.assertEqual([f["label"] for f in detail["approval_card"]["facts"]], ["Who", "Phone"])
		for part in (
			detail["approval_card"],
			detail["waiting"],
			api.handle_get_flow_run(self.runs[base.FLOW_1])["waiting"],
		):
			text = frappe.as_json(part)
			self.assertNotIn(NAME, text)
			self.assertNotIn(base.PHONE, text)
		self.assertEqual(detail["waiting"]["approver_users"], [base.USER_APPROVER])

	def test_card_is_whole_for_the_approver(self):
		self._park_for_approval(self.runs[base.FLOW_1], "Administrator")
		detail = api.get_flow_run(self.runs[base.FLOW_1])
		self.assertTrue(detail["can_decide"])
		self.assertEqual(detail["approval_card"]["facts"][0], {"label": "Who", "value": NAME})

	# --- run summaries and pending approvals --------------------------------------------------------------

	def _app_ids(self):
		return {r["run_id"] for r in runs_api.list_app_runs("huf", flow_ids=list(base.FLOWS))}

	def _app_counts(self, group_by):
		rows = runs_api.count_app_runs("huf", group_by=group_by, flow_ids=list(base.FLOWS))
		return sum(r["count"] for r in rows)

	def _approver_sees_both(self):
		for flow in base.FLOWS:
			self._park_for_approval(self.runs[flow], base.USER)
		frappe.get_doc("User", base.USER).add_roles(base.ROLE_APPROVE)

	def test_user_permissions_apply_to_app_summaries_and_pending(self):
		self._approver_sees_both()
		for allow, value in (("Flow Definition", base.FLOW_1), ("Agent Flow Run", self.runs[base.FLOW_1])):
			frappe.set_user("Administrator")
			self._restrict(allow, value)
			frappe.set_user(base.USER)
			self.assertEqual(self._app_ids(), {self.runs[base.FLOW_1]}, allow)
			self.assertEqual(self._app_counts("flow,status"), 1, allow)
			self.assertEqual(self._app_counts("flow,reason"), 1, allow)
			self.assertEqual(self._pending(base.FLOW_1), [self.runs[base.FLOW_1]], allow)
			self.assertEqual(self._pending(base.FLOW_2), [], allow)
			self.doCleanups()

	def test_narrowing_applies_to_app_summaries_and_pending(self):
		self._approver_sees_both()
		self._narrow("only_flow_1")
		frappe.set_user(base.USER)
		self.assertEqual(self._app_ids(), {self.runs[base.FLOW_1]})
		self.assertEqual(self._app_counts("flow,status"), 1)
		self.assertEqual(self._app_counts("flow,reason"), 1)
		self.assertEqual(self._pending(base.FLOW_1), [self.runs[base.FLOW_1]])
		with self.assertRaises(frappe.PermissionError):
			api.get_pending_approvals(flow_id=base.FLOW_2)
		frappe.set_user("Administrator")

	# --- cancelled approvals and the app approve grant ----------------------------------------------------

	def _assert_redacted(self, run, user):
		frappe.set_user(user)
		detail = api.get_flow_run(run)
		self.assertFalse(detail["can_decide"])
		for part in (detail["approval_card"], detail["waiting"], api.handle_get_flow_run(run)["waiting"]):
			text = frappe.as_json(part)
			self.assertNotIn(NAME, text)
			self.assertNotIn(base.PHONE, text)

	def test_card_stays_masked_after_member_removal_cancels_the_run(self):
		run = self.runs[base.FLOW_1]
		self._park_for_approval(run, base.USER_APPROVER)
		member.upsert_member(base.FLOW_1, base.PHONE, run=run)
		frappe.db.set_value("Agent Flow Run", run, "member_key", base.PHONE)
		frappe.set_user(base.USER)
		row = next(r for r in members_api.list_flow_members(base.FLOW_1) if r["member_key"] == "****3210")
		members_api.remove_flow_member(base.FLOW_1, member_ref=row["member_ref"])
		self.assertEqual(frappe.db.get_value("Agent Flow Run", run, "status"), "Cancelled")
		self._assert_redacted(run, base.USER)
		# Once the approval is closed nobody can decide it, so its texts are left out for everyone.
		self._assert_redacted(run, "Administrator")

	def test_named_approver_without_app_approve_grant_cannot_decide(self):
		run = self.runs[base.FLOW_1]
		self._park_for_approval(run, base.USER)
		frappe.get_doc("User", base.USER).remove_roles(base.ROLE_APPROVE)
		self._assert_redacted(run, base.USER)
		self.assertFalse(flow_access(base.USER, base.FLOW_1, "approve"))
		with self.assertRaises(frappe.PermissionError):
			engine.approve_flow_run(run, "approved")

	def test_narrow_refusing_approve_cannot_decide(self):
		run = self.runs[base.FLOW_1]
		self._approver_sees_both()
		patcher = mock.patch.object(access, "narrowers", return_value=[f"{__name__}.no_approve"])
		patcher.start()
		self.addCleanup(patcher.stop)
		self._assert_redacted(run, base.USER)
		with self.assertRaises(frappe.PermissionError):
			engine.approve_flow_run(run, "approved")

	# --- members ------------------------------------------------------------------------------------------

	def test_member_keys_are_masked_and_removable_by_ref(self):
		member.upsert_member(base.FLOW_1, base.PHONE)
		frappe.set_user(base.USER)
		rows = members_api.list_flow_members(base.FLOW_1)
		text = frappe.as_json(rows)
		self.assertNotIn(base.PHONE, text)
		self.assertNotIn(member.member_name(base.FLOW_1, base.PHONE), text)
		row = next(r for r in rows if r["member_key"] == "****3210")
		self.assertEqual(
			members_api.remove_flow_member(base.FLOW_1, member_ref=row["member_ref"]), {"removed": True}
		)
		self.assertFalse(frappe.db.exists("Flow Member State", member.member_name(base.FLOW_1, base.PHONE)))
		with self.assertRaises(frappe.ValidationError):
			members_api.remove_flow_member(base.FLOW_1, member_ref="not-a-ref")
		with self.assertRaises(frappe.ValidationError):
			members_api.remove_flow_member(base.FLOW_1)
