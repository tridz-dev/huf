"""H-W7-09: every whitelisted flow API is classified and app-scoped; /huf lockout; embed access and policy.

App A is ``huf``, app B is ``frappe`` (both installed). USER_A holds only app A's role (view, edit, test, approve).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_api_guards
"""

import ast
import importlib
import inspect
import pkgutil
import textwrap
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request
from werkzeug.datastructures import Headers

import huf.ai.flow
from huf.ai.flow.app_scope import access, api_guards, docperms
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger
from huf.www import huf as page

A_FLOW, B_FLOW, NATIVE_FLOW = "test-hw709-a", "test-hw709-b", "test-hw709-native"
ROLE_A, ROLE_B = "HW709 App A", "HW709 App B"
USER_A, USER_HUF = "hw709-a@example.com", "hw709-hufuser@example.com"

#: Guard -> what an app-only user gets on another app's flow and on a Huf-native flow.
FLOW_GUARDS = {"guard_flow", "guard_run", "guard_huf_flow", "guard_flow_or_huf"}
ALL_GUARDS = FLOW_GUARDS | {"guard_huf_only", "guard_app_meta", "guard_app_named", "guard_public"}
FLOW_PARAMS = {"flow_id", "flow"}
RUN_PARAMS = {"flow_run_id", "flow_run_name", "flow_run"}


def _grants():
	every = {a: frozenset({ROLE_A}) for a in access.ACTIONS}
	return {"huf": every, "frappe": {a: frozenset({ROLE_B}) for a in access.ACTIONS}}


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)


def whitelisted_flow_functions() -> dict:
	"""``{dotted path: function}`` for every whitelisted function defined under ``huf.ai.flow`` (tests excluded)."""
	for info in pkgutil.walk_packages(huf.ai.flow.__path__, "huf.ai.flow."):
		if ".tests" in info.name or info.name.split(".")[-1].startswith("test_"):
			continue
		importlib.import_module(info.name)
	found = {}
	for fn in frappe.whitelisted:
		fn = inspect.unwrap(fn)
		module = getattr(fn, "__module__", "") or ""
		if module.startswith("huf.ai.flow.") and ".tests" not in module:
			found[f"{module}.{fn.__qualname__}"] = fn
	return found


def guard_of(fn) -> str | None:
	"""Name of the ``api_guards`` function the body calls first, or None."""
	tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
	for node in ast.walk(tree):
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ALL_GUARDS:
			return node.func.id
	return None


