"""H-W7-12: app-scoped run summary. User A sees only app A runs; B user and Huf-native user refused; no PII.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_runs_api
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.app_scope import access, runs_api
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

A_FLOW, A_FLOW2, B_FLOW = "test-hw712-a", "test-hw712-a2", "test-hw712-b"
ROLE_A, ROLE_B = "HW712 App A", "HW712 App B"
USER_A, USER_B, USER_HUF = "hw712-a@example.com", "hw712-b@example.com", "hw712-huf@example.com"
PHONE = "919876543210"


def _grants():
	return {
		"huf": {a: frozenset({ROLE_A}) for a in access.ACTIONS},
		"frappe": {a: frozenset({ROLE_B}) for a in access.ACTIONS},
	}


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)


class TestRunsApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		for role in (ROLE_A, ROLE_B):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
		_user(USER_A, ROLE_A)
		_user(USER_B, ROLE_B)
		_user(USER_HUF, "Huf User")
		mock.patch.object(access, "app_grants", side_effect=_grants).start()

	@classmethod
	def tearDownClass(cls):
		mock.patch.stopall()
		frappe.set_user("Administrator")
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		flows = (A_FLOW, A_FLOW2, B_FLOW)
		frappe.db.delete("Agent Flow Run", {"flow_definition": ("in", flows)})
		frappe.db.delete("Flow Definition", {"name": ("in", flows)})
		defn = _graph([_trigger("end"), _end()])
		create_app_flow("huf", A_FLOW, "HW712 A", defn)
		create_app_flow("huf", A_FLOW2, "HW712 A2", defn)
		create_app_flow("frappe", B_FLOW, "HW712 B", defn)
		blocked = {
			"__node_outputs__": {"s1": {"status": "ok"}, "s2": {"reason_code": "freq_cap", "body": PHONE}}
		}
		for flow, status, ctx in (
			(A_FLOW, "Success", None),
			(A_FLOW, "Failed", blocked),
			(A_FLOW2, "Success", None),
			(B_FLOW, "Success", None),
		):
			frappe.get_doc(
				{"doctype": "Agent Flow Run", "flow_definition": flow, "flow_id": flow, "status": status,
				 "member_key": PHONE, "context_json": frappe.as_json(ctx) if ctx else None}
			).insert(ignore_permissions=True)  # fmt: skip

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_app_user_sees_only_own_app_runs(self):
		frappe.set_user(USER_A)
		rows = runs_api.list_app_runs("huf", flow_ids=[A_FLOW, A_FLOW2, B_FLOW])
		self.assertEqual(sorted(r["flow_id"] for r in rows), [A_FLOW, A_FLOW, A_FLOW2])
		failed = runs_api.list_app_runs("huf", status="Failed", flow_ids=[A_FLOW])
		self.assertEqual(len(failed), 1)
		self.assertEqual(failed[0]["reason"], "freq_cap")

	def test_counts_match_rows(self):
		frappe.set_user(USER_A)
		flows = [A_FLOW, A_FLOW2]
		rows = runs_api.list_app_runs("huf", flow_ids=flows)
		for group_by in ("flow,status,reason", "flow,status", "status"):
			counts = runs_api.count_app_runs("huf", group_by=group_by, flow_ids=flows)
			self.assertEqual(sum(c["count"] for c in counts), len(rows), group_by)
		by_status = {
			c["status"]: c["count"] for c in runs_api.count_app_runs("huf", "status", flow_ids=flows)
		}
		self.assertEqual(by_status, {"Success": 2, "Failed": 1})

	def test_other_app_and_native_users_refused(self):
		for user in (USER_B, USER_HUF):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError, msg=user):
				runs_api.list_app_runs("huf")
			with self.assertRaises(frappe.PermissionError, msg=user):
				runs_api.count_app_runs("huf")

	def test_no_pii_and_no_step_outputs(self):
		frappe.set_user(USER_A)
		dumped = frappe.as_json(runs_api.list_app_runs("huf", flow_ids=[A_FLOW]))
		self.assertNotIn(PHONE, dumped)
		self.assertNotIn("__node_outputs__", dumped)
		self.assertIn("****3210", dumped)

	def test_member_filter(self):
		frappe.set_user(USER_A)
		self.assertEqual(len(runs_api.list_app_runs("huf", flow_ids=[A_FLOW], member_key=PHONE)), 2)
		self.assertEqual(runs_api.list_app_runs("huf", flow_ids=[A_FLOW], member_key="nobody"), [])

	def test_test_runs_counted_only_on_request(self):
		run = {"doctype": "Agent Flow Run", "flow_definition": A_FLOW, "flow_id": A_FLOW, "status": "Success"}
		frappe.get_doc({**run, "run_mode": "Test"}).insert(ignore_permissions=True)
		blank = frappe.get_doc(run).insert(ignore_permissions=True)
		frappe.db.set_value("Agent Flow Run", blank.name, "run_mode", None, update_modified=False)
		frappe.set_user(USER_A)
		flows = [A_FLOW, A_FLOW2]
		for group_by in ("flow,status,reason", "status"):
			for kwargs, total in (({}, 4), ({"include_test": "0"}, 4), ({"include_test": 1}, 5)):
				counts = runs_api.count_app_runs("huf", group_by=group_by, flow_ids=flows, **kwargs)
				self.assertEqual(sum(c["count"] for c in counts), total, (group_by, kwargs))
		self.assertEqual(len(runs_api.list_app_runs("huf", flow_ids=flows)), 5)

	def test_bad_group_by_refused(self):
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			runs_api.count_app_runs("huf", group_by="member")
