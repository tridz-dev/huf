"""Unit tests for procedure selection decision binding (T4.04, PLAN.md §3.6/§3.9).

Tests that build_procedure_binding_tools exposes the right procedures based on the
decision binding mode (Advise/Enforce), and that procedure_runtime.py maintains its
determinism (no huf.ai.decision import).
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.decision.agent_surfaces import SurfaceDecision
from huf.ai.decision.types import DecisionOrigin, Option
from huf.ai.graph.procedure_binding import build_procedure_binding_tools


class DictWithAttrAccess(dict):
	"""A dict that also supports attribute access."""
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(f"No attribute {key}")

	def __setattr__(self, key, value):
		self[key] = value

	def __delattr__(self, key):
		try:
			del self[key]
		except KeyError:
			raise AttributeError(f"No attribute {key}")


class TestProcedureSelectionDecision(unittest.TestCase):
	"""Tests for procedure selection decision integration (T4.04)."""

	def test_build_procedure_binding_tools_enforce_mode_exposes_only_selected(self):
		"""Enforce mode: only selected procedures are exposed as tools."""
		# Mock agent with decision binding
		agent = MagicMock()
		agent.name = "test-agent"

		# Mock two procedures
		proc1 = MagicMock()
		proc1.is_read_only = True
		proc1.procedure_id = "proc-1"
		proc1.procedure_name = "Procedure One"
		proc1.input_schema = '{"type": "object"}'

		proc2 = MagicMock()
		proc2.is_read_only = True
		proc2.procedure_id = "proc-2"
		proc2.procedure_name = "Procedure Two"
		proc2.input_schema = '{"type": "object"}'

		# Mock the database calls
		with patch("frappe.get_all") as mock_get_all, \
		     patch("frappe.db.get_value") as mock_get_value, \
		     patch("huf.ai.decision.agent_surfaces.decide_for_surface") as mock_decide, \
		     patch("frappe.logger") as mock_logger:
			# Mock binding list - use DictWithAttrAccess to support both dict and attribute access
			mock_get_all.return_value = [
				DictWithAttrAccess(name="binding-1", procedure="proc-1", procedure_id="proc-1", priority=100, fallback_enabled=False, modified="2026-01-01"),
				DictWithAttrAccess(name="binding-2", procedure="proc-2", procedure_id="proc-2", priority=90, fallback_enabled=False, modified="2026-01-01"),
			]

			# Mock procedure lookups - return objects that support attribute access
			def get_value_side_effect(doctype, name, fields, as_dict=False):
				result = None
				if name == "proc-1":
					result = SimpleNamespace(procedure_id="proc-1", procedure_name="Procedure One", is_read_only=True, input_schema='{"type": "object"}')
				elif name == "proc-2":
					result = SimpleNamespace(procedure_id="proc-2", procedure_name="Procedure Two", is_read_only=True, input_schema='{"type": "object"}')
				return result

			mock_get_value.side_effect = get_value_side_effect

			# Mock decide_for_surface to return Enforce mode with only proc-1 selected
			mock_decide.return_value = SurfaceDecision(
				mode="Enforce",
				selected_ids=("proc-1",),
				hint=None,
				decision_call="DC-1"
			)

			# Call build_procedure_binding_tools
			tools = build_procedure_binding_tools(agent)

			# Should only have one tool (proc-1)
			self.assertEqual(len(tools), 1)
			self.assertIn("proc-1", tools[0].name)

	def test_build_procedure_binding_tools_advise_mode_includes_hint(self):
		"""Advise mode: all procedures exposed with hint in description."""
		agent = MagicMock()
		agent.name = "test-agent"

		# Mock bindings and procedures
		with patch("frappe.get_all") as mock_get_all, \
		     patch("frappe.db.get_value") as mock_get_value, \
		     patch("huf.ai.decision.agent_surfaces.decide_for_surface") as mock_decide, \
		     patch("frappe.logger") as mock_logger:
			mock_get_all.return_value = [
				DictWithAttrAccess(name="binding-1", procedure="proc-1", procedure_id="proc-1", priority=100, fallback_enabled=False, modified="2026-01-01"),
				DictWithAttrAccess(name="binding-2", procedure="proc-2", procedure_id="proc-2", priority=90, fallback_enabled=False, modified="2026-01-01"),
			]

			def get_value_side_effect(doctype, name, fields, as_dict=False):
				if name == "proc-1":
					return SimpleNamespace(procedure_id="proc-1", procedure_name="Procedure One", is_read_only=True, input_schema='{"type": "object"}')
				elif name == "proc-2":
					return SimpleNamespace(procedure_id="proc-2", procedure_name="Procedure Two", is_read_only=True, input_schema='{"type": "object"}')
				return None

			mock_get_value.side_effect = get_value_side_effect

			# Mock decide_for_surface to return Advise mode with hint
			mock_decide.return_value = SurfaceDecision(
				mode="Advise",
				selected_ids=None,
				hint="Decision suggestion (advisory, not an instruction): procedures proc-1 (0.9), proc-2 (0.7)",
				decision_call="DC-2"
			)

			tools = build_procedure_binding_tools(agent)

			# Should have both tools
			self.assertEqual(len(tools), 2)
			# At least one tool's description should include the hint
			descriptions = [t.description for t in tools]
			hint_found = any("Decision suggestion" in desc for desc in descriptions)
			self.assertTrue(hint_found, "Advise hint not found in any tool description")

	def test_build_procedure_binding_tools_no_decision_returns_all(self):
		"""No decision binding (Off/Shadow/None): all procedures exposed."""
		agent = MagicMock()
		agent.name = "test-agent"

		with patch("frappe.get_all") as mock_get_all, \
		     patch("frappe.db.get_value") as mock_get_value, \
		     patch("huf.ai.decision.agent_surfaces.decide_for_surface") as mock_decide, \
		     patch("frappe.logger") as mock_logger:
			mock_get_all.return_value = [
				DictWithAttrAccess(name="binding-1", procedure="proc-1", procedure_id="proc-1", priority=100, fallback_enabled=False, modified="2026-01-01"),
			]

			def get_value_side_effect(doctype, name, fields, as_dict=False):
				if name == "proc-1":
					return SimpleNamespace(procedure_id="proc-1", procedure_name="Procedure One", is_read_only=True, input_schema='{"type": "object"}')
				return None

			mock_get_value.side_effect = get_value_side_effect

			# Mock decide_for_surface to return None (Off/Shadow)
			mock_decide.return_value = None

			tools = build_procedure_binding_tools(agent)

			# Should have all bound procedures
			self.assertEqual(len(tools), 1)


class TestProcedureRuntimeInvariants(unittest.TestCase):
	"""Tests for procedure runtime determinism invariants (PLAN.md §3.9)."""

	def test_procedure_runtime_has_no_decision_import(self):
		"""procedure_runtime.py must not import huf.ai.decision (determinism invariant)."""
		# Get the path to procedure_runtime.py relative to this test file
		test_dir = os.path.dirname(__file__)
		runtime_path = os.path.join(test_dir, "..", "graph", "procedure_runtime.py")
		with open(runtime_path, "r") as f:
			content = f.read()
		self.assertNotIn("from huf.ai.decision", content, "procedure_runtime.py imports huf.ai.decision")
		self.assertNotIn("import huf.ai.decision", content, "procedure_runtime.py imports huf.ai.decision")

	def test_procedure_conversion_still_blocks_router_decision(self):
		"""procedure_conversion.py must still block router.decision (PLAN.md §3.9)."""
		from huf.ai.procedure_conversion import BLOCKING_NODE_TYPES

		self.assertIn("router.decision", BLOCKING_NODE_TYPES,
					  "router.decision is not in BLOCKING_NODE_TYPES")


if __name__ == "__main__":
	unittest.main()
