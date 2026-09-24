# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Integration tests for the router.decision Flow node end to end (T3.02, PLAN.md §3.11
point 4, D10): ``huf.ai.flow_engine._build_run_context`` injecting
``huf.ai.decision.flow_adapter.make_flow_decision_router`` into the run context,
``_exec_router_decision`` using it to route a real Flow Run, and the site kill switch
(``Agent Settings.decision_runtime_enabled``) turning that behaviour off cleanly.

T3.01's own unit tests (``huf/ai/decision/tests/test_flow_adapter.py``,
``huf/ai/decision/tests/test_flow_router.py``) already cover the adapter and the routing
contract Frappe-free with a fake ``flow_run``/mocked ``service.run_policy``. This module is
the thing those tests cannot reach: a real ``Flow Definition`` saved through
``flow_api.save_flow_definition`` (schema-valid graph-IR), a real ``Flow Run`` advanced
through ``flow_engine.run_flow`` / ``resume_flow_run`` / ``approve_flow_run``, and a real,
published ``Decision Policy`` for the D10 version-pinning assertions. ``service.run_policy``
itself is monkeypatched (same target ``huf.ai.decision.flow_adapter.service.run_policy`` the
T3.01 unit tests patch) so these tests do not depend on a live Decision backend -- only the
Flow <-> Decision Runtime wiring is under test here.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_flow_router_decision
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import flow_api
from huf.ai.decision.types import DecisionAnswer, DecisionResponse, DecisionStatus, QuestionKind, ServiceResult


def _limits() -> dict:
	return {
		"max_nodes": 20,
		"max_rows": 1000,
		"max_output_bytes": 100_000,
		"max_parallel_calls": 1,
		"max_foreach_iterations": 1,
		"max_external_calls": 5,
		"max_writes": 0,
		"max_wall_time_ms": 5000,
		"fail_closed": True,
	}


def _contract() -> dict:
	return {
		"input_schema": {"type": "object"},
		"output_schema": {"type": "object"},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
		"limits": _limits(),
	}


def _make_response(value: str, confidence: float = 0.9, status: DecisionStatus = DecisionStatus.SUCCESS) -> DecisionResponse:
	return DecisionResponse(
		status=status,
		answers={"route": DecisionAnswer("route", QuestionKind.SELECT, value, confidence=confidence)} if status == DecisionStatus.SUCCESS else {},
	)


