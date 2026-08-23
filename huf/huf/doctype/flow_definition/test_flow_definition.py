"""Tests for Flow Definition's save-time "Create a Procedure from this Flow on save"
checkbox (huf.huf.doctype.flow_definition.flow_definition._maybe_convert_to_procedure).

Bench-context tests use `frappe.tests.UnitTestCase` because the behaviour under test is
Document.save()/on_update lifecycle wiring, which a frappe-free stub cannot exercise
meaningfully. Run:
  bench --site <site> run-tests --app huf --module huf.huf.doctype.flow_definition.test_flow_definition
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from huf.huf.doctype.flow_definition import flow_definition as fd_module

def _valid_definition(flow_id):
	"""A schema-valid, shared-IR-shape Flow definition (post gap2 migration:
	nodes carry their own ``next``, no top-level ``edges``, ``schema_version``
	is the string ``"1.0.0"``). ``flow_definition.py``'s own ``validate()`` now
	rejects anything else at save time, before the auto-convert checkbox logic
	ever runs -- these tests exercise the checkbox, not schema validation
	(see test_flow_definition_schema.py for that)."""
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"id": flow_id,
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": [
			{
				"id": "start",
				"type": "trigger.webhook",
				"config": {"method": "POST"},
				"next": "finish",
			},
			{
				"id": "finish",
				"type": "output",
				"config": {"value": {"$from": "start"}},
			},
		],
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": {"fail_closed": True},
		},
	}


def _ensure_saving_flag():
	if getattr(frappe.flags, "currently_saving", None) is None:
		frappe.flags.currently_saving = []


class TestFlowDefinitionAutoConvert(UnitTestCase):
	def setUp(self):
		self._names = []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		for name in self._names:
			try:
				frappe.delete_doc("Flow Definition", name, force=1, ignore_permissions=True)
			except Exception:  # noqa: BLE001 -- best-effort test cleanup
				pass

	def _make_flow(self, flow_id, definition=None, auto_convert=0):
		import json

		definition = dict(definition) if definition else _valid_definition(flow_id)
		definition["id"] = flow_id

		_ensure_saving_flag()
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": flow_id,
				"flow_name": flow_id,
				"definition_json": json.dumps(definition),
				"auto_convert_to_procedure": auto_convert,
			}
		)
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)
		return doc

	def test_checkbox_off_never_calls_conversion(self):
		with patch.object(fd_module, "commit_if_background"):
			with patch("huf.ai.flow_api.convert_flow_to_procedure") as mock_convert:
				self._make_flow("test-auto-convert-off", auto_convert=0)
				mock_convert.assert_not_called()

	def test_checkbox_on_non_convertible_flow_sets_note_and_does_not_throw(self):
		"""A schema-valid Flow (post gap2 migration, every Flow that saves is
		schema-valid) can still be non-deterministic -- e.g. it contains an
		agent.run/router.llm/human.approval node -- and convert_flow_to_procedure
		legitimately refuses on those grounds. The save itself must still succeed --
		the checkbox is a best-effort convenience, not a save-time gate.
		"""
		with patch.object(fd_module, "commit_if_background"):
			with patch("huf.ai.flow_api.convert_flow_to_procedure") as mock_convert:
				mock_convert.return_value = {
					"convertible": False,
					"reason": "Not convertible: contains an agent.run node.",
				}
				doc = self._make_flow("test-auto-convert-refused", auto_convert=1)
				doc.reload()
				self.assertIsNone(doc.converted_procedure)
				self.assertTrue(doc.conversion_note)
				self.assertIn("agent.run", doc.conversion_note)

	def test_checkbox_on_convertible_flow_records_procedure_and_note(self):
		with patch.object(fd_module, "commit_if_background"):
			with patch("huf.ai.flow_api.convert_flow_to_procedure") as mock_convert:
				mock_convert.return_value = {
					"convertible": True,
					"name": "demo-procedure-v1",
					"estimated_round_trip_reduction_pct": 63,
				}
				doc = self._make_flow("test-auto-convert-success", auto_convert=1)
				mock_convert.assert_called_once_with("test-auto-convert-success")
				# _maybe_convert_to_procedure writes via frappe.db.set_value, which bypasses
				# the in-memory doc's cached field values -- reload to see it.
				doc.reload()
				self.assertEqual(doc.get("converted_procedure"), "demo-procedure-v1")
				self.assertIn("demo-procedure-v1", doc.get("conversion_note"))
				self.assertIn("63%", doc.get("conversion_note"))

	def test_conversion_never_raises_out_of_save(self):
		"""A conversion-side exception must never fail the Flow's own save (I9-style: this
		convenience must never break the thing it is attached to)."""
		with patch.object(fd_module, "commit_if_background"):
			with patch("huf.ai.flow_api.convert_flow_to_procedure", side_effect=RuntimeError("boom")):
				doc = self._make_flow("test-auto-convert-exception", auto_convert=1)
				doc.reload()
				self.assertIn("Not converted", doc.get("conversion_note"))
				self.assertIn("boom", doc.get("conversion_note"))

	def test_system_flow_is_never_auto_converted(self):
		"""D12: a locked/system flow must not spawn procedures from a checkbox a
		non-admin could have ticked before the flow was locked."""
		with patch.object(fd_module, "commit_if_background"):
			with patch("huf.ai.flow_api.convert_flow_to_procedure") as mock_convert:
				mock_convert.return_value = {"convertible": False, "reason": "n/a"}
				# insert() itself fires on_update once, while is_system is still 0 --
				# that first call is expected and asserted on before flipping the flag.
				doc = self._make_flow("test-auto-convert-system", auto_convert=1)
				self.assertEqual(mock_convert.call_count, 1)

				frappe.db.set_value("Flow Definition", doc.name, "is_system", 1)
				doc.reload()
				doc._maybe_convert_to_procedure()
				# The is_system guard must have short-circuited this second call --
				# call_count stays at 1, not "never called at all".
				self.assertEqual(mock_convert.call_count, 1)
