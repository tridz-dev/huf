"""Frappe integration test: loose ``origin_type`` strings normalize before persistence.

Decision Call.origin_type (huf/huf/doctype/decision_call/decision_call.json) is a Select with
options exactly Playground/API/Agent/Flow/Automation/Hub/Gateway/Knowledge. Callers across the
codebase (agent runs, flow nodes, hub triage, knowledge ingestion, ...) construct DecisionOrigin
with looser strings such as "Agent Run" -- without normalization the Decision Call insert fails
outright and DecisionRuntime._emit swallows the sink failure by design, so the call is silently
never persisted. This exercises the full huf.ai.decision.service.run_policy path (using the
"fake" adapter, same fixture pattern as test_service.py) end to end through the real Frappe
telemetry sink to confirm the row lands with the normalized value.
"""

from __future__ import annotations

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import service
from huf.ai.decision.types import DecisionOrigin, DecisionStatus


class TestOriginTypePersistence(FrappeTestCase):
	def setUp(self):
		self._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

		self.suffix = uuid.uuid4().hex[:8]
		self.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": f"TestOriginProvider{self.suffix}",
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		self.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": f"test-origin-model-{self.suffix}",
			"provider": self.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		self.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": f"test_origin_class_{self.suffix}",
			"class_name": "Test Origin Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": f"test_origin_family_{self.suffix}",
			"family_name": "Test Origin Family",
			"adapter_id": "fake",
			"model_class": self.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": f"test-origin-model-key-{self.suffix}",
			"model_name": "Test Origin Model",
			"family": self.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.deployment = frappe.get_doc({
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-origin-{self.suffix}",
			"deployment_name": "Test Origin Deployment",
			"decision_model": self.decision_model.name,
			"ai_model": self.ai_model.name,
			"provider": self.provider.name,
			"provider_model_id": self.ai_model.name,
			"wire_protocol": "systemone",
			"priority": 100,
			"enabled": 1,
			"is_default_for_model": 1,
		}).insert(ignore_permissions=True)

		self.policy = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Test Origin Policy {self.suffix}",
			"purpose": "Tool Selection",
			"default_model": self.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(self._definition()),
		}).insert(ignore_permissions=True)
		self.published_version = self.policy.publish_version()

	def tearDown(self):
		# Same teardown ordering as test_service.py: Decision Call rows link to this test's
		# Decision Policy Version / Decision Deployment and must go first, and Decision Policy /
		# Decision Policy Version reference each other (current_version / policy) circularly.
		for call_name in frappe.get_all("Decision Call", filters={"decision_model": self.decision_model.name}, pluck="name"):
			frappe.delete_doc("Decision Call", call_name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.db.set_value("Decision Policy", self.policy.name, "current_version", None, update_modified=False)
		frappe.delete_doc("Decision Policy Version", self.published_version, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Policy", self.policy.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Deployment", self.deployment.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model", self.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", self.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", self.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", self.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", self.provider.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", self._prev_kill_switch)

	@staticmethod
	def _definition(policy_id: str = "test-origin-policy") -> dict:
		return {
			"policy_id": policy_id,
			"fallback_action": "fallback_default",
			"state_bindings": [{"name": "state", "path": "$"}],
			"questions": [
				{
					"id": "q1",
					"kind": "judge",
					"instructions": "Is this state acceptable?",
					"positive_criteria": "state looks fine",
				}
			],
		}

	def test_loose_origin_type_normalizes_and_persists(self):
		"""origin_type="Agent Run" (not a valid Select option) must still land as "Agent"."""
		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			surface="Tool Selection",
			origin=DecisionOrigin(origin_type="Agent Run"),
		)

		self.assertEqual(result.status, DecisionStatus.SUCCESS)
		self.assertIsNotNone(result.decision_call)
		call = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call.origin_type, "Agent")
