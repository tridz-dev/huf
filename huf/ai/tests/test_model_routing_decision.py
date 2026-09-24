# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Model Routing (T5.02) test suite.

Covers PLAN.md §3.6 ("Model Routing" row) / HUF_Decision_Runtime_Implementation_Plan.md §12
("Surface 3 -- Agent model routing") end to end at the unit level:

- ``huf.ai.decision.model_routing.get_agent_model_candidates`` -- candidates are the Agent's
  default model plus its ``enable_auto_routing`` ``Agent Allowed Model`` rows, and never a
  Decision-only AI Model (IP §12.2/12.5).
- ``huf.ai.decision.model_routing.route_agent_model`` -- zero extra work when there is no
  enabled Model Routing binding; Enforce only ever returns a model from the candidate set it
  was given; any non-success degrades to ``(None, None)`` (Off, Shadow, error, timeout, budget
  exhaustion, or a hallucinated/stale id -- IP §12.5).
- ``huf.ai.agent_integration._resolve_effective_model`` -- routes only when the caller passed
  no override; records ``model_selection_source`` provenance (T1.21); a routed model still has
  to pass the pre-existing Decision-only guard (T1.15); RunBudget context is untouched.
- ``huf.ai.decision.binding.ADVISE_SURFACES`` -- Advise is not offered for Model Routing (D18):
  an Advise binding on this surface is downgraded to Off before ``run_policy`` is ever reached.

Per the swarm's SURFACE_API.md, these tests monkeypatch
``huf.ai.decision.agent_surfaces.decide_for_surface`` (never a real Decision backend/network
call) and build Agents as in-memory (unsaved) ``frappe.get_doc`` objects so no Agent Decision
Binding needs a real persisted ``Decision Policy`` to exist -- only the AI Provider/AI Model
records that ``is_decision_only_model`` genuinely needs to look up are inserted for real.

Run:
    bench --site dr-activation.local run-tests --app huf --module huf.ai.tests.test_model_routing_decision
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import _resolve_effective_model
from huf.ai.decision.agent_surfaces import SurfaceDecision
from huf.ai.decision.binding import ADVISE_SURFACES, resolve_agent_decision_binding
from huf.ai.decision.model_routing import (
	RouteableModel,
	get_agent_model_candidates,
	route_agent_model,
)
from huf.ai.tests.factories import make_ai_model, make_ai_provider


PREFIX = "_Test ModelRoutingDecision"


