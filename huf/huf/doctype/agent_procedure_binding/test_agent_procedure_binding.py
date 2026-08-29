# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Bench-only integration tests for Agent Procedure Binding (T-31).

Requires a real site (frappe.tests.IntegrationTestCase) -- exercises DB-level uniqueness
checks and Document.validate() through real inserts, which the frappe-free
huf.ai.tests.test_procedure_binding module (unit tests against the runtime exposure
logic) cannot.

Run with:
  bench --site <site> run-tests --app huf \
    --module huf.huf.doctype.agent_procedure_binding.test_agent_procedure_binding
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.transaction import commit_if_background


def _graph(tool_id="get_thing"):
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "n1",
		"nodes": [
			{"id": "n1", "type": "tool.call", "config": {"tool_id": tool_id}, "next": "n2"},
			{"id": "n2", "type": "output", "config": {"value": {"$from": "n1.result"}}},
		],
		"contract": {
			"input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": ["Thing"], "write": [], "http": "none", "code": "none"},
			"limits": {
				"max_nodes": 10,
				"max_rows": 100,
				"max_output_bytes": 10000,
				"max_parallel_calls": 1,
				"max_foreach_iterations": 1,
				"max_external_calls": 1,
				"max_writes": 0,
				"max_wall_time_ms": 5000,
				"fail_closed": True,
			},
		},
	}


def _ensure_saving_flag():
	"""See huf.huf.doctype.agent_procedure.test_agent_procedure._ensure_saving_flag --
	same underlying frappe.flags.currently_saving initialisation gap in this test runner.
	Must be its own statement immediately before insert(), never folded into a
	multi-line expression.
	"""
	if frappe.flags.currently_saving is None:
		frappe.flags.currently_saving = []


class TestAgentProcedureBinding(IntegrationTestCase):
	def setUp(self):
		self._procedure_names = []
		self._binding_names = []
		self._agent_names = []
		if getattr(frappe.flags, "currently_saving", None) is None:
			frappe.flags.currently_saving = []

	def tearDown(self):
		for doctype, names in (
			("Agent Procedure Binding", self._binding_names),
			("Agent Procedure", self._procedure_names),
			("Agent", self._agent_names),
		):
			for name in names:
				try:
					frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
				except (frappe.DoesNotExistError, frappe.LinkExistsError, frappe.ValidationError) as exc:
					frappe.logger("huf").debug(f"test cleanup: failed to delete {doctype} {name}: {exc!s}")
		commit_if_background()

	def _make_agent(self):
		_ensure_saving_flag()
		doc = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": frappe.generate_hash(length=10),
				"agent_modality": "Text",
				# Agent.validate requires instructions; without it every test here errors with
				# "Please provide an instruction for this AI Agent".
				"instructions": "Test agent for procedure binding.",
			}
		)
		doc.insert(ignore_permissions=True)
		self._agent_names.append(doc.name)
		return doc

	def _make_procedure(self, *, is_read_only_tool_id="get_thing", procedure_id=None):
		procedure_id = procedure_id or frappe.generate_hash(length=10)
		_ensure_saving_flag()
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": procedure_id,
				"procedure_name": "Test Procedure",
				"definition_json": frappe.as_json(_graph(tool_id=is_read_only_tool_id)),
			}
		)
		doc.insert(ignore_permissions=True)
		self._procedure_names.append(doc.name)
		return doc

	def _make_binding(self, agent, procedure, **kwargs):
		_ensure_saving_flag()
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure Binding",
				"agent": agent.name,
				"procedure": procedure.name,
				"enabled": 1,
				**kwargs,
			}
		)
		doc.insert(ignore_permissions=True)
		self._binding_names.append(doc.name)
		return doc

	def test_denormalizes_procedure_id_and_version(self):
		agent = self._make_agent()
		procedure = self._make_procedure()
		self.assertEqual(procedure.is_read_only, 1)  # sanity: fixture graph has no writes

		binding = self._make_binding(agent, procedure)

		self.assertEqual(binding.procedure_id, procedure.procedure_id)
		self.assertEqual(binding.version, procedure.version)

	def test_write_procedure_cannot_be_bound_enabled(self):
		"""I8: a Procedure whose graph performs writes must never be bindable/enabled."""
		agent = self._make_agent()
		procedure_id = frappe.generate_hash(length=10)
		graph = _graph()
		graph["contract"]["permission_envelope"]["write"] = ["Thing"]
		graph["nodes"][0]["config"] = {"tool_id": "create_thing"}

		_ensure_saving_flag()
		write_procedure = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": procedure_id,
				"procedure_name": "Write Procedure",
				"definition_json": frappe.as_json(graph),
			}
		)
		write_procedure.insert(ignore_permissions=True)
		self._procedure_names.append(write_procedure.name)
		self.assertEqual(write_procedure.is_read_only, 0)

		_ensure_saving_flag()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Agent Procedure Binding",
					"agent": agent.name,
					"procedure": write_procedure.name,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

	def test_second_enabled_binding_for_same_procedure_id_is_rejected(self):
		agent = self._make_agent()
		procedure_id = frappe.generate_hash(length=10)
		v1 = self._make_procedure(procedure_id=procedure_id, is_read_only_tool_id="get_thing")
		self._make_binding(agent, v1)

		v2_graph = _graph(tool_id="get_thing_v2")
		_ensure_saving_flag()
		v2 = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": procedure_id,
				"procedure_name": "Test Procedure",
				"definition_json": frappe.as_json(v2_graph),
			}
		)
		v2.insert(ignore_permissions=True)
		self._procedure_names.append(v2.name)

		_ensure_saving_flag()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Agent Procedure Binding",
					"agent": agent.name,
					"procedure": v2.name,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

	def test_per_agent_cap_is_enforced(self):
		agent = self._make_agent()

		original_conf = frappe.conf.get("agent_procedure_binding_max_per_agent")
		frappe.conf["agent_procedure_binding_max_per_agent"] = 2
		try:
			for i in range(2):
				procedure = self._make_procedure(is_read_only_tool_id=f"get_thing_{i}")
				self._make_binding(agent, procedure)

			procedure = self._make_procedure(is_read_only_tool_id="get_thing_overflow")
			with self.assertRaises(frappe.ValidationError):
				self._make_binding(agent, procedure)
		finally:
			if original_conf is None:
				frappe.conf.pop("agent_procedure_binding_max_per_agent", None)
			else:
				frappe.conf["agent_procedure_binding_max_per_agent"] = original_conf
