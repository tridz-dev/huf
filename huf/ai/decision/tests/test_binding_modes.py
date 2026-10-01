"""Test decision binding modes and surface validation."""

import unittest
from types import SimpleNamespace

import frappe
from frappe.test_runner import make_test_objects
from huf.ai.decision.binding import ADVISE_SURFACES, resolve_agent_decision_binding


class TestAdviceSurfacesConstant(unittest.TestCase):
	"""Test that ADVISE_SURFACES is defined and contains the correct surfaces."""

	def test_advise_surfaces_defined(self):
		"""ADVISE_SURFACES constant should be defined."""
		self.assertIsNotNone(ADVISE_SURFACES)
		self.assertIsInstance(ADVISE_SURFACES, set)

	def test_advise_surfaces_contains_required_surfaces(self):
		"""ADVISE_SURFACES should contain all surfaces that support Advise mode."""
		required = {"Tool Selection", "Skill Selection", "Procedure Selection", "Agent Routing", "RAG Filter"}
		self.assertEqual(ADVISE_SURFACES, required)

	def test_advise_surfaces_exact_strings(self):
		"""Verify exact string matching for surface names."""
		for surface in ADVISE_SURFACES:
			self.assertIsInstance(surface, str)
			self.assertTrue(len(surface) > 0)


class TestBindingResolutionWithAdvise(unittest.TestCase):
	"""Test that resolve_agent_decision_binding works correctly with Advise mode."""

	def test_advise_binding_on_valid_surface_is_resolved(self):
		"""Advise binding on a valid surface should be returned when requested."""
		agent = SimpleNamespace(
			decision_bindings=[
				SimpleNamespace(
					surface="Tool Selection",
					policy="test_policy",
					mode="Advise",
					priority=100,
					enabled=True
				)
			]
		)
		resolved = resolve_agent_decision_binding(agent, "Tool Selection", requested_mode="Advise")
		self.assertIsNotNone(resolved)
		self.assertEqual(resolved.mode, "Advise")
		self.assertEqual(resolved.surface, "Tool Selection")

	def test_advise_binding_on_valid_surface_returned_without_request(self):
		"""Advise binding should be returned even without explicit request (default behavior)."""
		agent = SimpleNamespace(
			decision_bindings=[
				SimpleNamespace(
					surface="Tool Selection",
					policy="test_policy",
					mode="Advise",
					priority=100,
					enabled=True
				)
			]
		)
		resolved = resolve_agent_decision_binding(agent, "Tool Selection")
		self.assertIsNotNone(resolved)
		self.assertEqual(resolved.mode, "Advise")

	def test_shadow_binding_is_resolved_when_requested(self):
		"""Shadow binding should be returned when explicitly requested."""
		agent = SimpleNamespace(
			decision_bindings=[
				SimpleNamespace(
					surface="Tool Selection",
					policy="test_policy",
					mode="Shadow",
					priority=100,
					enabled=True
				)
			]
		)
		resolved = resolve_agent_decision_binding(agent, "Tool Selection", requested_mode="Shadow")
		self.assertIsNotNone(resolved)
		self.assertEqual(resolved.mode, "Shadow")

	def test_enforce_binding_is_resolved_when_requested(self):
		"""Enforce binding should be returned when explicitly requested."""
		agent = SimpleNamespace(
			decision_bindings=[
				SimpleNamespace(
					surface="Tool Selection",
					policy="test_policy",
					mode="Enforce",
					priority=100,
					enabled=True
				)
			]
		)
		resolved = resolve_agent_decision_binding(agent, "Tool Selection", requested_mode="Enforce")
		self.assertIsNotNone(resolved)
		self.assertEqual(resolved.mode, "Enforce")

	def test_off_binding_never_resolved(self):
		"""Off mode binding should never be returned."""
		agent = SimpleNamespace(
			decision_bindings=[
				SimpleNamespace(
					surface="Tool Selection",
					policy="test_policy",
					mode="Off",
					priority=100,
					enabled=True
				)
			]
		)
		resolved = resolve_agent_decision_binding(agent, "Tool Selection", requested_mode="Shadow")
		self.assertIsNone(resolved)


