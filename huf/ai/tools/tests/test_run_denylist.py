"""Run, approval and channel records stay out of reach of generic agent tools.

A Guest-pinned tool runs with ``ignore_permissions`` (which the run write guard reads as server code) and
``attach_file_to_document`` writes with ``db.set_value`` (which never reaches a controller), so the tool doctype
denylist is the only thing between those paths and these records.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.handlers import crud
from huf.ai.tools import functions, frappe_generic
from huf.ai.tools.code_execution import _make_broker_handler
from huf.ai.tools.doctype_guard import _check_doctype_allowed

PROTECTED = (
	"Agent Flow Run",
	"Flow Member State",
	"Agent Execution Approval",
	"Channel Outbox",
	"Gateway Event",
)


class TestRunDenylist(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# db_insert: a bare row is enough, no flow definition or controller is involved
		run = frappe.get_doc({
			"doctype": "Agent Flow Run",
			"name": f"denylist-{frappe.generate_hash(length=10)}",
			"flow_id": "denylist",
			"status": "Queued",
			"trigger_type": "Manual",
			"started_at": now_datetime(),
		})
		run.db_insert()
		self.run_name = run.name

	def tearDown(self):
		frappe.db.rollback()

	def _status(self):
		return frappe.db.get_value("Agent Flow Run", self.run_name, "status")

	def assertRefused(self, result):
		self.assertIn("is not permitted through this tool", str(result))

	def test_guest_pinned_update_cannot_change_a_run(self):
		result = crud.handle_update_document(
			reference_doctype="Agent Flow Run",
			document_id=self.run_name,
			data={"status": "Success"},
			ignore_permissions=True,
		)
		self.assertRefused(result)
		self.assertEqual(self._status(), "Queued")

	def test_guest_pinned_set_value_and_delete_cannot_touch_a_run(self):
		self.assertRefused(crud.handle_set_value(
			doctype="Agent Flow Run", filters=self.run_name, fieldname="status", value="Success",
			ignore_permissions=True,
		))
		self.assertRefused(crud.handle_delete_document(
			reference_doctype="Agent Flow Run", document_id=self.run_name, ignore_permissions=True
		))
		self.assertEqual(self._status(), "Queued")

	def test_attach_file_cannot_set_a_run_field(self):
		url = frappe.get_doc({"doctype": "File", "file_name": "denylist.txt", "content": "x"}).insert().file_url
		result = crud.handle_attach_file_to_document(
			reference_doctype="Agent Flow Run", document_id=self.run_name, status=url
		)
		self.assertRefused(result)
		self.assertRefused(functions.attach_file_to_document("Agent Flow Run", self.run_name, status=url))
		self.assertEqual(self._status(), "Queued")

	def test_every_tool_write_handler_refuses_every_protected_doctype(self):
		for doctype in PROTECTED:
			pinned = {"reference_doctype": doctype, "ignore_permissions": True}
			calls = {
				"create": lambda: crud.handle_create_document(**pinned),
				"update": lambda: crud.handle_update_document(document_id="x", data={}, **pinned),
				"delete": lambda: crud.handle_delete_document(document_id="x", **pinned),
				"submit": lambda: crud.handle_submit_document(document_id="x", **pinned),
				"cancel": lambda: crud.handle_cancel_document(document_id="x", **pinned),
				"set_value": lambda: crud.handle_set_value(
					doctype=doctype, filters="x", fieldname="status", value="x", ignore_permissions=True
				),
				"create_many": lambda: crud.handle_create_documents(doctype, [{}]),
				"update_many": lambda: crud.handle_update_documents(doctype, [{"name": "x"}]),
				"delete_many": lambda: crud.handle_delete_documents(doctype, ["x"]),
				"attach": lambda: crud.handle_attach_file_to_document(doctype, "x", file_url="/files/x"),
				"fn_create": lambda: functions.create_document(doctype, {}),
				"fn_update": lambda: functions.update_document(doctype, "x", {}),
				"fn_delete": lambda: functions.delete_document(doctype, "x"),
				"fn_submit": lambda: functions.submit_document(doctype, "x"),
				"fn_cancel": lambda: functions.cancel_document(doctype, "x"),
				"fn_set_value": lambda: functions.set_value(doctype, "x", "status", "x"),
				"draft_create": lambda: frappe_generic.handle_create_record(doctype=doctype, values={}),
				"draft_update": lambda: frappe_generic.handle_update_record(doctype=doctype, name="x", values={}),
			}
			for label, call in calls.items():
				with self.subTest(doctype=doctype, path=label):
					self.assertRefused(call())

	def test_code_execution_broker_cannot_write_them(self):
		profile = {"permissions": [{"capability": "doc.create"}, {"capability": "doc.update"}]}
		broker = _make_broker_handler(profile, "Administrator")
		for doctype in PROTECTED:
			for capability in ("doc.create", "doc.update"):
				with self.subTest(doctype=doctype, capability=capability):
					ok, reason = broker(capability, {"doctype": doctype, "name": "x", "values": {}})
					self.assertFalse(ok)
					self.assertRefused(reason)

	def test_database_spelling_variants_are_refused(self):
		# the database collation ignores case, accents and trailing spaces
		for doctype in ("agent flow run", "Agent Flow Run ", "Agént Flow Run"):
			with self.subTest(doctype=doctype):
				meta, error = _check_doctype_allowed(doctype)
				self.assertIsNone(meta)
				self.assertTrue(error)
