"""H-W7-11: approval email, bell entry and ``view_link`` of an app flow point at the app's host route.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_links
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.app_scope import links
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.support import approval_notifications as notif
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

A_FLOW, NATIVE_FLOW = "test-hw711-a", "test-hw711-native"
APPROVER = "hw711-approver@example.com"
RESOLVER = "huf.ai.flow.app_scope.tests.test_links.host_route"


def host_route(kind, flow_id, run_id=None):
	return f"/app/journey-builder/{flow_id}?{kind}={run_id}"


def raising_route(kind, flow_id, run_id=None):
	raise RuntimeError("boom")


def _hooks(path):
	real = frappe.get_hooks

	def fake(hook=None, *args, **kwargs):
		if hook == links.HOOK:
			return {"huf": path} if path else {}
		return real(hook, *args, **kwargs)

	return mock.patch.object(links.frappe, "get_hooks", side_effect=fake)


class TestHostLinks(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Agent Flow Run", {"flow_definition": ("in", (A_FLOW, NATIVE_FLOW))})
		frappe.db.delete("Flow Definition", {"name": ("in", (A_FLOW, NATIVE_FLOW))})
		defn = _graph([_trigger("end"), _end()])
		create_app_flow("huf", A_FLOW, "HW711 A", defn)
		frappe.get_doc(
			{"doctype": "Flow Definition", "flow_id": NATIVE_FLOW, "flow_name": "HW711 native",
			 "status": "Draft", "definition_json": frappe.as_json(defn)}
		).insert(ignore_permissions=True)  # fmt: skip
		if not frappe.db.exists("User", APPROVER):
			frappe.get_doc(
				{"doctype": "User", "email": APPROVER, "first_name": "Approver", "send_welcome_email": 0}
			).insert(ignore_permissions=True)

	def _notify(self, flow):
		run = frappe._dict(name=f"RUN-{flow}", flow_id=flow)
		waiting = {"approver_type": "user", "approver_users": [APPROVER], "flow_name": flow}
		with (
			mock.patch.object(notif, "enqueue_create_notification") as bell,
			mock.patch.object(notif, "is_email_notifications_enabled", return_value=True),
			mock.patch.object(notif.frappe, "sendmail") as mail,
		):
			notif._send_approval_notifications(run, {}, {}, waiting)
		return bell.call_args.args[1], mail.call_args.kwargs["message"]

	def test_app_flow_email_and_bell_use_host_route(self):
		with _hooks(RESOLVER):
			bell, message = self._notify(A_FLOW)
		route = host_route("approval", A_FLOW, f"RUN-{A_FLOW}")
		self.assertEqual(bell["link"], route)
		self.assertIn(route, message)
		self.assertNotIn("/huf", message)
		self.assertNotIn("/huf", bell["email_content"])

	def test_raising_resolver_falls_back_to_app(self):
		with _hooks("huf.ai.flow.app_scope.tests.test_links.raising_route"):
			bell, message = self._notify(A_FLOW)
		self.assertEqual(bell["link"], "/app")
		self.assertNotIn("/huf", message)

	def test_missing_resolver_falls_back_to_app(self):
		with _hooks(None):
			self.assertEqual(links.flow_link("run", A_FLOW, "R1"), "/app")

	def test_unsafe_resolver_output_falls_back(self):
		for bad in ("/huf/flows/x", "https://evil.example/x", "//evil.example", "/app/agent-flow-run/R1"):
			with _hooks(RESOLVER), mock.patch(f"{__name__}.host_route", return_value=bad):
				self.assertEqual(links.flow_link("run", A_FLOW, "R1"), "/app")

	def test_native_flow_keeps_huf_link(self):
		with _hooks(RESOLVER):
			bell, message = self._notify(NATIVE_FLOW)
		self.assertEqual(bell["link"], f"/huf/flows/{NATIVE_FLOW}?run=RUN-{NATIVE_FLOW}")
		self.assertIn(f"/huf/flows/{NATIVE_FLOW}", message)
