"""Tests for huf.ai.decision.evaluation and its huf.ai.decision.api endpoints (T10.01).

Covers:
- get_policy_metrics: IP §19.3 aggregate metrics, grouped by version, null-vs-zero rates.
- get_shadow_agreement / get_followed_advice: correlation via Agent Run.model (Model Routing)
  and Agent Tool Call.tool (Tool Selection); every other surface reported as not_measurable.
- replay_policy: end-to-end rerun against a newer published version, marked surface, and its
  documented failure modes (no state_snapshot, cross-policy version).
- Capability gate (decision.run) on all four endpoints.

Fixtures mirror huf.ai.decision.tests.test_api_binding_stats.py / test_api.py (Decision Model/
Deployment/Policy hierarchy with the built-in "fake" backend, built once per class).
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import api
from huf.ai.tests.factories import make_user


def _make_user_unthrottled(*args, **kwargs):
	"""``make_user`` with ``User.before_insert``'s ``throttle_user_creation`` bypassed."""
	previous = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		return make_user(*args, **kwargs)
	finally:
		frappe.flags.in_import = previous


class TestEvaluationBase(FrappeTestCase):
	"""Shared Decision Model/Deployment/Policy fixtures, built once per class."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

		suffix = uuid.uuid4().hex[:8]

		cls.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": f"TestEvalProvider{suffix}",
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		cls.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": f"test-eval-model-{suffix}",
			"provider": cls.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		cls.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": f"test_eval_class_{suffix}",
			"class_name": "Test Eval Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": f"test_eval_family_{suffix}",
			"family_name": "Test Eval Family",
			"adapter_id": "fake",
			"model_class": cls.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": f"test-eval-model-key-{suffix}",
			"model_name": "Test Eval Model",
			"family": cls.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.deployment = frappe.get_doc({
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-eval-{suffix}",
			"deployment_name": "Test Eval Deployment",
			"decision_model": cls.decision_model.name,
			"ai_model": cls.ai_model.name,
			"provider": cls.provider.name,
			"provider_model_id": cls.ai_model.name,
			"wire_protocol": "systemone",
			"priority": 100,
			"enabled": 1,
			"is_default_for_model": 1,
		}).insert(ignore_permissions=True)

		# A select-kind policy with store_state=True: needed for replay (state_snapshot must be
		# persisted) and for shadow-agreement/followed-advice (a select answer's value is a
		# candidate id, comparable to an actual tool/model).
		cls.select_policy = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Test Eval Select Policy {suffix}",
			"purpose": "Tool Selection",
			"default_model": cls.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(cls._select_definition("test-eval-select-v1")),
		}).insert(ignore_permissions=True)
		cls.select_policy_version_1 = cls.select_policy.publish_version()

		cls.agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"Test Eval Agent {suffix}",
			"agent_type": "Standalone",
			"instructions": "You are a test agent.",
		}).insert(ignore_permissions=True)

		cls.run_only_user = _make_user_unthrottled(roles=("Huf User",)).email
		cls.admin_user = _make_user_unthrottled(roles=("Huf Manager",)).email
		cls.no_role_user = _make_user_unthrottled(roles=()).email

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Decision Call", filters={"decision_model": cls.decision_model.name}, pluck="name"):
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.delete_doc("Agent", cls.agent.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_value("Decision Policy", cls.select_policy.name, "current_version", None, update_modified=False)
		for version in frappe.get_all("Decision Policy Version", filters={"policy": cls.select_policy.name}, pluck="name"):
			frappe.delete_doc("Decision Policy Version", version, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.delete_doc("Decision Policy", cls.select_policy.name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.delete_doc("Decision Deployment", cls.deployment.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model", cls.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", cls.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", cls.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", cls.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", cls.provider.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", cls._prev_kill_switch)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup_calls: list[str] = []
		self._cleanup_agent_runs: list[str] = []
		self._cleanup_tool_calls: list[str] = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._cleanup_tool_calls:
			frappe.delete_doc("Agent Tool Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		for name in self._cleanup_calls:
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		for name in self._cleanup_agent_runs:
			frappe.delete_doc("Agent Run", name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.db.commit()

	# -- fixtures -----------------------------------------------------------------------

	@staticmethod
	def _select_definition(policy_id: str) -> dict:
		return {
			"policy_id": policy_id,
			"fallback_action": "fallback_default",
			"store_state": True,
			"state_bindings": [{"name": "state", "path": "$"}],
			"questions": [
				{
					"id": "q1",
					"kind": "select",
					"instructions": "Pick the best tool.",
					"options": [
						{"id": "toolA", "description": "Tool A"},
						{"id": "toolB", "description": "Tool B"},
					],
				}
			],
		}

	def _make_agent_run(self, *, model: str | None = None) -> str:
		run = frappe.get_doc({
			"doctype": "Agent Run",
			"agent": self.agent.name,
			"status": "Success",
			"model": model,
		}).insert(ignore_permissions=True)
		self._cleanup_agent_runs.append(run.name)
		return run.name

	def _make_tool_call(self, *, agent_run: str, tool: str) -> str:
		call = frappe.get_doc({
			"doctype": "Agent Tool Call",
			"agent_run": agent_run,
			"tool": tool,
			"status": "Completed",
		}).insert(ignore_permissions=True)
		self._cleanup_tool_calls.append(call.name)
		return call.name

	def _answer_json(self, *, value: str, probabilities: dict | None = None, kind: str = "select") -> str:
		return json.dumps({
			"q1": {
				"question_id": "q1",
				"kind": kind,
				"value": value,
				"probabilities": probabilities,
				"confidence": 0.9,
			}
		})

	def _make_decision_call(
		self,
		*,
		surface: str,
		policy: str | None = None,
		policy_version: str | None = None,
		mode: str = "Manual",
		status: str = "success",
		agent: str | None = None,
		agent_run: str | None = None,
		latency_ms: float | None = 100.0,
		input_tokens: int = 10,
		cost: float = 0.01,
		gate_result: str | None = "accepted",
		fallback_action: str | None = None,
		answer_json: str | None = None,
		started_at=None,
	) -> str:
		call = frappe.get_doc({
			"doctype": "Decision Call",
			"call_id": frappe.generate_hash(length=16),
			"agent": agent if agent is not None else self.agent.name,
			"agent_run": agent_run,
			"surface": surface,
			"policy": policy if policy is not None else self.select_policy.name,
			"policy_version": policy_version,
			"mode": mode,
			"status": status,
			"started_at": started_at or frappe.utils.now_datetime(),
			"latency_ms": latency_ms,
			"input_tokens": input_tokens,
			"cost": cost,
			"gate_result": gate_result,
			"fallback_action": fallback_action,
			"answer_json": answer_json or self._answer_json(value="toolA", probabilities={"toolA": 0.9, "toolB": 0.1}),
		}).insert(ignore_permissions=True)
		self._cleanup_calls.append(call.name)
		return call.name


class TestGetPolicyMetrics(TestEvaluationBase):
	def test_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.get_policy_metrics(self.select_policy.name)

	def test_empty_window_returns_null_rates_and_zero_counts(self):
		frappe.set_user(self.admin_user)
		result = api.get_policy_metrics(f"{self.select_policy.name}-does-not-exist-filter-only")
		overall = result["overall"]
		self.assertEqual(overall["decision_calls"], 0)
		self.assertIsNone(overall["success_rate"])
		self.assertIsNone(overall["fallback_rate"])
		self.assertEqual(overall["distribution_by_selected_option"], {})

	def test_aggregates_status_latency_tokens_cost(self):
		self._make_decision_call(
			surface="Tool Selection", status="success", latency_ms=100.0, input_tokens=10, cost=0.01,
			gate_result="accepted", answer_json=self._answer_json(value="toolA", probabilities={"toolA": 0.9, "toolB": 0.1}),
		)
		self._make_decision_call(
			surface="Tool Selection", status="timeout", latency_ms=3000.0, input_tokens=5, cost=0.0,
			gate_result="uncertain", fallback_action="fallback_default",
			answer_json=self._answer_json(value="none", probabilities=None),
		)
		self._make_decision_call(
			surface="Tool Selection", status="failed", latency_ms=None, input_tokens=0, cost=0.0,
			gate_result=None, fallback_action="fallback_default",
			answer_json="{}",
		)

		frappe.set_user(self.admin_user)
		result = api.get_policy_metrics(self.select_policy.name, surface="Tool Selection")
		overall = result["overall"]

		self.assertEqual(overall["decision_calls"], 3)
		self.assertAlmostEqual(overall["success_rate"], 1 / 3)
		self.assertAlmostEqual(overall["backend_error_rate"], 1 / 3)  # "failed"
		self.assertAlmostEqual(overall["timeout_rate"], 1 / 3)
		self.assertEqual(overall["input_tokens"], 15)
		self.assertAlmostEqual(overall["cost"], 0.01)
		self.assertAlmostEqual(overall["fallback_rate"], 2 / 3)
		# 1 of 2 gated rows is "uncertain"
		self.assertAlmostEqual(overall["low_confidence_rate"], 1 / 2)
		# 1 of 3 rows answered "none"
		self.assertAlmostEqual(overall["no_match_rate"], 1 / 3)
		self.assertEqual(overall["distribution_by_selected_option"], {"toolA": 1})
		self.assertEqual(result["sample_size"], 3)
		self.assertFalse(result["sample_capped"])

	def test_groups_by_policy_version(self):
		version_1 = self.select_policy_version_1
		doc = frappe.get_doc("Decision Policy", self.select_policy.name)
		doc.definition_json = frappe.as_json(self._select_definition("test-eval-select-v2-metrics"))
		doc.save(ignore_permissions=True)
		version_2 = doc.publish_version()
		try:
			self._make_decision_call(surface="Tool Selection", policy_version=version_1, status="success")
			self._make_decision_call(surface="Tool Selection", policy_version=version_1, status="success")
			self._make_decision_call(surface="Tool Selection", policy_version=version_2, status="failed")

			frappe.set_user(self.admin_user)
			result = api.get_policy_metrics(self.select_policy.name, surface="Tool Selection")

			self.assertEqual(result["overall"]["decision_calls"], 3)
			self.assertEqual(result["by_version"][version_1]["decision_calls"], 2)
			self.assertEqual(result["by_version"][version_1]["success_rate"], 1.0)
			self.assertEqual(result["by_version"][version_2]["decision_calls"], 1)
			self.assertEqual(result["by_version"][version_2]["success_rate"], 0.0)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Decision Policy", self.select_policy.name, "current_version", version_1, update_modified=False)
			frappe.delete_doc("Decision Policy Version", version_2, ignore_permissions=True, ignore_missing=True, force=True)

	def test_from_to_date_window_excludes_older_calls(self):
		old = frappe.utils.now_datetime() - timedelta(days=30)
		self._make_decision_call(surface="Tool Selection", started_at=old)
		self._make_decision_call(surface="Tool Selection")

		frappe.set_user(self.admin_user)
		result = api.get_policy_metrics(
			self.select_policy.name,
			surface="Tool Selection",
			from_date=frappe.utils.now_datetime() - timedelta(days=1),
		)
		self.assertEqual(result["overall"]["decision_calls"], 1)


class TestGetShadowAgreement(TestEvaluationBase):
	def test_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.get_shadow_agreement(policy=self.select_policy.name)

	def test_model_routing_matched(self):
		agent_run = self._make_agent_run(model=self.ai_model.name)
		self._make_decision_call(
			surface="Model Routing", mode="Shadow", agent_run=agent_run,
			answer_json=self._answer_json(value=self.ai_model.name, probabilities={self.ai_model.name: 1.0}),
		)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="Model Routing")

		self.assertIn("Model Routing", result["by_surface"])
		bucket = result["by_surface"]["Model Routing"]
		self.assertEqual(bucket["sampled"], 1)
		self.assertEqual(bucket["measurable"], 1)
		self.assertEqual(bucket["rate"], 1.0)
		self.assertNotIn("Model Routing", result["not_measurable"])

	def test_model_routing_mismatched(self):
		agent_run = self._make_agent_run(model=self.ai_model.name)
		# Shadow picked a different model docname than what actually ran.
		self._make_decision_call(
			surface="Model Routing", mode="Shadow", agent_run=agent_run,
			answer_json=self._answer_json(value="some-other-model-docname", probabilities=None),
		)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="Model Routing")

		bucket = result["by_surface"]["Model Routing"]
		self.assertEqual(bucket["measurable"], 1)
		self.assertEqual(bucket["rate"], 0.0)

	def test_tool_selection_matched_via_agent_tool_call(self):
		agent_run = self._make_agent_run()
		self._make_tool_call(agent_run=agent_run, tool="toolA")
		self._make_decision_call(
			surface="Tool Selection", mode="Shadow", agent_run=agent_run,
			answer_json=self._answer_json(value="toolA", probabilities={"toolA": 0.8, "toolB": 0.2}),
		)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="Tool Selection")

		bucket = result["by_surface"]["Tool Selection"]
		self.assertEqual(bucket["measurable"], 1)
		self.assertEqual(bucket["rate"], 1.0)

	def test_tool_selection_not_measurable_without_tool_calls(self):
		agent_run = self._make_agent_run()  # no Agent Tool Call rows recorded
		self._make_decision_call(surface="Tool Selection", mode="Shadow", agent_run=agent_run)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="Tool Selection")

		bucket = result["by_surface"]["Tool Selection"]
		self.assertEqual(bucket["sampled"], 1)
		self.assertEqual(bucket["measurable"], 0)
		self.assertIsNone(bucket["rate"])

	def test_would_have_fallback_rate_uses_all_sampled_rows(self):
		# Regardless of measurability, would-have-fallback is intrinsic to the shadow call.
		agent_run = self._make_agent_run()
		self._make_decision_call(surface="RAG Filter", mode="Shadow", agent_run=agent_run, fallback_action="fallback_default")
		self._make_decision_call(surface="RAG Filter", mode="Shadow", agent_run=agent_run, fallback_action=None)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="RAG Filter")

		self.assertIn("RAG Filter", result["not_measurable"])
		self.assertEqual(result["not_measurable"]["RAG Filter"]["sampled"], 2)
		bucket = result["by_surface"]["RAG Filter"]
		self.assertEqual(bucket["would_have_fallback_rate"], 0.5)
		self.assertIsNone(bucket["rate"])

	def test_unmeasurable_surface_reported_with_reason(self):
		agent_run = self._make_agent_run()
		self._make_decision_call(surface="Procedure Selection", mode="Shadow", agent_run=agent_run)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="Procedure Selection")

		self.assertIn("Procedure Selection", result["not_measurable"])
		self.assertIn("reason", result["not_measurable"]["Procedure Selection"])
		self.assertIn("Model Routing", result["measurable_surfaces"])
		self.assertIn("Tool Selection", result["measurable_surfaces"])

	def test_only_shadow_mode_calls_are_included(self):
		agent_run = self._make_agent_run(model=self.ai_model.name)
		self._make_decision_call(surface="Model Routing", mode="Enforce", agent_run=agent_run)

		frappe.set_user(self.admin_user)
		result = api.get_shadow_agreement(agent=self.agent.name, surface="Model Routing")
		self.assertEqual(result["sample_size"], 0)


class TestGetFollowedAdvice(TestEvaluationBase):
	def test_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.get_followed_advice(policy=self.select_policy.name)

	def test_tool_selection_advise_matched(self):
		agent_run = self._make_agent_run()
		self._make_tool_call(agent_run=agent_run, tool="toolB")
		self._make_decision_call(
			surface="Tool Selection", mode="Advise", agent_run=agent_run,
			answer_json=self._answer_json(value="toolB", probabilities={"toolA": 0.2, "toolB": 0.8}),
		)

		frappe.set_user(self.admin_user)
		result = api.get_followed_advice(agent=self.agent.name, surface="Tool Selection")

		bucket = result["by_surface"]["Tool Selection"]
		self.assertEqual(bucket["measurable"], 1)
		self.assertEqual(bucket["rate"], 1.0)

	def test_skill_selection_not_measurable(self):
		agent_run = self._make_agent_run()
		self._make_decision_call(surface="Skill Selection", mode="Advise", agent_run=agent_run)

		frappe.set_user(self.admin_user)
		result = api.get_followed_advice(agent=self.agent.name, surface="Skill Selection")

		self.assertIn("Skill Selection", result["not_measurable"])

	def test_only_advise_mode_calls_are_included(self):
		agent_run = self._make_agent_run()
		self._make_tool_call(agent_run=agent_run, tool="toolA")
		self._make_decision_call(surface="Tool Selection", mode="Shadow", agent_run=agent_run)

		frappe.set_user(self.admin_user)
		result = api.get_followed_advice(agent=self.agent.name, surface="Tool Selection")
		self.assertEqual(result["sample_size"], 0)


class TestReplayPolicy(TestEvaluationBase):
	def _run_original_call(self, *, user: str) -> tuple[str, str]:
		"""Run a real select-kind Manual decision through service.run_policy (via api.run_decision)
		so the resulting Decision Call has a genuine state_snapshot/candidate_ids_json to replay.
		Returns (decision_call_name, policy_version_1_name)."""
		frappe.set_user(user)
		result = api.run_decision(
			policy=self.select_policy.name,
			state=json.dumps({"request": "please pick a tool"}),
			candidates=json.dumps([
				{"id": "toolA", "description": "Tool A"},
				{"id": "toolB", "description": "Tool B"},
			]),
			candidate_source="routeable_models",
			candidate_resolver_id="test-resolver",
			origin_type="Playground",
		)
		frappe.set_user("Administrator")
		self.assertEqual(result["status"], "success")
		self._cleanup_calls.append(result["decision_call"])
		return result["decision_call"], self.select_policy_version_1

	def _publish_new_version(self) -> str:
		"""Publish a second version of select_policy (same question/options, different id) so a
		replay target belongs to the same policy but is a different, newer version."""
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Decision Policy", self.select_policy.name)
		doc.definition_json = frappe.as_json(self._select_definition("test-eval-select-v2"))
		doc.save(ignore_permissions=True)
		version_2 = doc.publish_version()
		return version_2

	def test_requires_decision_run(self):
		decision_call, _ = self._run_original_call(user=self.run_only_user)
		version_2 = self._publish_new_version()

		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.replay_policy(decision_call, version_2)

	def test_replay_reruns_against_newer_version_and_marks_surface(self):
		decision_call, version_1 = self._run_original_call(user=self.run_only_user)
		version_2 = self._publish_new_version()

		frappe.set_user(self.run_only_user)
		outcome = api.replay_policy(
			decision_call,
			version_2,
			candidate_source="routeable_models",
			candidate_resolver_id="test-replay-resolver",
		)

		self.assertEqual(outcome["original_decision_call"], decision_call)
		self.assertEqual(outcome["original_policy_version"], version_1)
		self.assertEqual(outcome["target_policy_version"], version_2)
		self.assertIsNotNone(outcome["replay_decision_call"])
		self.assertNotEqual(outcome["replay_decision_call"], decision_call)
		self.assertEqual(outcome["result"]["status"], "success")
		self.assertIn("q1", outcome["result"]["response"]["answers"])
		self.assertTrue(outcome["limitations"])  # non-empty, documents what was reconstructed

		self._cleanup_calls.append(outcome["replay_decision_call"])
		replay_call = frappe.get_doc("Decision Call", outcome["replay_decision_call"])
		self.assertEqual(replay_call.surface, "Replay:Playground")
		self.assertEqual(replay_call.origin_type, "Playground")
		self.assertEqual(replay_call.policy_version, version_2)
		self.assertEqual(replay_call.mode, "Manual")

	def test_replay_without_state_snapshot_raises(self):
		# A Decision Call inserted directly (not through store_state=True machinery) has no
		# state_snapshot -- replay must refuse rather than run with state=None.
		call = self._make_decision_call(surface="Tool Selection", policy_version=self.select_policy_version_1)
		version_2 = self._publish_new_version()

		frappe.set_user(self.admin_user)
		with self.assertRaises(frappe.ValidationError):
			api.replay_policy(call, version_2)

	def test_replay_against_version_of_different_policy_raises(self):
		decision_call, _ = self._run_original_call(user=self.run_only_user)

		other_policy = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Other Policy {frappe.generate_hash(length=8)}",
			"purpose": "Tool Selection",
			"default_model": self.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(self._select_definition("other-policy")),
		}).insert(ignore_permissions=True)
		other_version = other_policy.publish_version()

		frappe.set_user(self.run_only_user)
		try:
			with self.assertRaises(frappe.ValidationError):
				api.replay_policy(decision_call, other_version)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Decision Policy", other_policy.name, "current_version", None, update_modified=False)
			for version in frappe.get_all("Decision Policy Version", filters={"policy": other_policy.name}, pluck="name"):
				frappe.delete_doc("Decision Policy Version", version, ignore_permissions=True, ignore_missing=True, force=True)
			frappe.delete_doc("Decision Policy", other_policy.name, ignore_permissions=True, ignore_missing=True, force=True)
