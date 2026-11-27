# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run records feed trusted decisions (recorded approvals, reply window, live/test mode), so only server code may
create or change them. Every case goes through the real generic document APIs as a Huf role.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_run_doc_write
"""

import json

import frappe
from frappe import client
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine
from huf.ai.flow.runs import actions
from huf.testing.factories import make_user

RUN = "Agent Flow Run"
STATE = "Flow Member State"
FORGED = {
	"context_json": json.dumps({"approve": {"decision": "approved"}}),
	"trigger_payload": json.dumps({"forged": 1}),
	"waiting": json.dumps({"type": "approval"}),
	"status": "Success",
	"member_key": "forged-member",
	"run_mode": "Live",
}


class TestRunDocWrite(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow = f"_test-docwrite-{frappe.generate_hash(length=6)}"
		defn = {"nodes": [{"id": "n1", "type": "trigger.manual", "config": {}}], "edges": []}
		flow = frappe.get_doc({"doctype": "Flow Definition", "flow_id": self.flow, "flow_name": "Doc write", "status": "Draft", "definition_json": json.dumps(defn)})
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", flow.name))
		self.run_name = self._insert({"doctype": RUN, "flow_definition": flow.name, "flow_id": flow.name, "status": "Queued", "trigger_type": "Manual"})
		self.state = self._insert({"doctype": STATE, "flow": flow.name, "member_key": "m1"})
		self.users = {role: self._user(role) for role in ("Huf User", "Huf Manager")}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete(RUN, {"flow_id": self.flow})
		frappe.db.delete(STATE, {"flow": self.flow})
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _insert(self, values):
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def _user(self, role):
		user = make_user(roles=[role])
		self._docs.append(("User", user.name))
		return user.name

	def _refused(self, call):
		for role, user in self.users.items():
			frappe.set_user(user)
			with self.subTest(role=role), self.assertRaises(frappe.PermissionError):
				call()
			frappe.set_user("Administrator")

	def _snapshot(self, doctype, name):
		return frappe.db.get_value(doctype, name, "*", as_dict=True)

	def test_set_value_cannot_change_a_run(self):
		before = self._snapshot(RUN, self.run_name)
		for field, value in FORGED.items():
			with self.subTest(field=field):
				self._refused(lambda: client.set_value(RUN, self.run_name, field, value))
		self.assertEqual(self._snapshot(RUN, self.run_name), before)

	def test_save_savedocs_and_bulk_update_cannot_change_a_run(self):
		before = self._snapshot(RUN, self.run_name)

		def forged():
			return {**frappe.get_doc(RUN, self.run_name).as_dict(), **FORGED}

		self._refused(lambda: client.save(frappe.as_json(forged())))
		self._refused(lambda: savedocs(frappe.as_json(forged()), "Save"))
		frappe.set_user(self.users["Huf User"])
		out = client.bulk_update(json.dumps([{"doctype": RUN, "docname": self.run_name, **FORGED}]))
		frappe.set_user("Administrator")
		self.assertEqual(len(out["failed_docs"]), 1)
		self.assertEqual(self._snapshot(RUN, self.run_name), before)

	def test_a_payload_cannot_claim_to_be_server_code(self):
		self._refused(lambda: client.set_value(RUN, self.run_name, {"flags": {"ignore_permissions": 1}, "status": "Success"}))

	def test_insert_cannot_create_a_run(self):
		values = {"doctype": RUN, "flow_definition": self.flow, "flow_id": self.flow, **FORGED}
		self._refused(lambda: client.insert(dict(values)))
		self.assertEqual(frappe.db.count(RUN, {"flow_id": self.flow}), 1)

	def test_rename_cannot_move_a_run(self):
		self._refused(lambda: client.rename_doc(RUN, self.run_name, f"forged-{frappe.generate_hash(length=6)}"))
		self.assertTrue(frappe.db.exists(RUN, self.run_name))

	def test_member_state_cannot_be_created_or_changed(self):
		before = self._snapshot(STATE, self.state)
		frappe.set_user(self.users["Huf Manager"])
		with self.assertRaises(frappe.PermissionError):
			client.set_value(STATE, self.state, "vars_json", json.dumps({"approved": True}))
		with self.assertRaises(frappe.PermissionError):
			client.insert({"doctype": STATE, "flow": self.flow, "member_key": "forged"})
		frappe.set_user("Administrator")
		self.assertEqual(self._snapshot(STATE, self.state), before)

	def test_engine_creates_a_run_for_a_user_without_ignore_permissions(self):
		frappe.set_user(self.users["Huf User"])
		run = engine.create_flow_run(flow_id=self.flow, payload={}, trigger_type="Manual", mode="test")
		self.assertTrue(frappe.db.exists(RUN, run.name))
		# the engine's allowance covers its own insert only, not later saves of the returned document
		run.flags.ignore_permissions = False
		run.status = "Success"
		with self.assertRaises(frappe.PermissionError):
			run.save()

	def test_reads_and_cancel_still_work(self):
		frappe.set_user(self.users["Huf Manager"])
		self.assertEqual(client.get_value(RUN, "status", {"name": self.run_name})["status"], "Queued")
		self.assertEqual(actions.cancel_flow_run(self.run_name)["status"], "Cancelled")
