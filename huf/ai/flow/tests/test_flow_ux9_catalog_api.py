# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-9 ``get_data_catalog``: steps before a step, their fields and real examples; editors only.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux9_catalog_api
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.flow import catalog_api
from huf.testing.factories import make_user

SECRET = "s" * 40


def _graph(sample=None):
	trigger = {"id": "t", "type": "trigger.webhook", "_label": "New order", "config": {"method": "POST", "secret": SECRET}, "next": "fetch"}
	if sample is not None:
		trigger["_sample"] = sample
	return {
		"entry": "t",
		"nodes": [
			trigger,
			{"id": "fetch", "type": "tool.call", "_label": "Look up customer", "config": {"tool_id": "http_request", "input": {}}, "next": "cond"},
			{"id": "cond", "type": "condition", "_label": "Big order?", "config": {"expression": "True", "on_true": "mail", "on_false": "end"}},
			{"id": "mail", "type": "tool.call", "_label": "Send email", "config": {"tool_id": "gmail_send_email", "input": {}}},
			{"id": "end", "type": "output", "config": {}},
		],
	}


class TestDataCatalogApi(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow_id = f"_test-ux9-{frappe.generate_hash(length=8)}"
		self.flow = self._flow(_graph({"customer": {"name": "Ada Lovelace"}, "total": 450}))

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _flow(self, graph):
		doc = frappe.get_doc(
			{"doctype": "Flow Definition", "flow_id": self.flow_id, "flow_name": "UX9 catalog", "status": "Draft", "definition_json": json.dumps(graph)}
		)
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", doc.name))
		return doc.name

	def _run(self, status="Success", payload=None, outputs=None):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run", "flow_definition": self.flow, "flow_id": self.flow_id, "status": status, "trigger_type": "Webhook",
				"started_at": now_datetime(), "trigger_payload": json.dumps(payload or {}),
				"context_json": json.dumps({**(payload or {}), "__node_outputs__": outputs or {}}),
			}
		)
		run.insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))
		return run.name

	def test_lists_the_trigger_first_and_only_steps_before_the_step(self):
		out = catalog_api.get_data_catalog(self.flow_id, "mail")
		self.assertEqual(out["trigger"]["title"], "New order")
		self.assertEqual([s["title"] for s in out["steps"]], ["Big order?", "Look up customer"])  # closest first
		self.assertNotIn("end", [s["id"] for s in out["steps"]])
		self.assertEqual(catalog_api.get_data_catalog(self.flow_id, "fetch")["steps"], [])

	def test_pinned_sample_gives_trigger_fields_with_examples(self):
		fields = {f["path"]: f for f in catalog_api.get_data_catalog(self.flow_id, "mail")["trigger"]["fields"]}
		self.assertEqual(fields["input.customer.name"]["sample"], "Ada Lovelace")
		self.assertEqual(fields["input.customer.name"]["label"], "Customer > Name")
		self.assertEqual(catalog_api.get_data_catalog(self.flow_id, "mail")["trigger"]["source"], "pinned")

	def test_step_examples_come_from_the_latest_successful_run(self):
		self._run("Failed", outputs={"fetch": {"status": "old"}})
		self._run("Success", payload={"total": 9}, outputs={"fetch": {"credit": {"limit": 5000}, "tier": "gold"}})
		step = {s["id"]: s for s in catalog_api.get_data_catalog(self.flow_id, "mail")["steps"]}["fetch"]
		paths = {f["path"]: f for f in step["fields"]}
		self.assertEqual(paths["fetch.tier"]["sample"], "gold")
		self.assertEqual(paths["fetch.credit.limit"]["label"], "Credit > Limit")
		self.assertEqual(step["source"], "last_run")
		self.assertTrue(step["has_sample"])

	def test_a_step_that_never_ran_says_so(self):
		step = {s["id"]: s for s in catalog_api.get_data_catalog(self.flow_id, "mail")["steps"]}["cond"]
		self.assertEqual((step["fields"], step["source"], step["has_sample"]), ([], "none", False))

	def test_trigger_falls_back_to_the_last_request_when_nothing_is_pinned(self):
		self.flow_id = f"_test-ux9-{frappe.generate_hash(length=8)}"
		self.flow = self._flow(_graph())
		out = catalog_api.get_data_catalog(self.flow_id, "mail")
		self.assertEqual((out["trigger"]["has_sample"], out["trigger"]["last_request_available"]), (False, False))
		self._run(payload={"email": "ada@example.com", "password": "hunter2", "_trigger": {"x": 1}})
		out = catalog_api.get_data_catalog(self.flow_id, "mail")
		fields = {f["path"]: f for f in out["trigger"]["fields"]}
		self.assertEqual(fields["input.email"]["sample"], "ada@example.com")
		self.assertEqual(fields["input.password"]["sample"], "(hidden)")
		self.assertNotIn("input._trigger", fields)
		self.assertTrue(out["trigger"]["last_request_available"])

	def test_a_loop_step_gets_the_fields_of_the_current_item(self):
		self.flow_id = f"_test-ux9-{frappe.generate_hash(length=8)}"
		graph = _graph({"items": [{"sku": "A-1", "qty": 2}]})
		graph["nodes"][1] = {"id": "fetch", "type": "foreach", "config": {"items": {"$from": "input.items"}, "body": ["mail"], "max_iterations": 5, "on_item_error": "fail", "collect": {"$from": "mail"}}, "next": "end"}
		graph["nodes"][2:3] = []
		self.flow = self._flow(graph)
		loop = catalog_api.get_data_catalog(self.flow_id, "mail")["loop"]
		self.assertEqual(loop["id"], "fetch")
		self.assertIn("foreach.item.sku", [f["path"] for f in loop["item_fields"]])

	def test_only_editors_get_samples(self):
		viewer = make_user(roles=["Huf Viewer"])
		self._docs.append(("User", viewer.name))
		frappe.set_user(viewer.name)
		with self.assertRaises(frappe.PermissionError):
			catalog_api.get_data_catalog(self.flow_id, "mail")

	def test_unknown_flow_is_a_plain_error(self):
		with self.assertRaises(frappe.DoesNotExistError):
			catalog_api.get_data_catalog("no-such-flow", "mail")


