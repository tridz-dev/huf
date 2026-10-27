"""Activation-time validation for Flow Definition.

Pure-rule tests (no DB) over activation_rules.collect_activation_problems, plus a
DB-level test that Draft saves stay permissive while Active is refused.

  bench --site <site> run-tests --app huf --module huf.huf.doctype.flow_definition.test_flow_activation
"""

import copy
import json
import unittest

import frappe
from frappe.tests import UnitTestCase

from huf.huf.doctype.flow_definition.activation_rules import collect_activation_problems, entry_is_unset
from huf.huf.doctype.flow_definition.test_flow_definition import _valid_definition


def _good():
	return _valid_definition("x")


def _problems(defn):
	return collect_activation_problems(defn)


class TestActivationRules(unittest.TestCase):
	def test_valid_flow_has_no_problems(self):
		self.assertEqual(_problems(_good()), [])

	def test_no_trigger_node(self):
		d = _good()
		d["nodes"] = [{"id": "finish", "type": "output", "config": {"value": 1}}]
		d["entry"] = "finish"
		self.assertTrue(any("no trigger node" in p for p in _problems(d)))

	def test_trigger_unset(self):
		d = _good()
		d["nodes"][0] = {"id": "start", "type": "trigger.unset", "config": {}, "next": "finish"}
		probs = _problems(d)
		self.assertTrue(any("unset" in p for p in probs))
		self.assertFalse(any("no trigger node" in p for p in probs))
		self.assertTrue(entry_is_unset(d))
		self.assertFalse(entry_is_unset(_good()))

	def test_empty_required_config(self):
		d = _good()
		d["nodes"][0]["config"] = {"method": "  "}
		self.assertTrue(any("'method' is empty" in p for p in _problems(d)))

	def test_edge_to_nonexistent_node(self):
		d = _good()
		d["nodes"][0]["next"] = "ghost"
		self.assertTrue(any("nonexistent node 'ghost'" in p for p in _problems(d)))

	def test_orphan_node(self):
		d = _good()
		d["nodes"].append({"id": "lonely", "type": "output", "config": {"value": 1}})
		self.assertTrue(any("'lonely' is an orphan" in p for p in _problems(d)))

	def test_reports_all_problems_in_one_pass(self):
		d = copy.deepcopy(_good())
		d["nodes"][0] = {"id": "start", "type": "trigger.webhook", "config": {"method": ""}, "next": "ghost"}
		d["nodes"].append({"id": "lonely", "type": "output", "config": {"value": 1}})
		probs = _problems(d)
		self.assertGreaterEqual(len(probs), 3)


class TestFlowActivationGate(UnitTestCase):
	def setUp(self):
		self._names = []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		for name in self._names:
			try:
				frappe.delete_doc("Flow Definition", name, force=1, ignore_permissions=True)
			except Exception:  # noqa: BLE001 -- best-effort cleanup
				frappe.log_error(f"flow activation test cleanup failed: {name}")

	def _make(self, flow_id, definition, status):
		if getattr(frappe.flags, "currently_saving", None) is None:
			frappe.flags.currently_saving = []
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": flow_id,
				"flow_name": flow_id,
				"status": status,
				"definition_json": json.dumps(definition),
			}
		)
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)
		return doc

	def _unset_flow(self):
		d = _good()
		d["nodes"][0] = {"id": "start", "type": "trigger.unset", "config": {}, "next": "finish"}
		return d

	def test_draft_with_unset_trigger_saves(self):
		doc = self._make("act-draft-unset", self._unset_flow(), "Draft")
		self.assertEqual(doc.status, "Draft")

	def test_activating_unset_flow_is_refused_with_all_problems(self):
		d = self._unset_flow()
		d["nodes"][1]["config"] = {"value": 1}
		doc = self._make("act-draft-then-active", d, "Draft")
		doc.status = "Active"
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.save(ignore_permissions=True)
		self.assertIn("unset", str(ctx.exception))

	def test_insert_active_with_bad_flow_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._make("act-insert-active", self._unset_flow(), "Active")

	def test_valid_flow_can_be_active(self):
		doc = self._make("act-valid-active", _good(), "Active")
		self.assertEqual(doc.status, "Active")
