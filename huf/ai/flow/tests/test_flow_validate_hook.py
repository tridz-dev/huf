# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""H-W2-10: the ``huf_flow_validators`` hook lets an installed app refuse steps, fail-closed, in every mode.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_validate_hook
"""

import json
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow
from huf.ai.graph.validation.flow_validation import VALIDATOR_HOOK, validate_flow

HERE = "huf.ai.flow.tests.test_flow_validate_hook"
REFUSAL = "Steps of this kind are not allowed here."


def reject_condition(graph):
	"""Stands in for an app's node policy: the ``condition`` kind is refused."""
	return [
		{"code": "KIND_REFUSED", "node_id": n["id"], "field": "type", "message": REFUSAL}
		for n in graph["nodes"]
		if n["type"] == "condition"
	]


def allow(graph):
	return []


def crash(graph):
	raise RuntimeError("person@example.com")


def returns_nothing(graph):
	return None


def returns_junk(graph):
	return [{"code": "NO_MESSAGE"}]


def mutates(graph):
	graph["nodes"].clear()
	return []


@contextmanager
def validators(*names):
	real = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		if hook == VALIDATOR_HOOK:
			return [n if "." in n else f"{HERE}.{n}" for n in names]
		return real(hook, *args, **kwargs)

	with patch.object(frappe, "get_hooks", get_hooks):
		yield


class TestValidatorHook(IntegrationTestCase):
	def test_refusal_fails_both_modes_with_the_apps_sentence(self):
		g = finished_flow()
		with validators("reject_condition"):
			for mode in ("draft", "publish"):
				result = validate_flow(g, mode)
				self.assertFalse(result.ok, mode)
				self.assertFalse(result.finished)
				self.assertEqual([(e.code, e.node_id) for e in result.errors], [("KIND_REFUSED", "cond")])
				self.assertEqual(result.messages(g), [REFUSAL])
				self.assertEqual(result.to_dict(g)["errors"][0]["message"], REFUSAL)

	def test_no_hook_or_no_objection_passes(self):
		for names in ((), ("allow",)):
			with validators(*names):
				self.assertTrue(validate_flow(finished_flow(), "publish").ok, names)

	def test_broken_hooks_fail_closed(self):
		for name in ("crash", "returns_nothing", "returns_junk", "no_such_function", "no_such_app.check"):
			with validators("allow", name):
				for mode in ("draft", "publish"):
					result = validate_flow(finished_flow(), mode)
					self.assertFalse(result.ok, (name, mode))
					self.assertEqual({e.code for e in result.errors}, {"APP_VALIDATOR_FAILED"}, name)
					self.assertNotIn("person@example.com", json.dumps(result.to_dict()))

	def test_a_hook_cannot_change_the_definition(self):
		g = finished_flow()
		with validators("mutates", "reject_condition"):
			result = validate_flow(g, "publish")
		self.assertEqual(g, finished_flow())
		self.assertEqual([e.code for e in result.errors], ["KIND_REFUSED"])


class TestValidatorHookOnBench(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = f"_test-validator-{frappe.generate_hash(length=8)}"

	def tearDown(self):
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		if frappe.db.exists("Flow Definition", self.flow_id):
			frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_refused_kind_cannot_be_saved(self):
		with validators("reject_condition"), self.assertRaises(frappe.ValidationError):
			flow_api.save_flow_definition(self.flow_id, finished_flow())
		self.assertFalse(frappe.db.exists("Flow Definition", self.flow_id))

	def test_flow_stored_before_the_policy_cannot_be_published_or_started(self):
		flow_api.save_flow_definition(self.flow_id, finished_flow())
		with validators("reject_condition"):
			with self.assertRaises(frappe.ValidationError):
				flow_api.publish_flow(self.flow_id)
			self.assertEqual(frappe.db.get_value("Flow Definition", self.flow_id, "status"), "Draft")
			with self.assertRaises(frappe.ValidationError):
				flow_engine.create_flow_run(self.flow_id, payload={"n": 2}, trigger_type="Webhook")
		self.assertFalse(frappe.db.exists("Agent Flow Run", {"flow_id": self.flow_id}))
