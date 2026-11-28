"""H-W7-08: delegated, app-scoped permissions on app-owned flows, runs and member states.

App A is ``huf``, app B is ``frappe`` (both installed). Users hold only an app role; none holds a Huf role.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_access
"""

from unittest import mock

import frappe
import frappe.client
from frappe.tests import IntegrationTestCase

from huf.ai.flow.app_scope import access, docperms
from huf.ai.flow.app_scope.access import flow_access, set_app_flow_status
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

A_FLOW, B_FLOW, NATIVE_FLOW = "test-hw708-a", "test-hw708-b", "test-hw708-native"
ROLE_A, ROLE_B, ROLE_A_VIEW = "HW708 App A Editor", "HW708 App B Editor", "HW708 App A Viewer"
USER_A, USER_A_VIEW, USER_B = "hw708-a@example.com", "hw708-aview@example.com", "hw708-b@example.com"
USER_HUF, USER_SM = "hw708-hufuser@example.com", "hw708-sm@example.com"
EMPTY = frozenset()


def _grants(view_a=(ROLE_A_VIEW,), with_b=True):
	g = {
		"huf": {
			"view": frozenset(view_a) | {ROLE_A},
			"edit": frozenset({ROLE_A}),
			"test": EMPTY,
			"approve": EMPTY,
		}
	}
	if with_b:
		g["frappe"] = {
			"view": frozenset({ROLE_B}),
			"edit": frozenset({ROLE_B}),
			"test": EMPTY,
			"approve": EMPTY,
		}
	return g


def _defn():
	return _graph([_trigger("end"), _end()])


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)


