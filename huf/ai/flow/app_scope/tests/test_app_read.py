"""FIX-sec-app-read: what a delegated app role may read of runs, member states and people.

App A is ``huf`` (view, edit, test and approve roles). Users hold no Huf role.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_app_read
"""

from unittest import mock

import frappe
import frappe.client
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api, run_identity_api
from huf.ai.flow.app_scope import access, docperms, runs_api
from huf.ai.flow.app_scope.access import flow_access
from huf.ai.flow.app_scope.api_guards import guard_run
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.catalog import form_options_api
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

FLOW_1, FLOW_2 = "test-secread-1", "test-secread-2"
FLOWS = (FLOW_1, FLOW_2)
ROLE, ROLE_APPROVE, ROLE_OTHER = "SecRead App Editor", "SecRead App Approver", "SecRead Other"
USER, USER_APPROVER = "secread-a@example.com", "secread-approver@example.com"
USER_OTHER, USER_BOTH = "secread-other@example.com", "secread-both@example.com"
PHONE = "919876543210"
EMAIL = "member.secret@example.com"


def _grants():
	return {
		"huf": {
			"view": frozenset({ROLE}),
			"edit": frozenset({ROLE}),
			"test": frozenset({ROLE}),
			"approve": frozenset({ROLE_APPROVE}),
		}
	}


def only_flow_1(request):
	return request["flow_id"] == FLOW_1


def broken(request):
	raise RuntimeError


def truthy(request):
	return "yes"


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)