class TestDataTriggerCatalog(IntegrationTestCase):
	"""A data trigger knows its fields from the document type, including what a Link field points at."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = f"_test-ux9-{frappe.generate_hash(length=8)}"
		graph = {
			"entry": "t",
			"nodes": [
				{"id": "t", "type": "trigger.doc-event", "_label": "A to-do is added", "config": {"doctype": "ToDo", "event": "after_insert"}, "next": "mail"},
				{"id": "mail", "type": "tool.call", "config": {"tool_id": "gmail_send_email", "input": {}}},
			],
		}
		doc = frappe.get_doc({"doctype": "Flow Definition", "flow_id": self.flow_id, "flow_name": "UX9 data", "status": "Draft", "definition_json": json.dumps(graph)})
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		self.flow = doc.name
		self.todo = frappe.get_doc({"doctype": "ToDo", "description": "Call Ada", "allocated_to": "Administrator"}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.delete_doc("ToDo", self.todo.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Flow Definition", self.flow, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_fields_come_from_the_document_type_with_a_recent_record_as_the_example(self):
		trigger = catalog_api.get_data_catalog(self.flow_id, "mail")["trigger"]
		fields = {f["path"]: f for f in trigger["fields"]}
		self.assertEqual(fields["input.description"]["label"], "Description")
		self.assertIn("input.status", fields)
		self.assertTrue(trigger["has_sample"])
		self.assertEqual(trigger["doctype"], "ToDo")

	def test_a_link_field_offers_the_fields_of_what_it_points_at(self):
		trigger = catalog_api.get_data_catalog(self.flow_id, "mail")["trigger"]
		linked = [f for f in trigger["fields"] if f["path"].startswith("input._links.allocated_to.")]
		self.assertTrue(linked)
		self.assertTrue(all(f["label"].startswith("Allocated To > ") for f in linked))

	def test_the_run_payload_carries_what_the_catalog_promises(self):
		from huf.ai.flow import triggers

		payload = triggers.build_doc_event_payload(self.todo, "Administrator", "after_insert")
		row = payload["_links"]["allocated_to"]
		self.assertEqual(row.get("first_name") is not None or row.get("full_name") is not None, True)
		self.assertNotIn("password", json.dumps(row).lower())
		trigger = catalog_api.get_data_catalog(self.flow_id, "mail")["trigger"]
		for f in trigger["fields"]:
			if f["path"].startswith("input._links.allocated_to."):
				self.assertIn(f["path"].rsplit(".", 1)[1], row)