class TestModelRoutingDecision(IntegrationTestCase):
	"""Model Routing candidate sourcing, decision gating, and provenance."""

	def setUp(self):
		self._names = {"AI Provider": [], "AI Model": []}

		self.provider = make_ai_provider(provider_name="TestModelRouting", provider_brand="openai")
		self.provider.flags.ignore_mandatory = True
		self._track("AI Provider", self.provider.name)

		self.default_model = make_ai_model(
			provider=self.provider.name, model_name=f"{PREFIX}_default", modalities="Text"
		)
		self._track("AI Model", self.default_model.name)

		self.fast_model = make_ai_model(
			provider=self.provider.name, model_name=f"{PREFIX}_fast", modalities="Text"
		)
		self._track("AI Model", self.fast_model.name)

		self.excluded_model = make_ai_model(
			provider=self.provider.name, model_name=f"{PREFIX}_excluded", modalities="Text"
		)
		self._track("AI Model", self.excluded_model.name)

		self.decision_model = make_ai_model(
			provider=self.provider.name, model_name=f"{PREFIX}_decision_only", modalities="Decision"
		)
		self._track("AI Model", self.decision_model.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("AI Model", "AI Provider"):
			for name in self._names.get(doctype, []):
				try:
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
				except Exception:
					pass
		frappe.db.commit()

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)

	def _agent(self, allowed_models=(), decision_bindings=(), **overrides):
		"""An in-memory (never inserted) Agent doc -- no DB round-trip, no Link validation."""
		fields = {
			"doctype": "Agent",
			"agent_name": f"{PREFIX}-agent",
			"provider": self.provider.name,
			"model": self.default_model.name,
			"instructions": "You are a deterministic test agent.",
		}
		fields.update(overrides)
		agent = frappe.get_doc(fields)
		agent.name = fields.get("agent_name")
		for row in allowed_models:
			agent.append("allowed_models", row)
		for row in decision_bindings:
			agent.append("decision_bindings", row)
		return agent

	def _binding(self, mode="Enforce", policy="_test-model-routing-policy", **overrides):
		row = {"surface": "Model Routing", "policy": policy, "mode": mode, "enabled": 1, "priority": 100}
		row.update(overrides)
		return row

	# =========================================================================
	# get_agent_model_candidates -- authoritative candidate sourcing (IP §12.2/12.5)
	# =========================================================================

	def test_candidates_include_default_and_enabled_allowed_models(self):
		agent = self._agent(
			allowed_models=[
				{"model": self.fast_model.name, "provider": self.provider.name, "enable_auto_routing": 1},
			]
		)
		candidates = get_agent_model_candidates(agent)
		self.assertEqual({c.model for c in candidates}, {self.default_model.name, self.fast_model.name})

	def test_candidates_exclude_rows_with_auto_routing_disabled(self):
		agent = self._agent(
			allowed_models=[
				{"model": self.fast_model.name, "provider": self.provider.name, "enable_auto_routing": 1},
				{"model": self.excluded_model.name, "provider": self.provider.name, "enable_auto_routing": 0},
			]
		)
		candidates = {c.model for c in get_agent_model_candidates(agent)}
		self.assertIn(self.fast_model.name, candidates)
		self.assertNotIn(self.excluded_model.name, candidates)

	def test_candidates_never_include_a_decision_only_model(self):
		agent = self._agent(
			allowed_models=[
				{"model": self.decision_model.name, "provider": self.provider.name, "enable_auto_routing": 1},
			]
		)
		candidates = {c.model for c in get_agent_model_candidates(agent)}
		self.assertNotIn(self.decision_model.name, candidates)

	def test_candidates_exclude_decision_only_default_model_too(self):
		# Defensive: even if an Agent's own default somehow became Decision-only, routing must
		# never offer it as a candidate (agent_integration's own guard is a second layer, not
		# the only one).
		agent = self._agent(model=self.decision_model.name)
		candidates = get_agent_model_candidates(agent)
		self.assertEqual(candidates, ())

	def test_candidates_carry_routing_description_for_the_hint_and_state(self):
		agent = self._agent(
			allowed_models=[
				{
					"model": self.fast_model.name,
					"provider": self.provider.name,
					"enable_auto_routing": 1,
					"routing_description": "Cheap fallback for simple extraction.",
				}
			]
		)
		by_model = {c.model: c for c in get_agent_model_candidates(agent)}
		self.assertEqual(
			by_model[self.fast_model.name].routing_description, "Cheap fallback for simple extraction."
		)

	# =========================================================================
	# route_agent_model -- binding gate, Enforce-within-set, degrade-to-default
	# =========================================================================

	def test_no_binding_returns_default_without_building_candidates(self):
		agent = self._agent()  # no decision_bindings rows at all -> Off
		with patch(
			"huf.ai.decision.model_routing.get_agent_model_candidates",
			side_effect=AssertionError("must not build candidates when there is no binding"),
		):
			routed, decision_call = route_agent_model(agent)
		self.assertIsNone(routed)
		self.assertIsNone(decision_call)

	def test_disabled_binding_returns_default(self):
		agent = self._agent(decision_bindings=[self._binding(enabled=0)])
		routed, decision_call = route_agent_model(agent)
		self.assertIsNone(routed)
		self.assertIsNone(decision_call)

	def test_enforce_selects_a_model_within_the_candidate_set(self):
		agent = self._agent(
			decision_bindings=[self._binding(mode="Enforce")],
			allowed_models=[{"model": self.fast_model.name, "provider": self.provider.name, "enable_auto_routing": 1}],
		)
		decision = SurfaceDecision(mode="Enforce", selected_ids=(self.fast_model.name,), hint=None, decision_call="DC-001")
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=decision) as mock_decide:
			routed, decision_call = route_agent_model(agent, request_text="summarize this")
		self.assertEqual(routed.model, self.fast_model.name)
		self.assertEqual(decision_call, "DC-001")
		# Candidate provenance passed straight through, per SURFACE_API.md.
		_, kwargs = mock_decide.call_args
		self.assertEqual(kwargs["candidate_resolver_id"], "get_routeable_models")

	def test_enforce_result_outside_candidate_set_falls_back_to_default(self):
		# decide_for_surface itself guarantees selected_ids <= permitted ids (I-DR1), but a
		# defensive re-check at the call site must still hold if that ever regresses, or if the
		# candidate set legitimately changed between resolution and answer.
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		decision = SurfaceDecision(mode="Enforce", selected_ids=("stale-hallucinated-id",), hint=None, decision_call="DC-002")
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=decision):
			routed, decision_call = route_agent_model(agent)
		self.assertIsNone(routed)
		self.assertIsNone(decision_call)

	def test_any_decision_failure_falls_back_to_default(self):
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=None):
			routed, decision_call = route_agent_model(agent)
		self.assertIsNone(routed)
		self.assertIsNone(decision_call)

	def test_shadow_mode_never_narrows_and_returns_default(self):
		# decide_for_surface already returns None for Shadow (enqueued, D6); asserting the
		# surface call site treats that identically to Off/error.
		agent = self._agent(decision_bindings=[self._binding(mode="Shadow")])
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=None) as mock_decide:
			routed, decision_call = route_agent_model(agent)
		self.assertIsNone(routed)
		self.assertIsNone(decision_call)
		mock_decide.assert_called_once()

	# =========================================================================
	# Advise is not offered for Model Routing (D18)
	# =========================================================================

	def test_model_routing_not_in_advise_surfaces(self):
		self.assertNotIn("Model Routing", ADVISE_SURFACES)

	def test_advise_binding_on_model_routing_is_downgraded_to_off(self):
		agent = self._agent(decision_bindings=[self._binding(mode="Advise")])
		self.assertIsNone(resolve_agent_decision_binding(agent, "Model Routing"))

	def test_advise_binding_on_model_routing_never_reaches_decide_for_surface(self):
		agent = self._agent(decision_bindings=[self._binding(mode="Advise")])
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface") as mock_decide:
			routed, decision_call = route_agent_model(agent)
		mock_decide.assert_not_called()
		self.assertIsNone(routed)
		self.assertIsNone(decision_call)

	# =========================================================================
	# _resolve_effective_model integration -- gating, provenance, guard, RunBudget
	# =========================================================================

	def test_resolve_effective_model_skips_routing_when_caller_overrides(self):
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		with patch(
			"huf.ai.decision.model_routing.route_agent_model",
			side_effect=AssertionError("must not route when the caller passed an override"),
		):
			provider, model, model_name = _resolve_effective_model(agent, model=self.fast_model.name)
		self.assertEqual(model, self.fast_model.name)

	def test_resolve_effective_model_routes_when_no_override_and_records_provenance(self):
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		selection_context = {}
		with patch(
			"huf.ai.decision.model_routing.route_agent_model",
			return_value=(RouteableModel(model=self.fast_model.name, provider=self.provider.name), "DC-003"),
		) as mock_route:
			provider, model, model_name = _resolve_effective_model(
				agent, selection_context=selection_context, request_text="hello"
			)
		mock_route.assert_called_once()
		self.assertEqual(model, self.fast_model.name)
		self.assertEqual(provider, self.provider.name)
		self.assertEqual(selection_context["model_selection_source"], "decision_policy")
		self.assertEqual(selection_context["decision_call"], "DC-003")

	def test_resolve_effective_model_falls_back_to_agent_default_when_routing_yields_nothing(self):
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		selection_context = {}
		with patch("huf.ai.decision.model_routing.route_agent_model", return_value=(None, None)):
			provider, model, model_name = _resolve_effective_model(agent, selection_context=selection_context)
		self.assertEqual(model, self.default_model.name)
		self.assertEqual(selection_context["model_selection_source"], "agent_default")
		self.assertIsNone(selection_context["decision_call"])

	def test_resolve_effective_model_records_caller_override_source(self):
		agent = self._agent()
		selection_context = {}
		_resolve_effective_model(agent, model=self.fast_model.name, selection_context=selection_context)
		self.assertEqual(selection_context["model_selection_source"], "caller_override")

	def test_resolve_effective_model_records_orchestration_override_source(self):
		agent = self._agent()
		selection_context = {}
		_resolve_effective_model(
			agent,
			model=self.fast_model.name,
			override_source="orchestration_override",
			selection_context=selection_context,
		)
		self.assertEqual(selection_context["model_selection_source"], "orchestration_override")

	def test_a_routed_decision_only_model_still_hits_the_existing_guard(self):
		"""Even if routing itself picked a Decision-only model (should never happen given
		get_agent_model_candidates' own filter), _resolve_effective_model's pre-existing T1.15
		guard is a second, independent line of defense and must still fire."""
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		with patch(
			"huf.ai.decision.model_routing.route_agent_model",
			return_value=(RouteableModel(model=self.decision_model.name, provider=self.provider.name), "DC-004"),
		):
			with self.assertRaises(frappe.ValidationError):
				_resolve_effective_model(agent)

	def test_resolve_effective_model_does_not_touch_run_budget(self):
		# get_current_budget() returns a *fresh default* RunBudget object every time its
		# context var is unset (see run_budget.py), so identity comparison across two calls is
		# not meaningful by itself -- what must hold is that resolving the effective model never
		# calls set_current_budget (routing/model resolution must not read or write the budget
		# context; RunBudget accounting happens entirely in the caller, independent of routing).
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		with patch(
			"huf.ai.decision.model_routing.route_agent_model",
			return_value=(RouteableModel(model=self.fast_model.name, provider=self.provider.name), "DC-005"),
		):
			with patch(
				"huf.ai.run_budget.set_current_budget",
				side_effect=AssertionError("resolving the effective model must not touch RunBudget"),
			):
				_resolve_effective_model(agent)

	def test_sync_and_stream_style_calls_resolve_to_the_same_route(self):
		"""run_agent_sync's first resolution call (no conversation/agent_run yet) and
		run_agent_stream's first resolution call (conversation already exists) differ only in
		how much best-effort DecisionOrigin context they can supply -- both must land on the
		identical (provider, model, model_name, source) route for an equivalent turn."""
		agent = self._agent(decision_bindings=[self._binding(mode="Enforce")])
		routed = (RouteableModel(model=self.fast_model.name, provider=self.provider.name), "DC-006")
		with patch("huf.ai.decision.model_routing.route_agent_model", return_value=routed):
			sync_ctx, stream_ctx = {}, {}
			sync_result = _resolve_effective_model(
				agent, user="Administrator", request_text="hi", selection_context=sync_ctx
			)
			stream_result = _resolve_effective_model(
				agent,
				user="Administrator",
				conversation="some-conversation",
				request_text="hi",
				selection_context=stream_ctx,
			)
		self.assertEqual(sync_result, stream_result)
		self.assertEqual(sync_ctx["model_selection_source"], stream_ctx["model_selection_source"])