class RouterDecisionFlowTestBase(IntegrationTestCase):
	"""Shared fixture: a real, published Decision Policy plus small bookkeeping for cleanup."""

	def setUp(self):
		frappe.set_user("Administrator")
		self._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)
		self._names: dict[str, list[str]] = {}

		self.suffix = uuid.uuid4().hex[:8]
		self.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": f"TestFlowDRProvider{self.suffix}",
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		self.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": f"test-flow-dr-model-{self.suffix}",
			"provider": self.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		self.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": f"test_flow_dr_class_{self.suffix}",
			"class_name": "Test Flow DR Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": f"test_flow_dr_family_{self.suffix}",
			"family_name": "Test Flow DR Family",
			"adapter_id": "fake",
			"model_class": self.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": f"test-flow-dr-model-key-{self.suffix}",
			"model_name": "Test Flow DR Model",
			"family": self.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.deployment = frappe.get_doc({
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-flow-dr-{self.suffix}",
			"deployment_name": "Test Flow DR Deployment",
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
			"policy_name": f"Test Flow DR Policy {self.suffix}",
			"purpose": "Flow Routing",
			"default_model": self.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(self._policy_definition()),
		}).insert(ignore_permissions=True)
		self.published_version = self.policy.publish_version()
		self.policy.reload()

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Flow Run", "Flow Definition"):
			for name in self._names.get(doctype, []):
				try:
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
				except Exception:  # noqa: BLE001 -- best-effort test cleanup
					pass
		for call_name in frappe.get_all("Decision Call", filters={"decision_model": self.decision_model.name}, pluck="name"):
			frappe.delete_doc("Decision Call", call_name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.db.set_value("Decision Policy", self.policy.name, "current_version", None, update_modified=False)
		for version_name in frappe.get_all("Decision Policy Version", filters={"policy": self.policy.name}, pluck="name"):
			frappe.delete_doc("Decision Policy Version", version_name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.delete_doc("Decision Policy", self.policy.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Deployment", self.deployment.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model", self.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", self.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", self.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", self.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", self.provider.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", self._prev_kill_switch)
		frappe.db.commit()

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)

	@staticmethod
	def _policy_definition() -> dict:
		return {
			"policy_id": "test-flow-dr-policy",
			"fallback_action": "fallback_default",
			"state_bindings": [{"name": "state", "path": "$"}],
			"questions": [
				{
					"id": "route",
					"kind": "select",
					"instructions": "Pick the right branch.",
					"options": [{"id": "branch_a", "label": "Branch A"}, {"id": "branch_b", "label": "Branch B"}],
				}
			],
		}

	# -- Flow graph construction ------------------------------------------------------------

	def _flow_id(self, label: str) -> str:
		flow_id = f"_test-flow-dr-{label}-{uuid.uuid4().hex[:8]}"
		return flow_id

	def _save_flow(self, flow_id: str, nodes: list[dict], *, minimum_confidence: float | None = None) -> dict:
		decide_config = {
			"policy": self.policy.name,
			"options": [{"label": "Branch A", "node_id": "branch_a"}],
			"default": "branch_default",
			"uncertain_next": "branch_uncertain",
			"state_bindings": [{"name": "state", "path": "$"}],
		}
		if minimum_confidence is not None:
			decide_config["minimum_confidence"] = minimum_confidence

		defn = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{"id": "start", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "decide"},
				{"id": "decide", "type": "router.decision", "config": decide_config},
				*nodes,
			],
			"contract": _contract(),
		}
		saved = flow_api.save_flow_definition(flow_id, defn)
		self._track("Flow Definition", saved["flow_id"])
		return defn

	def _default_branches(self) -> list[dict]:
		return [
			{"id": "branch_a", "type": "output", "config": {"value": "a"}},
			{"id": "branch_default", "type": "output", "config": {"value": "default"}},
			{"id": "branch_uncertain", "type": "output", "config": {"value": "uncertain"}},
		]

	def _run(self, flow_id: str) -> "frappe.Document":
		from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow

		flow_run = create_flow_run(flow_id=flow_id, payload={}, trigger_type="Doc Event")
		self._track("Flow Run", flow_run.name)
		engine_run_flow(flow_run.name)
		flow_run.reload()
		return flow_run


class TestRouterDecisionRouting(RouterDecisionFlowTestBase):
	"""Confident branch, low-confidence -> uncertain_next, backend down -> uncertain_next."""

	def test_confident_branch_routes_to_selected_node(self):
		flow_id = self._flow_id("confident")
		self._save_flow(flow_id, self._default_branches())

		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=_make_response("branch_a", confidence=0.95)),
		):
			flow_run = self._run(flow_id)

		self.assertEqual(flow_run.status, "Success", flow_run.last_error)
		self.assertEqual(flow_run.current_node_id, "branch_a")

	def test_low_confidence_routes_to_uncertain_next(self):
		flow_id = self._flow_id("lowconf")
		self._save_flow(flow_id, self._default_branches(), minimum_confidence=0.8)

		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=_make_response("branch_a", confidence=0.2)),
		):
			flow_run = self._run(flow_id)

		self.assertEqual(flow_run.status, "Success", flow_run.last_error)
		self.assertEqual(flow_run.current_node_id, "branch_uncertain")

	def test_backend_down_routes_to_uncertain_next(self):
		flow_id = self._flow_id("backdown")
		self._save_flow(flow_id, self._default_branches())

		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.UNAVAILABLE, response=DecisionResponse(status=DecisionStatus.UNAVAILABLE, error_code="backend_unavailable")),
		):
			flow_run = self._run(flow_id)

		self.assertEqual(flow_run.status, "Success", flow_run.last_error)
		self.assertEqual(flow_run.current_node_id, "branch_uncertain")


