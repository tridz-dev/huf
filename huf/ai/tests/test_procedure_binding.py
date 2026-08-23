# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.graph.procedure_binding (T-31).

Standalone-first: frappe is faked with a hand-written double (never a bare MagicMock --
this file's own `PermissionError` alias trick and the `.throw()`/`.get_all()` shape mirror
`huf.ai.tests.test_graph_permissions._FrappeDouble`), so these tests pass without a bench
and are re-run unmodified against a real one. Covers:

  * get_binding_cap() default + configured + malformed-config fallback.
  * get_bound_procedures_for_agent(): I8 re-check (non-read-only procedures are dropped
    even if somehow enabled), and the hard per-agent cap (extra enabled bindings beyond
    the cap are dropped, not silently exposed).
  * invoke_bound_procedure() always calls run_agent_procedure_run -- never
    execute_procedure directly -- and pins a fresh Agent Procedure Run to bound.procedure.

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_binding
"""

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

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph import procedure_binding
from huf.ai.graph.procedure_binding import (
	DEFAULT_BINDING_CAP,
	BoundProcedure,
	build_procedure_binding_tools,
	get_binding_cap,
	get_bound_procedures_for_agent,
	invoke_bound_procedure,
)


class _Row(dict):
	"""frappe.get_all()/get_value(as_dict=True) rows support both row.x and row["x"]."""

	def __getattr__(self, item):
		try:
			return self[item]
		except KeyError:
			return None


class _FrappeDouble:
	"""Minimal stand-in for the ``frappe`` module as ``procedure_binding.py`` uses it.

	Plain object, not a MagicMock-with-affordances -- see the module-level rationale in
	test_graph_permissions.py for why (identical behaviour with or without a bench).
	"""

	def __init__(self, *, conf=None, bindings=None, procedures=None):
		self.conf = conf or {}
		self._bindings = bindings or []
		self._procedures = procedures or {}
		self.inserted_docs = []

	# -- logging: no-ops that never raise --
	def logger(self, *_a, **_k):
		return _NullLogger()

	def get_all(self, doctype, filters=None, fields=None, order_by=None):
		if doctype != "Agent Procedure Binding":
			raise AssertionError(doctype)
		rows = [r for r in self._bindings if r["agent"] == filters["agent"] and r["enabled"] == 1]
		rows.sort(key=lambda r: (-(r.get("priority") or 0), r.get("modified") or ""))
		return [_Row(r) for r in rows]

	class db:
		pass

	def get_doc(self, spec):
		doc = _FakeRunDoc(spec)
		self.inserted_docs.append(doc)
		return doc

	def get_cached_doc(self, doctype, name):
		return _Row({"name": name, "doctype": doctype})

	def get_traceback(self):
		return ""


class _NullLogger:
	def warning(self, *a, **k):
		pass

	def debug(self, *a, **k):
		pass


class _FakeRunDoc:
	def __init__(self, spec):
		self.__dict__.update(spec)
		self.name = "AGPR-TEST-0001"
		self.inserted = False

	def insert(self, ignore_permissions=False):
		self.inserted = True


class TestGetBindingCap(unittest.TestCase):
	def test_default_when_unconfigured(self):
		with patch.object(procedure_binding, "frappe", _FrappeDouble(conf={})):
			self.assertEqual(get_binding_cap(), DEFAULT_BINDING_CAP)

	def test_configured_value_is_used(self):
		with patch.object(
			procedure_binding, "frappe", _FrappeDouble(conf={"agent_procedure_binding_max_per_agent": 3})
		):
			self.assertEqual(get_binding_cap(), 3)

	def test_malformed_config_falls_back_to_default(self):
		with patch.object(
			procedure_binding,
			"frappe",
			_FrappeDouble(conf={"agent_procedure_binding_max_per_agent": "not-a-number"}),
		):
			self.assertEqual(get_binding_cap(), DEFAULT_BINDING_CAP)

	def test_non_positive_config_falls_back_to_default(self):
		with patch.object(
			procedure_binding, "frappe", _FrappeDouble(conf={"agent_procedure_binding_max_per_agent": 0})
		):
			self.assertEqual(get_binding_cap(), DEFAULT_BINDING_CAP)


def _binding_row(name, agent, procedure, procedure_id, priority=0, modified="2026-01-01"):
	return {
		"name": name,
		"agent": agent,
		"procedure": procedure,
		"procedure_id": procedure_id,
		"enabled": 1,
		"priority": priority,
		"modified": modified,
	}


class TestGetBoundProceduresForAgent(unittest.TestCase):
	def _double(self, *, conf=None, bindings, procedures):
		fake = _FrappeDouble(conf=conf or {}, bindings=bindings, procedures=procedures)

		def get_value(doctype, name, fields, as_dict=True):
			if doctype != "Agent Procedure":
				raise AssertionError(doctype)
			row = procedures.get(name)
			return _Row(row) if row else None

		fake.db = types.SimpleNamespace(get_value=get_value)
		return fake

	def test_empty_when_no_bindings(self):
		fake = self._double(bindings=[], procedures={})
		with patch.object(procedure_binding, "frappe", fake):
			self.assertEqual(get_bound_procedures_for_agent("agent-1"), [])

	def test_read_only_procedure_is_exposed(self):
		bindings = [_binding_row("AGPB-1", "agent-1", "proc-a-v1", "proc-a")]
		procedures = {
			"proc-a-v1": {
				"procedure_id": "proc-a",
				"procedure_name": "Proc A",
				"is_read_only": 1,
				"input_schema": '{"type": "object", "properties": {"x": {"type": "string"}}}',
			}
		}
		fake = self._double(bindings=bindings, procedures=procedures)
		with patch.object(procedure_binding, "frappe", fake):
			resolved = get_bound_procedures_for_agent("agent-1")

		self.assertEqual(len(resolved), 1)
		self.assertIsInstance(resolved[0], BoundProcedure)
		self.assertEqual(resolved[0].procedure_id, "proc-a")
		self.assertEqual(resolved[0].input_schema["properties"]["x"]["type"], "string")

	def test_write_procedure_is_never_exposed_even_if_enabled(self):
		"""I8, re-checked at read time regardless of what saved the binding as enabled."""
		bindings = [_binding_row("AGPB-1", "agent-1", "proc-w-v1", "proc-w")]
		procedures = {
			"proc-w-v1": {
				"procedure_id": "proc-w",
				"procedure_name": "Proc W",
				"is_read_only": 0,
				"input_schema": "{}",
			}
		}
		fake = self._double(bindings=bindings, procedures=procedures)
		with patch.object(procedure_binding, "frappe", fake):
			resolved = get_bound_procedures_for_agent("agent-1")

		self.assertEqual(resolved, [])

	def test_per_agent_cap_drops_lowest_priority_bindings(self):
		bindings = [
			_binding_row("AGPB-1", "agent-1", "proc-a-v1", "proc-a", priority=10),
			_binding_row("AGPB-2", "agent-1", "proc-b-v1", "proc-b", priority=5),
			_binding_row("AGPB-3", "agent-1", "proc-c-v1", "proc-c", priority=1),
		]
		procedures = {
			f"proc-{c}-v1": {
				"procedure_id": f"proc-{c}",
				"procedure_name": f"Proc {c.upper()}",
				"is_read_only": 1,
				"input_schema": "{}",
			}
			for c in ("a", "b", "c")
		}
		fake = self._double(conf={"agent_procedure_binding_max_per_agent": 2}, bindings=bindings, procedures=procedures)
		with patch.object(procedure_binding, "frappe", fake):
			resolved = get_bound_procedures_for_agent("agent-1")

		self.assertEqual([b.procedure_id for b in resolved], ["proc-a", "proc-b"])

	def test_missing_procedure_is_skipped_not_fatal(self):
		bindings = [_binding_row("AGPB-1", "agent-1", "proc-missing-v1", "proc-missing")]
		fake = self._double(bindings=bindings, procedures={})
		with patch.object(procedure_binding, "frappe", fake):
			resolved = get_bound_procedures_for_agent("agent-1")

		self.assertEqual(resolved, [])


class TestInvokeBoundProcedure(unittest.TestCase):
	def test_always_goes_through_run_agent_procedure_run(self):
		"""Never calls execute_procedure directly -- run lock / I1 / I5 must all fire."""
		bound = BoundProcedure(
			binding_name="AGPB-1",
			agent="agent-1",
			procedure="proc-a-v1",
			procedure_id="proc-a",
			procedure_name="Proc A",
			input_schema={"type": "object"},
		)

		fake_frappe = _FrappeDouble()

		fake_runtime = types.ModuleType("huf.ai.graph.procedure_runtime")
		calls = []

		class _Outcome:
			# Mirrors ProcedureOutcome's status constants, which invoke_bound_procedure
			# compares against directly.
			SUCCESS = "success"
			FAILED = "failed"
			NOT_APPLICABLE = "not_applicable"

			def __init__(self):
				self.status = "success"
				self.output = {"ok": True}
				self.error = None

		def fake_run_agent_procedure_run(run_name, *, agent_doc=None):
			calls.append((run_name, agent_doc))
			return _Outcome()

		fake_runtime.run_agent_procedure_run = fake_run_agent_procedure_run
		# invoke_bound_procedure also imports ProcedureOutcome (added when the fallback
		# protocol was wired in), so the stub module has to provide it or the import fails.
		fake_runtime.ProcedureOutcome = _Outcome

		with patch.object(procedure_binding, "frappe", fake_frappe), \
			patch.dict(sys.modules, {"huf.ai.graph.procedure_runtime": fake_runtime}):
			result = invoke_bound_procedure(bound, {"x": "1"}, agent_run_id="AGR-1")

		self.assertEqual(len(calls), 1)
		run_name, _agent_doc = calls[0]
		self.assertEqual(run_name, "AGPR-TEST-0001")
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["output"], {"ok": True})

		# The Agent Procedure Run created and inserted was pinned to bound.procedure.
		self.assertEqual(len(fake_frappe.inserted_docs), 1)
		inserted = fake_frappe.inserted_docs[0]
		self.assertTrue(inserted.inserted)
		self.assertEqual(inserted.procedure, "proc-a-v1")
		self.assertEqual(inserted.agent_run, "AGR-1")


class TestBuildProcedureBindingTools(unittest.TestCase):
	def test_no_bindings_returns_empty_list(self):
		fake = _FrappeDouble()
		with patch.object(procedure_binding, "frappe", fake), \
			patch.object(procedure_binding, "get_bound_procedures_for_agent", return_value=[]):
			agent = types.SimpleNamespace(name="agent-1")
			self.assertEqual(build_procedure_binding_tools(agent), [])

	def test_builds_one_tool_per_bound_procedure_with_schema_as_params(self):
		try:
			import agents
		except ImportError:
			self.skipTest("openai-agents (the `agents` package) is not installed in this environment")

		bound = BoundProcedure(
			binding_name="AGPB-1",
			agent="agent-1",
			procedure="proc-a-v1",
			procedure_id="proc-a",
			procedure_name="Proc A",
			input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
		)
		with patch.object(procedure_binding, "get_bound_procedures_for_agent", return_value=[bound]):
			agent = types.SimpleNamespace(name="agent-1")
			tools = build_procedure_binding_tools(agent, agent_run_id="AGR-1")

		self.assertEqual(len(tools), 1)
		tool = tools[0]
		self.assertEqual(tool.name, "procedure__proc-a")
		self.assertEqual(tool.params_json_schema, bound.input_schema)


if __name__ == "__main__":
	unittest.main()