class TestAdviceSurfaceValidation(unittest.TestCase):
	"""Test Agent.validate() with decision binding surfaces."""

	def test_advise_on_tool_selection_is_valid(self):
		"""Advise mode on Tool Selection surface should be valid."""
		try:
			agent = frappe.get_doc({
				"doctype": "Agent",
				"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
				"instructions": "Test agent",
				"provider": "",
				"model": "",
				"decision_bindings": [
					{
						"surface": "Tool Selection",
						"mode": "Advise",
						"policy": "test_policy",
						"enabled": True
					}
				]
			})
			agent.validate()
		except frappe.ValidationError as e:
			self.fail(f"Advise on Tool Selection should be valid, but raised: {e}")

	def test_advise_on_skill_selection_is_valid(self):
		"""Advise mode on Skill Selection surface should be valid."""
		try:
			agent = frappe.get_doc({
				"doctype": "Agent",
				"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
				"instructions": "Test agent",
				"provider": "",
				"model": "",
				"decision_bindings": [
					{
						"surface": "Skill Selection",
						"mode": "Advise",
						"policy": "test_policy",
						"enabled": True
					}
				]
			})
			agent.validate()
		except frappe.ValidationError as e:
			self.fail(f"Advise on Skill Selection should be valid, but raised: {e}")

	def test_advise_on_procedure_selection_is_valid(self):
		"""Advise mode on Procedure Selection surface should be valid."""
		try:
			agent = frappe.get_doc({
				"doctype": "Agent",
				"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
				"instructions": "Test agent",
				"provider": "",
				"model": "",
				"decision_bindings": [
					{
						"surface": "Procedure Selection",
						"mode": "Advise",
						"policy": "test_policy",
						"enabled": True
					}
				]
			})
			agent.validate()
		except frappe.ValidationError as e:
			self.fail(f"Advise on Procedure Selection should be valid, but raised: {e}")

	def test_advise_on_agent_routing_is_valid(self):
		"""Advise mode on Agent Routing surface should be valid."""
		try:
			agent = frappe.get_doc({
				"doctype": "Agent",
				"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
				"instructions": "Test agent",
				"provider": "",
				"model": "",
				"decision_bindings": [
					{
						"surface": "Agent Routing",
						"mode": "Advise",
						"policy": "test_policy",
						"enabled": True
					}
				]
			})
			agent.validate()
		except frappe.ValidationError as e:
			self.fail(f"Advise on Agent Routing should be valid, but raised: {e}")

	def test_advise_on_rag_filter_is_valid(self):
		"""Advise mode on RAG Filter surface should be valid."""
		try:
			agent = frappe.get_doc({
				"doctype": "Agent",
				"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
				"instructions": "Test agent",
				"provider": "",
				"model": "",
				"decision_bindings": [
					{
						"surface": "RAG Filter",
						"mode": "Advise",
						"policy": "test_policy",
						"enabled": True
					}
				]
			})
			agent.validate()
		except frappe.ValidationError as e:
			self.fail(f"Advise on RAG Filter should be valid, but raised: {e}")

	def test_advise_on_model_routing_is_invalid(self):
		"""Advise mode on Model Routing surface should be invalid."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Model Routing",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		self.assertIn("Advise mode is not supported", str(context.exception))
		self.assertIn("Model Routing", str(context.exception))

	def test_advise_on_context_relevance_is_invalid(self):
		"""Advise mode on Context Relevance surface should be invalid."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Context Relevance",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		self.assertIn("Advise mode is not supported", str(context.exception))

	def test_advise_on_input_guardrail_is_invalid(self):
		"""Advise mode on Input Guardrail surface should be invalid."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Input Guardrail",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		self.assertIn("Advise mode is not supported", str(context.exception))

	def test_advise_on_output_guardrail_is_invalid(self):
		"""Advise mode on Output Guardrail surface should be invalid."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Output Guardrail",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		self.assertIn("Advise mode is not supported", str(context.exception))

	def test_advise_on_output_verification_is_invalid(self):
		"""Advise mode on Output Verification surface should be invalid."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Output Verification",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		self.assertIn("Advise mode is not supported", str(context.exception))

	def test_advise_on_agent_tool_is_invalid(self):
		"""Advise mode on Agent Tool surface should be invalid."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Agent Tool",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		self.assertIn("Advise mode is not supported", str(context.exception))

	def test_other_modes_on_all_surfaces_are_valid(self):
		"""Off, Shadow, and Enforce modes should be valid on all surfaces."""
		all_surfaces = [
			"Model Routing",
			"Tool Selection",
			"Skill Selection",
			"Procedure Selection",
			"Context Relevance",
			"Input Guardrail",
			"Output Guardrail",
			"Output Verification",
			"RAG Filter",
			"Agent Routing",
			"Agent Tool"
		]
		other_modes = ["Off", "Shadow", "Enforce"]

		for surface in all_surfaces:
			for mode in other_modes:
				try:
					agent = frappe.get_doc({
						"doctype": "Agent",
						"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
						"instructions": "Test agent",
						"provider": "",
						"model": "",
						"decision_bindings": [
							{
								"surface": surface,
								"mode": mode,
								"policy": "test_policy",
								"enabled": True
							}
						]
					})
					agent.validate()
				except frappe.ValidationError as e:
					self.fail(f"{mode} on {surface} should be valid, but raised: {e}")

	def test_error_message_lists_allowed_surfaces(self):
		"""Error message for invalid Advise surface should list allowed surfaces."""
		agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"test_agent_{frappe.utils.random_string(8)}",
			"instructions": "Test agent",
			"provider": "",
			"model": "",
			"decision_bindings": [
				{
					"surface": "Model Routing",
					"mode": "Advise",
					"policy": "test_policy",
					"enabled": True
				}
			]
		})
		with self.assertRaises(frappe.ValidationError) as context:
			agent.validate()
		error_msg = str(context.exception)
		self.assertIn("Tool Selection", error_msg)
		self.assertIn("Skill Selection", error_msg)
		self.assertIn("Procedure Selection", error_msg)
		self.assertIn("Agent Routing", error_msg)
		self.assertIn("RAG Filter", error_msg)


class ResolverAdviseFallbackTests(unittest.TestCase):
	def test_advise_on_unsupported_surface_resolves_as_off(self):
		from types import SimpleNamespace

		from huf.ai.decision.binding import resolve_agent_decision_binding

		row = SimpleNamespace(enabled=1, surface="Model Routing", mode="Advise", policy="p", priority=1)
		agent = SimpleNamespace(decision_bindings=[row])
		self.assertIsNone(resolve_agent_decision_binding(agent, "Model Routing"))