class TestSwitchOff(RouterDecisionFlowTestBase):
	"""Agent Settings.decision_runtime_enabled off -> switch-off message, follows uncertain_next."""

	def test_switch_off_follows_uncertain_next_with_switch_off_message(self):
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 0)
		flow_id = self._flow_id("switchoff")
		self._save_flow(flow_id, self._default_branches())

		with patch("huf.ai.decision.flow_adapter.service.run_policy") as mock_run_policy:
			flow_run = self._run(flow_id)

		mock_run_policy.assert_not_called()
		self.assertEqual(flow_run.status, "Success", flow_run.last_error)
		self.assertEqual(flow_run.current_node_id, "branch_uncertain")

	def test_switch_off_fails_when_no_uncertain_next(self):
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 0)
		flow_id = self._flow_id("switchoff-nofallback")
		decide_config = {
			"policy": self.policy.name,
			"options": [{"label": "Branch A", "node_id": "branch_a"}],
			"default": "branch_default",
		}
		defn = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{"id": "start", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "decide"},
				{"id": "decide", "type": "router.decision", "config": decide_config},
				{"id": "branch_a", "type": "output", "config": {"value": "a"}},
				{"id": "branch_default", "type": "output", "config": {"value": "default"}},
			],
			"contract": _contract(),
		}
		saved = flow_api.save_flow_definition(flow_id, defn)
		self._track("Flow Definition", saved["flow_id"])

		flow_run = self._run(flow_id)

		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("Decision Runtime is off for this site", flow_run.last_error or "")


class TestPolicyVersionPinAcrossResume(RouterDecisionFlowTestBase):
	"""D10: a Flow Run pins the published Decision Policy Version on first use, and a
	pause/resume (which rebuilds the whole run context from scratch) keeps using that
	pinned version even though a newer version has since been published."""

	def test_pin_persists_in_context_json_across_resume(self):
		flow_id = self._flow_id("pin")
		nodes = [
			{
				"id": "branch_a",
				"type": "human.approval",
				"config": {"message": "Approve?", "approve_next": "done", "reject_next": "branch_uncertain"},
			},
			{"id": "done", "type": "output", "config": {"value": "done"}},
			{"id": "branch_default", "type": "output", "config": {"value": "default"}},
			{"id": "branch_uncertain", "type": "output", "config": {"value": "uncertain"}},
		]
		self._save_flow(flow_id, nodes)

		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=_make_response("branch_a", confidence=0.95)),
		):
			flow_run = self._run(flow_id)

		self.assertEqual(flow_run.status, "Waiting Approval", flow_run.last_error)

		pinned_before = json.loads(flow_run.context_json or "{}").get("__decision_policy_pins__")
		self.assertIsNotNone(pinned_before, "decide node did not record a D10 pin")
		self.assertEqual(pinned_before["decide"]["version"], self.published_version)

		# Republish -- a running Flow must not change behaviour because a policy was
		# republished mid-run (D10 mirrors Flow's F-1 pin-on-create immunity).
		new_version = self.policy.publish_version()
		self.assertNotEqual(new_version, self.published_version)

		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=_make_response("branch_a"))

		from huf.ai.flow_engine import approve_flow_run

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			approve_flow_run(flow_run.name, "approved")

		flow_run.reload()
		self.assertEqual(flow_run.status, "Success", flow_run.last_error)
		self.assertEqual(flow_run.current_node_id, "done")

		# The "decide" node did not run again (approve_next skips straight to "done"), so
		# fake_run_policy above was never called -- prove the pin itself survived the
		# resume-triggered _build_run_context rebuild by reading it back from the
		# persisted context and by re-invoking the injected decision_router directly for
		# the same node, exactly as a second execution of "decide" would.
		pinned_after = json.loads(flow_run.context_json or "{}").get("__decision_policy_pins__")
		self.assertEqual(pinned_after["decide"]["version"], self.published_version)

		from huf.ai.flow_engine import _build_run_context, _pinned_version

		version = _pinned_version(flow_run)
		run_ctx = _build_run_context(flow_run, version)
		decision_router = run_ctx["decision_router"]
		self.assertIsNotNone(decision_router)

		node = {"id": "decide"}
		config = {"policy": self.policy.name, "options": [{"label": "Branch A", "node_id": "branch_a"}]}
		candidates = [{"to": "branch_a", "label": "Branch A"}]
		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			decision_router(flow_run, node, config, run_ctx.context.as_dict(), candidates)

		self.assertEqual(
			captured.get("policy_version"),
			self.published_version,
			"resume must keep using the version pinned on first use, not the newly published one",
		)
