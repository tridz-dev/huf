# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Standalone unit tests for the T-34 procedure additions to
huf.ai.tools.lazy_discovery: bound Agent Procedures must appear in all four
discovery handlers (grouped separately, not mixed with atomic tools), their
input_schema must load only on demand (never in list_tool_groups), and every
handler must re-check permissions via get_bound_procedures_for_agent (I1) --
never trust an earlier discovery response.

This file complements huf.ai.tests.test_lazy_tool_discovery (bench-only,
real doctypes) with a hand-written-double standalone path, per this repo's
"never a bare MagicMock" convention (see test_procedure_binding.py /
test_graph_permissions.py).

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_lazy_discovery_procedures
"""

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _install_standalone_frappe_stub():
	"""See huf.ai.tests.test_graph_permissions._install_standalone_frappe_stub -- same
	rationale: huf/__init__.py does `import frappe` unconditionally at package-import
	time, before conftest.py's stub would otherwise run.
	"""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: (lambda f: f)
	fake.logger = lambda *a, **k: _NullLogger()

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


class _NullLogger:
	def warning(self, *a, **k):
		pass

	def debug(self, *a, **k):
		pass


_install_standalone_frappe_stub()

from huf.ai.graph.procedure_binding import BoundProcedure
from huf.ai.tools import lazy_discovery


class _ToolDoc:
	def __init__(self, tool_name, description="", service=None, provider_app=None, params=None):
		self.tool_name = tool_name
		self.description = description
		self.service = service
		self.provider_app = provider_app
		self.params = params


def _bound(procedure_id="proc-a", procedure_name="Proc A", input_schema=None):
	return BoundProcedure(
		binding_name="AGPB-1",
		agent="agent-1",
		procedure="proc-a-v1",
		procedure_id=procedure_id,
		procedure_name=procedure_name,
		input_schema=input_schema or {"type": "object", "properties": {"x": {"type": "string"}}},
	)


class _Agent:
	name = "agent-1"


class TestListToolGroupsIncludesProcedures(unittest.TestCase):
	def test_procedures_get_their_own_group_not_mixed_with_atomic_tools(self):
		with (
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery.PermissionAwareToolRegistry, "get_allowed_tools", return_value=[
				_ToolDoc("send_email", description="Send an email.", service="gmail"),
			]),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[_bound()]),
		):
			groups = json.loads(lazy_discovery.handle_list_tool_groups(agent_name="agent-1"))

		by_service = {g["service"]: g for g in groups}
		self.assertIn("gmail", by_service)
		self.assertIn(lazy_discovery.PROCEDURE_GROUP_NAME, by_service)
		self.assertNotEqual(by_service["gmail"], by_service[lazy_discovery.PROCEDURE_GROUP_NAME])
		self.assertEqual(by_service[lazy_discovery.PROCEDURE_GROUP_NAME]["tool_count"], 1)

	def test_no_input_schema_anywhere_in_the_initial_listing(self):
		"""The entire point of lazy discovery: schemas never appear in list_tool_groups."""
		with (
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery.PermissionAwareToolRegistry, "get_allowed_tools", return_value=[]),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[_bound()]),
		):
			raw = lazy_discovery.handle_list_tool_groups(agent_name="agent-1")

		self.assertNotIn("input_schema", raw)
		self.assertNotIn("properties", raw)

	def test_no_procedure_group_when_agent_has_no_bindings(self):
		with (
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery.PermissionAwareToolRegistry, "get_allowed_tools", return_value=[]),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[]),
		):
			groups = json.loads(lazy_discovery.handle_list_tool_groups(agent_name="agent-1"))

		self.assertEqual(groups, [])


class TestDescribeProcedureGroup(unittest.TestCase):
	def test_describe_procedure_group_lists_bound_procedures_with_schema_deferred_still(self):
		bound = _bound()
		with (
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[bound]),
		):
			result = json.loads(
				lazy_discovery.handle_describe_tool_group(
					service=lazy_discovery.PROCEDURE_GROUP_NAME, agent_name="agent-1"
				)
			)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["tool_name"], "procedure__proc-a")
		# describe_tool_group's own contract (matches ordinary tools): no input_schema
		# key here either -- only load_tools returns parameters.
		self.assertNotIn("parameters", result[0])
		self.assertNotIn("input_schema", result[0])


class TestSearchToolsIncludesProcedures(unittest.TestCase):
	def test_search_matches_bound_procedure_by_name(self):
		bound = _bound(procedure_id="refund-check", procedure_name="Refund Eligibility Check")

		# handle_search_tools unconditionally imports
		# huf.ai.capability_discovery.actions at call time (even with zero allowed
		# tools) -- that module chain pulls in real frappe.model.document, which is
		# not importable standalone. Stub the module out so the *procedure* addition
		# under test here can be exercised without a bench; the atomic-tool search
		# path that actually calls search_app_actions is covered on a real bench by
		# test_lazy_tool_discovery.test_search_tools_only_covers_allowed_tools.
		fake_actions_module = types.ModuleType("huf.ai.capability_discovery.actions")
		fake_actions_module.search_app_actions = lambda *a, **k: []

		with (
			patch.dict(sys.modules, {"huf.ai.capability_discovery.actions": fake_actions_module}),
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery.PermissionAwareToolRegistry, "get_allowed_tools", return_value=[]),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[bound]),
		):
			matches = json.loads(lazy_discovery.handle_search_tools(query="refund", agent_name="agent-1"))

		self.assertEqual([m["tool_name"] for m in matches], ["procedure__refund-check"])
		self.assertEqual(matches[0]["service"], lazy_discovery.PROCEDURE_GROUP_NAME)


class TestLoadToolsProcedures(unittest.TestCase):
	def test_load_tools_accepts_bound_procedure_and_returns_full_schema(self):
		bound = _bound()
		state = {"version": 1, "scope": {}, "items": []}
		with (
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery.PermissionAwareToolRegistry, "get_allowed_tools", return_value=[]),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[bound]),
			patch.object(lazy_discovery, "_get_conversation_data", return_value=state),
			patch.object(lazy_discovery, "_set_conversation_data") as set_data,
		):
			result = json.loads(
				lazy_discovery.handle_load_tools(
					tool_names=["procedure__proc-a", "not-a-real-tool"],
					agent_name="agent-1",
					conversation_id="CONV-1",
				)
			)

		self.assertEqual(result["rejected"], ["not-a-real-tool"])
		accepted = {a["tool_name"]: a for a in result["accepted"]}
		self.assertIn("procedure__proc-a", accepted)
		self.assertEqual(accepted["procedure__proc-a"]["parameters"], bound.input_schema)
		set_data.assert_called_once()

	def test_load_tools_re_checks_permissions_not_trusting_prior_discovery(self):
		"""If the binding disappeared/became non-read-only since list_tool_groups was
		called, get_bound_procedures_for_agent (I8 re-check) returns [] and load_tools
		must reject the name outright -- I1: discovery can never widen permissions."""
		with (
			patch.object(lazy_discovery, "_resolve_agent_doc", return_value=_Agent()),
			patch.object(lazy_discovery.PermissionAwareToolRegistry, "get_allowed_tools", return_value=[]),
			patch.object(lazy_discovery, "get_bound_procedures_for_agent", return_value=[]),
		):
			result = json.loads(
				lazy_discovery.handle_load_tools(
					tool_names=["procedure__proc-a"], agent_name="agent-1", conversation_id="CONV-1"
				)
			)

		self.assertEqual(result["accepted"], [])
		self.assertEqual(result["rejected"], ["procedure__proc-a"])


if __name__ == "__main__":
	unittest.main()