class AppReadFixture(IntegrationTestCase):
	"""Two app-owned flows with one run and one member each, and the app's users. No tests of its own."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		for role in (ROLE, ROLE_APPROVE, ROLE_OTHER):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
		_user(USER, ROLE)
		_user(USER_APPROVER, ROLE_APPROVE)
		_user(USER_OTHER, ROLE_OTHER)
		_user(USER_BOTH, ROLE, "Huf User")
		mock.patch.object(access, "app_grants", side_effect=_grants).start()
		mock.patch.object(docperms, "app_grants", side_effect=_grants).start()
		docperms.sync_app_flow_docperms()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		with mock.patch.object(docperms, "app_grants", return_value={}):
			docperms.sync_app_flow_docperms()
		mock.patch.stopall()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Member State", {"flow": ("in", FLOWS)})
		frappe.db.delete("Agent Flow Run", {"flow_definition": ("in", FLOWS)})
		frappe.db.delete("Flow Definition", {"name": ("in", FLOWS)})
		self.runs, self.states = {}, {}
		for flow in FLOWS:
			create_app_flow("huf", flow, flow, _graph([_trigger("end"), _end()]))
			self.runs[flow] = (
				frappe.get_doc(
					{
						"doctype": "Agent Flow Run",
						"flow_definition": flow,
						"flow_id": flow,
						"status": "Waiting User",
						"context_json": frappe.as_json({"phone": PHONE, "mail": EMAIL}),
						"waiting": frappe.as_json({"type": "reply", "phone": PHONE}),
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
			self.states[flow] = (
				frappe.get_doc({"doctype": "Flow Member State", "flow": flow, "member_key": f"m-{flow}"})
				.insert(ignore_permissions=True)
				.name
			)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _narrow(self, fn):
		patcher = mock.patch.object(access, "narrowers", side_effect=lambda app: [f"{__name__}.{fn}"])
		patcher.start()
		self.addCleanup(patcher.stop)

	def _restrict(self, allow, value):
		doc = frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": USER,
				"allow": allow,
				"for_value": value,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.clear_cache, user=USER)
		self.addCleanup(doc.delete, ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.clear_cache(user=USER)


class TestAppRead(AppReadFixture):
	# --- raw documents ------------------------------------------------------------------------------------

	def test_app_roles_do_not_read_raw_runs_or_states(self):
		for user in (USER, USER_BOTH):
			frappe.set_user(user)
			for doctype, names in (("Agent Flow Run", self.runs), ("Flow Member State", self.states)):
				with self.assertRaises(frappe.PermissionError, msg=(user, doctype)):
					frappe.client.get(doctype, names[FLOW_1])
				try:
					listed = frappe.get_list(doctype, pluck="name", limit_page_length=0)
				except frappe.PermissionError:
					listed = []
				self.assertFalse(set(listed) & set(names.values()), (user, doctype))

	def test_app_user_still_reads_runs_through_masked_apis(self):
		frappe.set_user(USER)
		detail = api.get_flow_run(self.runs[FLOW_1])
		self.assertNotIn(PHONE, frappe.as_json(detail))
		rows = api.list_flow_runs(flow_id=FLOW_1)
		self.assertEqual([r["name"] for r in rows], [self.runs[FLOW_1]])
		self.assertEqual(api.list_flow_runs_page(flow_id=FLOW_1)["total"], 1)

	def test_agent_tool_get_run_is_masked(self):
		frappe.set_user(USER)
		result = api.handle_get_flow_run(self.runs[FLOW_1])
		self.assertTrue(result["success"], result)
		text = frappe.as_json(result)
		self.assertNotIn(PHONE, text)
		self.assertNotIn(EMAIL, text)

	# --- User Permissions ---------------------------------------------------------------------------------

	def _assert_run_refused(self, run):
		with self.assertRaises(frappe.PermissionError):
			api.get_flow_run(run)
		with self.assertRaises(frappe.PermissionError):
			run_identity_api.get_flow_run_identity(run)
		result = api.handle_get_flow_run(run)
		self.assertNotIn("success", result)
		self.assertIn("error", result)
		self.assertEqual(api.get_flow_step_labels([{"flow_run": run, "flow_node_id": "end"}]), [None])

	def test_user_permission_on_flow_hides_other_flows_runs(self):
		self._restrict("Flow Definition", FLOW_1)
		frappe.set_user(USER)
		self.assertTrue(api.get_flow_run(self.runs[FLOW_1]))
		self.assertTrue(run_identity_api.get_flow_run_identity(self.runs[FLOW_1]))
		self.assertTrue(api.handle_get_flow_run(self.runs[FLOW_1])["success"])
		self._assert_run_refused(self.runs[FLOW_2])

	def test_user_permission_on_runs_applies_to_detail_and_lists(self):
		hidden = (
			frappe.get_doc(
				{
					"doctype": "Agent Flow Run",
					"flow_definition": FLOW_1,
					"flow_id": FLOW_1,
					"status": "Waiting User",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self._restrict("Agent Flow Run", self.runs[FLOW_1])
		frappe.set_user(USER)
		self._assert_run_refused(hidden)
		self.assertEqual([r["name"] for r in api.list_flow_runs(flow_id=FLOW_1)], [self.runs[FLOW_1]])
		page = api.list_flow_runs_page(flow_id=FLOW_1)
		self.assertEqual((page["total"], [r["name"] for r in page["items"]]), (1, [self.runs[FLOW_1]]))

	# --- narrowing hook -----------------------------------------------------------------------------------

	def test_narrowing_hook_scopes_every_path(self):
		self._narrow("only_flow_1")
		frappe.set_user(USER)
		self.assertTrue(flow_access(USER, FLOW_1, "view"))
		for action in access.ACTIONS:
			self.assertFalse(flow_access(USER, FLOW_2, action))
		listed = set(frappe.get_list("Flow Definition", pluck="name", limit_page_length=0))
		self.assertEqual(listed & set(FLOWS), {FLOW_1})
		self.assertFalse(frappe.has_permission("Flow Definition", "write", doc=FLOW_2))
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("Flow Definition", FLOW_2)
		with self.assertRaises(frappe.PermissionError):
			guard_run(self.runs[FLOW_2], "view")
		with self.assertRaises(frappe.PermissionError):
			api.get_flow_run(self.runs[FLOW_2])
		self.assertEqual(
			{r["flow_id"] for r in runs_api.list_app_runs("huf", flow_ids=list(FLOWS))}, {FLOW_1}
		)

	def test_narrowing_hook_fails_closed(self):
		for fn in ("broken", "truthy", "no_such_function"):
			with mock.patch.object(access, "narrowers", return_value=[f"{__name__}.{fn}"]):
				self.assertFalse(flow_access(USER, FLOW_1, "view"), fn)
				self.assertTrue(flow_access("Administrator", FLOW_1, "view"), fn)

	# --- people and roles ---------------------------------------------------------------------------------

	def test_app_user_looks_up_only_approvers_of_the_app(self):
		frappe.set_user(USER)
		names = {r["name"] for r in form_options_api.search_flow_users("secread", limit=50)}
		self.assertEqual(names, {USER_APPROVER})
		found = {
			r["name"]: r["found"] for r in form_options_api.check_flow_users([USER_APPROVER, USER_OTHER])
		}
		self.assertEqual(found, {USER_APPROVER: True, USER_OTHER: False})
		self.assertEqual([r["name"] for r in api.get_approver_roles()], [ROLE_APPROVE])
