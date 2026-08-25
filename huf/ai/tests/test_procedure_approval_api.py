# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Bench-only integration tests for huf.ai.procedure_approval_api.

Covers the manual-approval gate for write Agent Procedures (I8):
- request_procedure_approval(): any user with Agent Procedure read access can request
  review; read-only Procedures are rejected (nothing to approve); already-Approved is a
  clean no-op.
- approve_procedure(): manager-only (System Manager / Huf Manager); non-managers are
  rejected with frappe.PermissionError; re-approving an already-Approved Procedure is a
  clean no-op, not an error; read-only Procedures are rejected.
- Agent Procedure Binding: a write Procedure only binds/enables once approval_status ==
  "Approved"; the pre-existing read-only-only path is unaffected.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_approval_api
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import procedure_approval_api
from huf.ai.transaction import commit_if_background

NON_MANAGER_ROLES = ["Huf User"]
MANAGER_ROLES = ["Huf User", "Huf Manager"]


def _graph(tool_id="get_thing", write=False):
	graph = {
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
			"permission_envelope": {
				"read": ["Thing"],
				"write": ["Thing"] if write else [],
				"http": "none",
				"code": "none",
			},
			"limits": {
				"max_nodes": 10,
				"max_rows": 100,
				"max_output_bytes": 10000,
				"max_parallel_calls": 1,
				"max_foreach_iterations": 1,
				"max_external_calls": 1,
				"max_writes": 1 if write else 0,
				"max_wall_time_ms": 5000,
				"fail_closed": True,
			},
		},
	}
	return graph


def _ensure_saving_flag():
	if frappe.flags.currently_saving is None:
		frappe.flags.currently_saving = []


