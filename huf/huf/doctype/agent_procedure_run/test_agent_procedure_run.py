# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Bench-only integration tests for Agent Procedure Run (T-21).

Covers definition pinning (I6, GT-01), the distributed execution lock (GT-08), and the
Agent Tool Call telemetry linkage (I5).

Run with:
  bench --site <site> run-tests --app huf --module huf.huf.doctype.agent_procedure_run.test_agent_procedure_run
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import procedure_lock
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
			"input_schema": {"type": "object"},
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


class _FlagsSafeIntegrationTestCase(IntegrationTestCase):
	"""IntegrationTestCase that guarantees ``frappe.flags.currently_saving`` is a list.

	``frappe.model.document.set_user_and_timestamp`` appends to this flag unconditionally, but
	nothing initialises it outside a request lifecycle, so any ``insert()`` from a test errors with
	``AttributeError: 'NoneType' object has no attribute 'append'``. This is a pre-existing framework
	issue in this repo -- ``huf/ai/tests/test_code_execution_broker_permissions.py`` is quarantined
	for exactly this reason. Initialising the flag is preferable to quarantining the tests.
	"""

	def setUp(self):
		super().setUp()
		if getattr(frappe.flags, "currently_saving", None) is None:
			frappe.flags.currently_saving = []


class TestAgentProcedureRunPinning(_FlagsSafeIntegrationTestCase):
	def setUp(self):
		self._procedure_names = []
		self._run_names = []
		self.procedure_id = frappe.generate_hash(length=10)
		self.procedure = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "Pin Test",
				"status": "Active",
				"definition_json": frappe.as_json(_graph(tool_id="v1_tool")),
			}
		)
		self.procedure.insert(ignore_permissions=True)
		self._procedure_names.append(self.procedure.name)

	def tearDown(self):
		for name in self._run_names:
			try:
				frappe.delete_doc("Agent Procedure Run", name, force=1, ignore_permissions=True)
			except (frappe.DoesNotExistError, frappe.LinkExistsError, frappe.ValidationError) as exc:
				frappe.logger("huf").debug(f"test cleanup: failed to delete {name}: {exc!s}")
		for name in self._procedure_names:
			try:
				frappe.delete_doc("Agent Procedure", name, force=1, ignore_permissions=True)
			except (frappe.DoesNotExistError, frappe.LinkExistsError, frappe.ValidationError) as exc:
				frappe.logger("huf").debug(f"test cleanup: failed to delete {name}: {exc!s}")
		commit_if_background()

	def _insert_run(self):
		run = frappe.get_doc({"doctype": "Agent Procedure Run", "procedure": self.procedure.name})
		run.insert(ignore_permissions=True)
		self._run_names.append(run.name)
		return run

	def test_run_pins_definition_and_fingerprint_at_creation(self):
		run = self._insert_run()
		self.assertEqual(run.pinned_fingerprint, self.procedure.fingerprint)
		self.assertEqual(run.procedure_id, self.procedure_id)
		pinned = frappe.parse_json(run.pinned_definition_json)
		self.assertEqual(pinned["nodes"][0]["config"]["tool_id"], "v1_tool")

	def test_run_keeps_pinned_definition_after_procedure_moves_to_a_newer_version(self):
		"""GT-01's bug: a resumed run must never re-fetch the procedure's current
		version. Simulate a newer version existing and assert the run's own copy is
		untouched."""
		run = self._insert_run()

		newer = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "Pin Test",
				"status": "Active",
				"definition_json": frappe.as_json(_graph(tool_id="v2_tool")),
			}
		)
		newer.insert(ignore_permissions=True)
		self._procedure_names.append(newer.name)
		self.assertNotEqual(newer.fingerprint, run.pinned_fingerprint)

		run.reload()
		pinned = frappe.parse_json(run.pinned_definition_json)
		self.assertEqual(pinned["nodes"][0]["config"]["tool_id"], "v1_tool")
		self.assertEqual(run.pinned_fingerprint, self.procedure.fingerprint)

	def test_pinned_fields_cannot_be_changed_on_an_existing_run(self):
		run = self._insert_run()
		run.pinned_fingerprint = "0" * 64
		with self.assertRaises(frappe.ValidationError):
			run.save(ignore_permissions=True)

	def test_status_transition_to_running_stamps_started_at(self):
		run = self._insert_run()
		self.assertFalse(run.started_at)
		run.status = "Running"
		run.save(ignore_permissions=True)
		self.assertTrue(run.started_at)

	def test_status_transition_to_completed_stamps_completed_at(self):
		run = self._insert_run()
		run.status = "Completed"
		run.save(ignore_permissions=True)
		self.assertTrue(run.completed_at)


class TestAgentProcedureRunLock(_FlagsSafeIntegrationTestCase):
	"""Exercises the real frappe.cache()-backed lock (huf.ai.procedure_lock) against
	an actual run name -- huf.ai.tests.test_procedure_lock covers the pure logic with a
	fake cache; this proves the same module works against the real cache backend."""

	def setUp(self):
		self.run_name = f"__test_lock_run_{frappe.generate_hash(length=8)}__"

	def tearDown(self):
		procedure_lock.release_run_lock(self.run_name)

	def test_second_acquire_fails_while_first_holds_on_real_cache(self):
		self.assertTrue(procedure_lock.acquire_run_lock(self.run_name))
		self.assertFalse(procedure_lock.acquire_run_lock(self.run_name))
		procedure_lock.release_run_lock(self.run_name)
		self.assertTrue(procedure_lock.acquire_run_lock(self.run_name))


class TestAgentToolCallProcedureRunLinkage(_FlagsSafeIntegrationTestCase):
	"""I5: Agent Run -> Agent Procedure Run -> many Agent Tool Call must be queryable."""

	def setUp(self):
		self._names = {"Agent Procedure Run": [], "Agent Procedure": [], "Agent Tool Call": []}
		self.procedure_id = frappe.generate_hash(length=10)
		self.procedure = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "Telemetry Test",
				"definition_json": frappe.as_json(_graph()),
			}
		)
		self.procedure.insert(ignore_permissions=True)
		self._names["Agent Procedure"].append(self.procedure.name)

		self.run = frappe.get_doc({"doctype": "Agent Procedure Run", "procedure": self.procedure.name})
		self.run.insert(ignore_permissions=True)
		self._names["Agent Procedure Run"].append(self.run.name)

	def tearDown(self):
		for doctype, names in self._names.items():
			for name in names:
				try:
					frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
				except (frappe.DoesNotExistError, frappe.LinkExistsError, frappe.ValidationError) as exc:
					frappe.logger("huf").debug(f"test cleanup: failed to delete {name}: {exc!s}")
		commit_if_background()

	def test_agent_tool_call_can_link_to_procedure_run(self):
		call = frappe.get_doc(
			{
				"doctype": "Agent Tool Call",
				"tool": "get_thing",
				"agent_procedure_run": self.run.name,
				"status": "Completed",
			}
		)
		call.insert(ignore_permissions=True)
		self._names["Agent Tool Call"].append(call.name)

		linked = frappe.get_all(
			"Agent Tool Call", filters={"agent_procedure_run": self.run.name}, pluck="name"
		)
		self.assertIn(call.name, linked)


if __name__ == "__main__":
	import unittest

	unittest.main()