class TestApiGuards(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		for role in (ROLE_A, ROLE_B):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
		_user(USER_A, ROLE_A)
		_user(USER_HUF, "Huf User")
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
		flows = (A_FLOW, B_FLOW, NATIVE_FLOW)
		frappe.db.delete("Agent Flow Run", {"flow_definition": ("in", flows)})
		frappe.db.delete("Flow Definition", {"name": ("in", flows)})
		defn = _graph([_trigger("end"), _end()])
		create_app_flow("huf", A_FLOW, "HW709 A", defn)
		create_app_flow("frappe", B_FLOW, "HW709 B", defn)
		frappe.get_doc(
			{"doctype": "Flow Definition", "flow_id": NATIVE_FLOW, "flow_name": "HW709 native",
			 "status": "Draft", "definition_json": frappe.as_json(defn)}
		).insert(ignore_permissions=True)  # fmt: skip
		self.runs = {
			f: frappe.get_doc({"doctype": "Agent Flow Run", "flow_definition": f, "flow_id": f})
			.insert(ignore_permissions=True)
			.name
			for f in flows
		}
		self._saved_request = getattr(frappe.local, "request", None)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.request = self._saved_request
		frappe.local.response_headers = Headers()

	# --- introspection table --------------------------------------------------------------------------------

	def test_every_whitelisted_flow_api_is_classified(self):
		functions = whitelisted_flow_functions()
		self.assertGreater(len(functions), 40)
		unclassified = sorted(name for name, fn in functions.items() if guard_of(fn) is None)
		self.assertEqual(unclassified, [], "whitelisted flow APIs without an api_guards guard")

	def _kwargs(self, fn, flow):
		kwargs = {}
		for name, param in inspect.signature(fn).parameters.items():
			if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
				continue
			if name in FLOW_PARAMS:
				kwargs[name] = flow
			elif name in RUN_PARAMS:
				kwargs[name] = self.runs[flow]
			elif param.default is param.empty:
				kwargs[name] = "approved" if name == "decision" else "x"
		return kwargs

	def test_app_user_is_refused_on_other_and_native_flows(self):
		for name, fn in sorted(whitelisted_flow_functions().items()):
			guard = guard_of(fn)
			if guard in (None, "guard_public", "guard_app_meta"):
				continue
			for flow in (B_FLOW, NATIVE_FLOW):
				frappe.set_user(USER_A)
				kwargs = self._kwargs(fn, flow)
				if guard in FLOW_GUARDS and not (set(kwargs) & (FLOW_PARAMS | RUN_PARAMS)):
					continue  # a flow-or-huf list called without its flow: covered as Huf-wide below
				with self.assertRaises(frappe.PermissionError, msg=f"{name} on {flow}"):
					fn(**kwargs)

	def test_app_user_passes_guards_on_own_flow(self):
		frappe.set_user(USER_A)
		for action in access.ACTIONS:
			api_guards.guard_flow(A_FLOW, action)
			api_guards.guard_run(self.runs[A_FLOW], action)
		api_guards.guard_app_named("huf")
		api_guards.guard_app_meta()
		for refused in (
			lambda: api_guards.guard_huf_flow(A_FLOW),  # publish, settings: the host app's path only
			lambda: api_guards.guard_huf_only(),
			lambda: api_guards.guard_app_named("frappe"),
			lambda: api_guards.guard_app_named(None),
			lambda: api_guards.guard_flow_or_huf(None, "view"),
		):
			with self.assertRaises(frappe.PermissionError):
				refused()

	def test_huf_user_does_not_reach_app_flows(self):
		frappe.set_user(USER_HUF)
		api_guards.guard_flow(NATIVE_FLOW, "view")
		api_guards.guard_huf_only()
		for flow in (A_FLOW, B_FLOW):
			with self.assertRaises(frappe.PermissionError):
				api_guards.guard_flow(flow, "view")

	def test_list_node_types_refuses_an_app_the_user_may_not_view(self):
		from huf.ai.flow.catalog.api import list_node_types

		frappe.set_user(USER_A)
		with self.assertRaises(frappe.PermissionError):
			list_node_types(app="frappe")
		with self.assertRaises(frappe.PermissionError):
			list_node_types()

	def test_publish_is_refused_for_app_user(self):
		from huf.ai.flow.api import publish_flow, unpublish_flow

		frappe.set_user(USER_A)
		for fn in (publish_flow, unpublish_flow):
			with self.assertRaises(frappe.PermissionError):
				fn(A_FLOW)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Flow Definition", A_FLOW, "status"), "Draft")

	def test_dry_run_by_app_user_never_sends(self):
		"""G2/G5: a test by an app-only user is always a dry run and queues nothing on the outbox."""
		from huf.ai.channels import outbox
		from huf.ai.flow.api import run_flow

		frappe.set_user(USER_A)
		with mock.patch.object(outbox, "enqueue") as enqueue:
			result = run_flow(A_FLOW, payload={}, mode="real")
		enqueue.assert_not_called()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Agent Flow Run", result["flow_run_id"], "run_mode"), "Test")

	# --- /huf lockout and embed -----------------------------------------------------------------------------

	def _open(self, path):
		set_request(method="GET", path=path)
		frappe.local.response_headers = Headers()
		with mock.patch.object(page, "build_boot_context", return_value={}) as boot:
			page.get_context(frappe._dict())
		return boot

	def test_huf_app_is_403_for_app_user_without_boot(self):
		frappe.set_user(USER_A)
		for path in ("/huf", "/huf/flows", f"/huf/flows/{A_FLOW}"):
			set_request(method="GET", path=path)
			frappe.local.response_headers = Headers()
			with mock.patch.object(page, "build_boot_context") as boot, self.assertRaises(
				page.HufNotPermitted, msg=path
			) as raised:
				page.get_context(frappe._dict())
			boot.assert_not_called()
			self.assertEqual(raised.exception.http_status_code, 403)

	def test_guest_and_huf_user_keep_the_app(self):
		for user in ("Guest", USER_HUF):
			frappe.set_user(user)
			self._open("/huf/flows").assert_called_once()

	def test_embed_of_own_app_flow_carries_policy(self):
		frappe.set_user(USER_A)
		extra = self._open(f"/huf/embed/flow/{A_FLOW}").call_args.args[0]
		self.assertEqual(
			extra["huf_embed"]["policy"],
			{"publish": "host", "test": "dry_run", "can_edit": True, "can_test": True, "can_approve": True},
		)
		for value in extra["huf_embed"]["policy"].values():
			self.assertIsInstance(value, (bool, str))

	def test_embed_of_other_app_or_native_flow_is_403(self):
		frappe.set_user(USER_A)
		for flow in (B_FLOW, NATIVE_FLOW, "no-such-flow"):
			with self.assertRaises(page.EmbedNotPermitted, msg=flow):
				self._open(f"/huf/embed/flow/{flow}")

	def test_native_embed_has_no_policy(self):
		frappe.set_user("Administrator")
		extra = self._open(f"/huf/embed/flow/{NATIVE_FLOW}").call_args.args[0]
		self.assertNotIn("policy", extra["huf_embed"])
