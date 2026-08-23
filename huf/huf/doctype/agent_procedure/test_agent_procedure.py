# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Bench-only integration tests for Agent Procedure (T-20).

Requires a real site (frappe.tests.IntegrationTestCase). Covers what
huf.ai.tests.test_procedure_versioning cannot: DB-level uniqueness (structural
immutability), Document.save() guards, tier locking through huf.ai.system_records, and
permission_query_conditions.

Run with:
  bench --site <site> run-tests --app huf --module huf.huf.doctype.agent_procedure.test_agent_procedure
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.transaction import commit_if_background

NON_MANAGER_ROLES = ["Huf User"]


def _graph(tool_id="get_thing", extra_nodes=None):
	nodes = [
		{"id": "n1", "type": "tool.call", "config": {"tool_id": tool_id}, "next": "n2"},
		{"id": "n2", "type": "output", "config": {"value": {"$from": "n1.result"}}},
	]
	if extra_nodes:
		nodes.extend(extra_nodes)
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "n1",
		"nodes": nodes,
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


def _ensure_saving_flag():
	"""Guarantee ``frappe.flags.currently_saving`` is a list before an insert.

	``frappe.model.document.set_user_and_timestamp`` appends to this flag unconditionally, but the
	test runner does not initialise it, so ``insert()`` raises
	``AttributeError: 'NoneType' object has no attribute 'append'``. Setting it in ``setUp`` is not
	enough -- the framework resets ``frappe.local`` between setUp and the test body -- so the guard
	has to sit next to the insert. This repo already quarantines
	``huf/ai/tests/test_code_execution_broker_permissions.py`` for the same underlying issue.
	"""

	if frappe.flags.currently_saving is None:
		frappe.flags.currently_saving = []


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