class TestAppScopedAccess(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		for role in (ROLE_A, ROLE_B, ROLE_A_VIEW):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
		_user(USER_A, ROLE_A)
		_user(USER_A_VIEW, ROLE_A_VIEW)
		_user(USER_B, ROLE_B)
		_user(USER_HUF, "Huf User")
		_user(USER_SM, "System Manager")
		cls.patcher = mock.patch.object(access, "app_grants", side_effect=lambda: _grants())
		cls.patcher.start()
		mock.patch.object(docperms, "app_grants", side_effect=lambda: _grants()).start()
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
		flows = (A_FLOW, B_FLOW, NATIVE_FLOW)
		frappe.db.delete("Flow Member State", {"flow": ("in", flows)})
		frappe.db.delete("Agent Flow Run", {"flow_definition": ("in", flows)})
		frappe.db.delete("Flow Definition", {"name": ("in", flows)})
		create_app_flow("huf", A_FLOW, "HW708 A", _defn())
		create_app_flow("frappe", B_FLOW, "HW708 B", _defn())
		frappe.get_doc(
			{"doctype": "Flow Definition", "flow_id": NATIVE_FLOW, "flow_name": "HW708 native",
			 "status": "Draft", "definition_json": frappe.as_json(_defn())}
		).insert(ignore_permissions=True)  # fmt: skip
		self.runs = {}
		for flow in flows:
			run = frappe.get_doc({"doctype": "Agent Flow Run", "flow_definition": flow}).insert(
				ignore_permissions=True
			)
			self.runs[flow] = run.name
			frappe.get_doc({"doctype": "Flow Member State", "flow": flow, "member_key": f"m-{flow}"}).insert(
				ignore_permissions=True
			)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _as(self, user):
		frappe.set_user(user)

	# --- Flow Definition ----------------------------------------------------------------------------------

	def test_app_user_lists_only_own_flows(self):
		self._as(USER_A)
		names = set(frappe.get_list("Flow Definition", pluck="name", limit_page_length=0))
		self.assertIn(A_FLOW, names)
		self.assertNotIn(B_FLOW, names)
		self.assertNotIn(NATIVE_FLOW, names)
		self._as(USER_B)
		names = set(frappe.get_list("Flow Definition", pluck="name", limit_page_length=0))
		self.assertEqual(names & {A_FLOW, B_FLOW, NATIVE_FLOW}, {B_FLOW})

	def test_app_user_get_is_scoped(self):
		self._as(USER_A)
		self.assertEqual(frappe.client.get("Flow Definition", A_FLOW)["name"], A_FLOW)
		for other in (B_FLOW, NATIVE_FLOW):
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get("Flow Definition", other)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Flow Definition", other).check_permission("read")

	def test_app_user_saves_own_flow_only(self):
		self._as(USER_A)
		doc = frappe.get_doc("Flow Definition", A_FLOW)
		doc.description = "edited by A"
		doc.save()
		self.assertEqual(frappe.db.get_value("Flow Definition", A_FLOW, "description"), "edited by A")
		for other in (B_FLOW, NATIVE_FLOW):
			with self.assertRaises(frappe.PermissionError):
				frappe.client.set_value("Flow Definition", other, "description", "by A")

	def test_viewer_is_read_only(self):
		self._as(USER_A_VIEW)
		self.assertTrue(frappe.has_permission("Flow Definition", "read", A_FLOW))
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Flow Definition", A_FLOW, "description", "x")

	def test_app_user_cannot_activate_live_send_create_or_delete(self):
		self._as(USER_A)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Flow Definition", A_FLOW, "status", "Active")
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Flow Definition", A_FLOW, "live_send", 1)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Flow Definition", A_FLOW).db_set("status", "Active")
		with self.assertRaises(frappe.PermissionError):
			frappe.client.delete("Flow Definition", A_FLOW)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.insert(
				{"doctype": "Flow Definition", "flow_id": "test-hw708-new", "flow_name": "x",
				 "status": "Draft", "definition_json": frappe.as_json(_defn())}
			)  # fmt: skip
		frappe.set_user("Administrator")
		row = frappe.db.get_value("Flow Definition", A_FLOW, ["status", "live_send"], as_dict=True)
		self.assertEqual((row.status, row.live_send), ("Draft", 0))
		self.assertTrue(frappe.db.exists("Flow Definition", A_FLOW))

	def test_server_path_may_set_status(self):
		set_app_flow_status("huf", A_FLOW, "Draft", live_send=False)
		with self.assertRaises(frappe.PermissionError):
			set_app_flow_status("frappe", A_FLOW, "Draft")

	def test_huf_user_sees_no_app_flows(self):
		self._as(USER_HUF)
		names = set(frappe.get_list("Flow Definition", pluck="name", limit_page_length=0))
		self.assertIn(NATIVE_FLOW, names)
		self.assertFalse(names & {A_FLOW, B_FLOW})
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("Flow Definition", A_FLOW)

	def test_privileged_see_everything(self):
		self._as(USER_SM)
		names = set(frappe.get_list("Flow Definition", pluck="name", limit_page_length=0))
		self.assertTrue({A_FLOW, B_FLOW, NATIVE_FLOW} <= names)

	def test_flow_access_matrix(self):
		self.assertTrue(flow_access(USER_A, A_FLOW, "view"))
		self.assertTrue(flow_access(USER_A, A_FLOW, "edit"))
		self.assertFalse(flow_access(USER_A, A_FLOW, "test"))
		self.assertFalse(flow_access(USER_A, A_FLOW, "approve"))
		self.assertFalse(flow_access(USER_A, A_FLOW, "bogus"))
		self.assertFalse(flow_access(USER_A, "no-such-flow", "view"))
		for action in access.ACTIONS:
			self.assertFalse(flow_access(USER_A, B_FLOW, action))
			self.assertFalse(flow_access(USER_A, NATIVE_FLOW, action))
			self.assertFalse(flow_access(USER_HUF, A_FLOW, action))
			self.assertTrue(flow_access(USER_SM, B_FLOW, action))
		self.assertFalse(flow_access(USER_A_VIEW, A_FLOW, "edit"))

	def test_no_huf_role_needed(self):
		for user in (USER_A, USER_A_VIEW, USER_B):
			self.assertFalse(set(frappe.get_roles(user)) & {"Huf User", "Huf Viewer", "Huf Manager"})
		self.assertTrue(flow_access(USER_A, A_FLOW, "view"))

	# --- runs and member states -----------------------------------------------------------------------------

	def test_app_roles_read_no_run_or_state_documents(self):
		"""Raw payloads: app roles get runs only through the masked APIs (see test_app_read)."""
		self._as(USER_A)
		for doctype in ("Agent Flow Run", "Flow Member State"):
			self.assertFalse(frappe.has_permission(doctype, "read"))
		for flow in (A_FLOW, B_FLOW, NATIVE_FLOW):
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get("Agent Flow Run", self.runs[flow])
			state = frappe.db.get_value("Flow Member State", {"flow": flow}, "name", ignore=True)
			self.assertFalse(frappe.has_permission("Flow Member State", "read", state))

	def test_app_user_cannot_write_runs_or_states(self):
		self._as(USER_A)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Agent Flow Run", self.runs[A_FLOW], "status", "Completed")
		state = frappe.db.get_value("Flow Member State", {"flow": A_FLOW}, "name")
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Flow Member State", state, "status", "Completed")
		with self.assertRaises(frappe.PermissionError):
			frappe.client.insert({"doctype": "Agent Flow Run", "flow_definition": A_FLOW})

	def test_huf_user_sees_no_app_runs(self):
		self._as(USER_HUF)
		runs = set(frappe.get_list("Agent Flow Run", pluck="flow_definition", limit_page_length=0))
		self.assertIn(NATIVE_FLOW, runs)
		self.assertFalse(runs & {A_FLOW, B_FLOW})

	# --- DocPerm sync -------------------------------------------------------------------------------------

	def test_sync_is_idempotent_and_least_privilege(self):
		docperms.sync_app_flow_docperms()
		docperms.sync_app_flow_docperms()
		rows = frappe.get_all(
			"Custom DocPerm", filters={"role": ("in", [ROLE_A, ROLE_B, ROLE_A_VIEW])}, fields=["*"]
		)
		keys = [(r.parent, r.role) for r in rows]
		self.assertEqual(len(keys), len(set(keys)))
		self.assertEqual(len(keys), 3)
		self.assertEqual({parent for parent, _role in keys}, {"Flow Definition"})
		for r in rows:
			self.assertEqual(r.permlevel, 0)
			for f in ("create", "delete", "share", "export", "import", "submit", "amend", "cancel"):
				self.assertFalse(r.get(f), (r.parent, r.role, f))
			self.assertEqual(bool(r.write), r.parent == "Flow Definition" and r.role != ROLE_A_VIEW)
		# Huf's own standard rows survive the switch to custom perms.
		self.assertTrue(
			frappe.db.exists("Custom DocPerm", {"parent": "Flow Definition", "role": "Huf Manager"})
		)

	def test_removing_app_removes_rows(self):
		with mock.patch.object(docperms, "app_grants", side_effect=lambda: _grants(with_b=False)):
			docperms.sync_app_flow_docperms()
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"role": ROLE_B}))
		self.assertTrue(frappe.db.exists("Custom DocPerm", {"role": ROLE_A}))
		docperms.sync_app_flow_docperms()
		self.assertTrue(frappe.db.exists("Custom DocPerm", {"role": ROLE_B}))

	def test_protected_roles_are_never_delegated(self):
		with mock.patch.object(
			frappe, "get_hooks",
			return_value={"huf": {"view": ["Huf User", "System Manager", ROLE_A], "edit": ["Huf Manager"]}},
		):  # fmt: skip
			self.patcher.stop()
			try:
				grants = access.app_grants()
			finally:
				self.patcher.start()
		self.assertEqual(grants["huf"]["view"], frozenset({ROLE_A}))
		self.assertEqual(grants["huf"]["edit"], EMPTY)

	def test_app_cannot_grant_on_another_app(self):
		def hooks(name, app_name=None, **kw):
			return {"huf": {"view": [ROLE_B]}} if app_name == "frappe" else {}

		self.patcher.stop()
		try:
			with mock.patch.object(frappe, "get_hooks", side_effect=hooks):
				grants = access.app_grants()
		finally:
			self.patcher.start()
		self.assertNotIn("huf", grants)
