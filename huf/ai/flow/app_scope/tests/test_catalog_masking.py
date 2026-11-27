"""F2-catalog-masking: the "Use data" picker never hands an app editor raw run data (G4).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_catalog_masking
"""

import json

import frappe

from huf.ai.flow.app_scope.tests.test_app_read import EMAIL, FLOW_1, PHONE, USER, AppReadFixture
from huf.ai.flow.catalog import api as catalog_api
from huf.ai.flow.runs.shape import REDACTED

GRAPH = {
	"entry": "t",
	"nodes": [
		{"id": "t", "type": "trigger.webhook", "config": {}, "next": "fetch"},
		{"id": "fetch", "type": "tool.call", "config": {"tool_id": "http_request"}, "next": "mail"},
		{"id": "mail", "type": "tool.call", "config": {"tool_id": "gmail_send_email"}},
	],
}


class TestCatalogMasking(AppReadFixture):
	def setUp(self):
		super().setUp()
		frappe.db.set_value("Flow Definition", FLOW_1, "definition_json", json.dumps(GRAPH))
		frappe.db.delete("Agent Flow Run", {"flow_definition": FLOW_1})

	def _add_run(self, status="Success", tier="gold", waiting=None):
		payload = {"phone": PHONE, "email": EMAIL, "tier": tier}
		return (
			frappe.get_doc(
				{
					"doctype": "Agent Flow Run",
					"flow_definition": FLOW_1,
					"flow_id": FLOW_1,
					"status": status,
					"trigger_payload": json.dumps(payload),
					"context_json": json.dumps({"__node_outputs__": {"fetch": dict(payload)}}),
					"waiting": json.dumps(waiting) if waiting else None,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _catalog(self, user=USER):
		frappe.set_user(user)
		try:
			return catalog_api.get_data_catalog(FLOW_1, "mail")
		finally:
			frappe.set_user("Administrator")

	def _samples(self, out):
		steps = [out["trigger"], *out["steps"]]
		return {f["path"]: f.get("sample") for step in steps for f in step["fields"]}

	def test_app_editor_gets_masked_examples_and_a_privileged_user_raw_ones(self):
		name = self._add_run()
		out = self._catalog()
		text = json.dumps(out)
		self.assertNotIn(PHONE, text)
		self.assertNotIn(EMAIL, text)
		self.assertEqual(self._samples(out)["input.tier"], "gold")
		self.assertEqual(self._samples(out)["fetch.tier"], "gold")
		self.assertEqual(self._samples(self._catalog("Administrator"))["fetch.email"], EMAIL)
		self.assertIn(PHONE, frappe.db.get_value("Agent Flow Run", name, "trigger_payload"))

	def test_a_run_the_editor_may_not_read_is_skipped(self):
		self._add_run(tier="open")
		hidden = self._add_run(tier="hidden")
		self.assertEqual(self._samples(self._catalog())["input.tier"], "hidden")
		from unittest import mock

		with mock.patch.object(catalog_api, "can_access_run", side_effect=lambda name, ptype: name != hidden):
			self.assertEqual(self._samples(self._catalog())["input.tier"], "open")
		with mock.patch.object(catalog_api, "can_access_run", return_value=False):
			out = self._catalog()
		self.assertEqual((out["trigger"]["has_sample"], out["steps"][0]["has_sample"]), (False, False))

	def test_an_approval_the_editor_cannot_decide_is_redacted(self):
		self._add_run(
			status="Waiting Approval",
			waiting={"type": "approval", "node_id": "fetch", "approver_type": "role", "approver_role": "System Manager"},
		)
		samples = self._samples(self._catalog())
		self.assertEqual(samples["input.tier"], REDACTED)
		self.assertEqual(samples["fetch.tier"], REDACTED)