class TestProcedureApprovalApi(IntegrationTestCase):
	def setUp(self):
		self._procedure_names = []
		self._agent_names = []
		self._binding_names = []
		_ensure_saving_flag()

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

	def _make_procedure(self, *, write=True, tool_id=None, procedure_id=None):
		procedure_id = procedure_id or frappe.generate_hash(length=10)
		tool_id = tool_id or ("create_thing" if write else "get_thing")
		_ensure_saving_flag()
		doc = frappe.get_doc(
			{
				"doctype": "Agent Procedure",
				"procedure_id": procedure_id,
				"procedure_name": "Test Procedure",
				"definition_json": frappe.as_json(_graph(tool_id=tool_id, write=write)),
			}
		)
		doc.insert(ignore_permissions=True)
		self._procedure_names.append(doc.name)
		return doc

	def _make_agent(self):
		_ensure_saving_flag()
		doc = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": frappe.generate_hash(length=10),
				"agent_modality": "Text",
				"instructions": "Test agent for procedure approval.",
			}
		)
		doc.insert(ignore_permissions=True)
		self._agent_names.append(doc.name)
		return doc

	# -- request_procedure_approval ---------------------------------------------------

	def test_request_approval_sets_pending_review(self):
		procedure = self._make_procedure(write=True)
		self.assertEqual(procedure.approval_status, "Not Requested")

		with patch("frappe.has_permission", return_value=True):
			result = procedure_approval_api.request_procedure_approval(procedure.name)

		self.assertEqual(result["approval_status"], "Pending Review")
		self.assertTrue(result["changed"])
		self.assertEqual(
			frappe.db.get_value("Agent Procedure", procedure.name, "approval_status"),
			"Pending Review",
		)

	def test_request_approval_rejects_read_only_procedure(self):
		procedure = self._make_procedure(write=False)

		with patch("frappe.has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				procedure_approval_api.request_procedure_approval(procedure.name)

	def test_request_approval_on_already_approved_is_noop(self):
		procedure = self._make_procedure(write=True)
		with patch("frappe.has_permission", return_value=True), patch(
			"frappe.get_roles", return_value=MANAGER_ROLES
		):
			procedure_approval_api.request_procedure_approval(procedure.name)
			procedure_approval_api.approve_procedure(procedure.name, approve=True)

		with patch("frappe.has_permission", return_value=True):
			result = procedure_approval_api.request_procedure_approval(procedure.name)

		self.assertEqual(result["approval_status"], "Approved")
		self.assertFalse(result["changed"])

	# -- approve_procedure --------------------------------------------------------------

	def test_non_manager_cannot_approve(self):
		procedure = self._make_procedure(write=True)
		with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
			self.assertRaises(
				frappe.PermissionError,
				procedure_approval_api.approve_procedure,
				procedure.name,
				True,
			)

	def test_manager_can_approve_and_stamps_reviewer(self):
		procedure = self._make_procedure(write=True)
		with patch("frappe.get_roles", return_value=MANAGER_ROLES):
			result = procedure_approval_api.approve_procedure(procedure.name, approve=True, note="looks good")

		self.assertEqual(result["approval_status"], "Approved")
		self.assertTrue(result["changed"])
		self.assertEqual(result["approved_by"], frappe.session.user)

		doc = frappe.get_doc("Agent Procedure", procedure.name)
		self.assertEqual(doc.approval_status, "Approved")
		self.assertEqual(doc.approved_by, frappe.session.user)
		self.assertTrue(doc.approved_at)
		self.assertEqual(doc.approval_note, "looks good")

	def test_manager_can_reject(self):
		procedure = self._make_procedure(write=True)
		with patch("frappe.get_roles", return_value=MANAGER_ROLES):
			result = procedure_approval_api.approve_procedure(procedure.name, approve=False, note="not ready")

		self.assertEqual(result["approval_status"], "Rejected")
		doc = frappe.get_doc("Agent Procedure", procedure.name)
		self.assertEqual(doc.approval_status, "Rejected")

	def test_reapproving_already_approved_is_noop(self):
		procedure = self._make_procedure(write=True)
		with patch("frappe.get_roles", return_value=MANAGER_ROLES):
			first = procedure_approval_api.approve_procedure(procedure.name, approve=True)
			self.assertTrue(first["changed"])

			second = procedure_approval_api.approve_procedure(procedure.name, approve=True)

		self.assertEqual(second["approval_status"], "Approved")
		self.assertFalse(second["changed"])

	def test_approve_rejects_read_only_procedure(self):
		procedure = self._make_procedure(write=False)
		with patch("frappe.get_roles", return_value=MANAGER_ROLES):
			with self.assertRaises(frappe.ValidationError):
				procedure_approval_api.approve_procedure(procedure.name, approve=True)

	# -- binding interaction -------------------------------------------------------------

	def test_unapproved_write_procedure_cannot_be_bound(self):
		agent = self._make_agent()
		procedure = self._make_procedure(write=True)

		_ensure_saving_flag()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Agent Procedure Binding",
					"agent": agent.name,
					"procedure": procedure.name,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

	def test_approved_write_procedure_can_be_bound(self):
		agent = self._make_agent()
		procedure = self._make_procedure(write=True)

		with patch("frappe.get_roles", return_value=MANAGER_ROLES):
			procedure_approval_api.approve_procedure(procedure.name, approve=True)

		_ensure_saving_flag()
		binding = frappe.get_doc(
			{
				"doctype": "Agent Procedure Binding",
				"agent": agent.name,
				"procedure": procedure.name,
				"enabled": 1,
			}
		)
		binding.insert(ignore_permissions=True)
		self._binding_names.append(binding.name)

		self.assertEqual(binding.procedure_id, procedure.procedure_id)

	def test_rejected_write_procedure_still_cannot_be_bound(self):
		agent = self._make_agent()
		procedure = self._make_procedure(write=True)

		with patch("frappe.get_roles", return_value=MANAGER_ROLES):
			procedure_approval_api.approve_procedure(procedure.name, approve=False)

		_ensure_saving_flag()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Agent Procedure Binding",
					"agent": agent.name,
					"procedure": procedure.name,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