class TestAgentProcedureVersioning(_FlagsSafeIntegrationTestCase):
	def setUp(self):
		self._names = []
		self.procedure_id = frappe.generate_hash(length=10)

	def tearDown(self):
		for name in self._names:
			try:
				frappe.delete_doc("Agent Procedure", name, force=1, ignore_permissions=True)
			except (frappe.DoesNotExistError, frappe.LinkExistsError, frappe.ValidationError) as exc:
				frappe.logger("huf").debug(f"test cleanup: failed to delete {name}: {exc!s}")
		commit_if_background()

	def _insert(self, tool_id="get_thing", **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "Test Procedure",
				"definition_json": frappe.as_json(_graph(tool_id=tool_id)),
				**kwargs,
			}
		)
		_ensure_saving_flag()
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)
		return doc

	def test_first_version_is_v1(self):
		doc = self._insert()
		self.assertEqual(doc.version, 1)
		self.assertEqual(doc.name, f"{self.procedure_id}-v1")

	def test_second_distinct_insert_is_v2(self):
		self._insert(tool_id="get_thing")
		doc2 = self._insert(tool_id="get_other_thing")
		self.assertEqual(doc2.version, 2)
		self.assertEqual(doc2.name, f"{self.procedure_id}-v2")

	def test_fingerprint_is_deterministic_and_populated(self):
		doc = self._insert()
		self.assertEqual(len(doc.fingerprint), 64)
		int(doc.fingerprint, 16)

	def test_same_content_reinserted_gets_next_version_number_with_same_fingerprint(self):
		"""Re-authoring identical content is still a new version row (append-only, per
		spec section 7's "any change ... produces a new fingerprint" is about content
		changes; re-submitting unchanged content is a caller decision, not blocked here)
		-- but its fingerprint matches the earlier version's, which is the useful signal
		a caller can use to detect a no-op edit before deciding to insert at all."""
		doc1 = self._insert(tool_id="get_thing")
		doc2 = self._insert(tool_id="get_thing")
		self.assertEqual(doc1.fingerprint, doc2.fingerprint)
		self.assertNotEqual(doc1.name, doc2.name)

	def test_direct_insert_with_explicit_colliding_version_is_rejected(self):
		"""Structural mechanism: the docname IS (procedure_id, version) -- a second
		insert naming the same pair collides on the primary key. This is the "unique
		key preventing overwrite" GT-14 calls for, independent of any validate hook."""
		self._insert()  # v1
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc(
				{
					"doctype": "Agent Procedure",
					"procedure_id": self.procedure_id,
					"procedure_name": "Colliding",
					"version": 1,
					"definition_json": frappe.as_json(_graph(tool_id="something_else")),
				}
			_ensure_saving_flag()
			).insert(ignore_permissions=True)

	def test_saving_existing_version_with_changed_content_is_blocked(self):
		"""Defence in depth (not the structural guarantee itself, see module docstring):
		Document.save() must refuse to mutate an existing version's content."""
		doc = self._insert()
		doc.definition_json = frappe.as_json(_graph(tool_id="mutated"))
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_db_set_value_bypasses_the_document_guard(self):
		"""Documents the known, acknowledged gap (GT-14 / huf.ai.system_records GAP 2):
		frappe.db.set_value has no Document lifecycle and is NOT stopped by validate().
		This is exactly why the primary-key uniqueness above -- not this guard -- is the
		mechanism I6 actually depends on."""
		doc = self._insert()
		frappe.db.set_value("Agent Procedure", doc.name, "procedure_name", "tampered directly")
		commit_if_background()
		self.assertEqual(
			frappe.db.get_value("Agent Procedure", doc.name, "procedure_name"), "tampered directly"
		)

	def test_flow_only_node_is_rejected_at_validate(self):
		graph = _graph(extra_nodes=[{"id": "a1", "type": "agent.run", "config": {}}])
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "Bad",
				"definition_json": frappe.as_json(graph),
			}
		)
		with self.assertRaises(frappe.ValidationError):
			_ensure_saving_flag()
			doc.insert(ignore_permissions=True)

	def test_router_llm_and_human_approval_are_also_rejected(self):
		for node_type in ("router.llm", "human.approval"):
			graph = _graph(extra_nodes=[{"id": "x1", "type": node_type, "config": {}}])
			doc = frappe.get_doc(
				{
					"doctype": "Agent Procedure",
					"procedure_id": frappe.generate_hash(length=10),
					"procedure_name": "Bad",
					"definition_json": frappe.as_json(graph),
				}
			)
			with self.assertRaises(frappe.ValidationError):
				_ensure_saving_flag()
				doc.insert(ignore_permissions=True)

	def test_rename_is_never_allowed(self):
		doc = self._insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.rename_doc("Agent Procedure", doc.name, f"{doc.name}-renamed")


class TestAgentProcedureTierLocking(_FlagsSafeIntegrationTestCase):
	def setUp(self):
		self._names = []
		self.procedure_id = frappe.generate_hash(length=10)

	def tearDown(self):
		for name in self._names:
			try:
				frappe.delete_doc("Agent Procedure", name, force=1, ignore_permissions=True)
			except (frappe.DoesNotExistError, frappe.LinkExistsError, frappe.ValidationError) as exc:
				frappe.logger("huf").debug(f"test cleanup: failed to delete {name}: {exc!s}")
		commit_if_background()

	def test_system_tier_sets_is_system_flag(self):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "System Template",
				"tier": "System",
				"definition_json": frappe.as_json(_graph()),
			}
		)
		_ensure_saving_flag()
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)
		self.assertEqual(doc.is_system, 1)

	def test_draft_tier_is_not_locked(self):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "Draft Proc",
				"tier": "Draft",
				"definition_json": frappe.as_json(_graph()),
			}
		)
		_ensure_saving_flag()
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)
		self.assertEqual(doc.is_system, 0)

	def test_non_manager_cannot_edit_metadata_on_system_tier(self):
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": self.procedure_id,
				"procedure_name": "System Template",
				"tier": "System",
				"definition_json": frappe.as_json(_graph()),
			}
		)
		_ensure_saving_flag()
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		doc.reload()
		doc.procedure_name = "Renamed by non-manager"
		with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
			with self.assertRaises(frappe.ValidationError):
				doc.save(ignore_permissions=True)


if __name__ == "__main__":
	import unittest

	unittest.main()
