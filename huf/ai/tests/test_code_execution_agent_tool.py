"""Security tests for exposing ``run_python`` (Code Execution) to agents.

Covers: type-map resolution, trusted ``agent_doc`` injection (model args
overridden), ``conversation``/``agent_run`` pinned from the run context, both
gates (offer-time ``_allows_code_execution`` and dispatch-time ``run_python``),
Guest refusal, and an idempotent seeder. The sandbox itself is never run.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_code_execution_agent_tool
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai import sdk_tools
from huf.ai.tools import invocation as tool_invocation
from huf.ai.tools.registry import PermissionAwareToolRegistry
from huf.ai.tools import code_execution
from huf.install import create_code_execution_tools

RUN_PYTHON_PATH = "huf.ai.tools.code_execution.run_python"


def _agent(**kw):
	base = {"doctype": "Agent", "name": "AG-1", "allow_code_execution": 1, "execution_profile": None}
	base.update(kw)
	return SimpleNamespace(**base)


class TestCodeExecutionResolution(FrappeTestCase):
	def test_type_map_has_code_execution(self):
		self.assertEqual(tool_invocation.TYPE_TO_FUNCTION_PATH.get("Code Execution"), RUN_PYTHON_PATH)

	def test_build_extra_args_injects_agent_doc(self):
		agent = _agent()
		extra = tool_invocation.build_extra_args({"types": "Code Execution", "agent_doc": agent})
		self.assertIs(extra["agent_doc"], agent)

	def test_build_extra_args_always_sets_agent_doc_key(self):
		# Even with no agent, the key is present so a model-supplied value is overwritten.
		extra = tool_invocation.build_extra_args({"types": "Code Execution"})
		self.assertIn("agent_doc", extra)
		self.assertIsNone(extra["agent_doc"])


class TestCodeExecutionArgPinning(FrappeTestCase):
	def _invoke(self, model_args, ctx, extra_args):
		captured = {}

		def fake_run_python(code, agent_doc, conversation=None, agent_run=None, **kwargs):
			captured.update(
				code=code, agent_doc=agent_doc, conversation=conversation, agent_run=agent_run, kwargs=kwargs
			)
			return {"ok": True}

		with patch.object(sdk_tools, "get_function_from_name", return_value=fake_run_python):
			tool = sdk_tools.create_function_tool(
				"run_python",
				"d",
				RUN_PYTHON_PATH,
				{"type": "object", "properties": {}},
				extra_args=extra_args,
				tool_type="Code Execution",
			)
		asyncio.run(tool.on_invoke_tool(ctx, json.dumps(model_args)))
		return captured

	def test_model_cannot_override_agent_doc_conversation_agent_run(self):
		trusted = _agent(name="TRUSTED")
		ctx = {"conversation_id": "CONV-REAL", "agent_run_id": "RUN-REAL", "agent_name": "TRUSTED"}
		got = self._invoke(
			{
				"code": "print(1)",
				"agent_doc": "VICTIM-AGENT",
				"conversation": "CONV-VICTIM",
				"agent_run": "RUN-VICTIM",
				"conversation_id": "CONV-VICTIM",
				"agent_run_id": "RUN-VICTIM",
			},
			ctx,
			{"agent_doc": trusted},
		)
		self.assertIs(got["agent_doc"], trusted)
		self.assertEqual(got["conversation"], "CONV-REAL")
		self.assertEqual(got["agent_run"], "RUN-REAL")

	def test_model_supplied_ids_dropped_when_context_has_none(self):
		got = self._invoke(
			{"code": "x", "conversation": "CONV-VICTIM", "agent_run": "RUN-VICTIM"},
			{},
			{"agent_doc": _agent()},
		)
		self.assertIsNone(got["conversation"])
		self.assertIsNone(got["agent_run"])


class TestCodeExecutionGates(FrappeTestCase):
	def test_dispatch_gate_site_switch_off(self):
		with patch.object(code_execution, "_is_site_enabled", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				code_execution.run_python("print(1)", agent_doc=_agent())

	def test_dispatch_gate_missing_capability(self):
		with (
			patch.object(code_execution, "_is_site_enabled", return_value=True),
			patch.object(code_execution, "has_capability", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				code_execution.run_python("print(1)", agent_doc=_agent())

	def test_dispatch_gate_agent_not_enabled_hallucinated_call(self):
		# A never-offered / hallucinated call reaches run_python for an agent
		# that has code execution off: refused with no audit row created.
		with (
			patch.object(code_execution, "_is_site_enabled", return_value=True),
			patch.object(code_execution, "has_capability", return_value=True),
			patch.object(code_execution.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				code_execution.run_python("print(1)", agent_doc=_agent(allow_code_execution=0))
			get_doc.assert_not_called()

	def test_offer_gate_blocks_without_capability_or_flag(self):
		tool = SimpleNamespace(types="Code Execution")
		with patch("huf.permissions.has_capability", return_value=False):
			self.assertFalse(PermissionAwareToolRegistry._allows_code_execution(tool, _agent(), "u@x.com"))
		with patch("huf.permissions.has_capability", return_value=True):
			self.assertFalse(
				PermissionAwareToolRegistry._allows_code_execution(
					tool, _agent(allow_code_execution=0), "u@x.com"
				)
			)
			self.assertFalse(PermissionAwareToolRegistry._allows_code_execution(tool, _agent(), "u@x.com"))

	def test_guest_refused_at_offer_and_dispatch(self):
		tool = SimpleNamespace(types="Code Execution", is_read_only=0, allowed_for_guest=0)
		self.assertFalse(PermissionAwareToolRegistry._can_use_tool(tool, "Guest"))
		with (
			patch.object(code_execution, "_is_site_enabled", return_value=True),
			patch.object(code_execution, "has_capability", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				code_execution.run_python("print(1)", agent_doc=_agent())

	def test_deterministic_path_refuses_code_execution(self):
		# Flows/procedures have no agent: caller-supplied agent_doc must never be honoured.
		doc = {
			"name": "x",
			"tool_name": "run_python",
			"types": "Code Execution",
			"function_path": None,
			"reference_doctype": None,
			"reference_report": None,
			"agent": None,
			"function_name": None,
			"allowed_for_guest": 0,
			"blocking": 0,
			"base_url": None,
		}
		with (
			patch.object(tool_invocation, "resolve_tool_doc", return_value=doc),
			patch.object(tool_invocation, "get_function_from_name") as getter,
		):
			res = asyncio.run(tool_invocation.invoke_tool("run_python", {"code": "1", "agent_doc": "A"}))
		self.assertFalse(res.success)
		self.assertTrue(res.denied)
		getter.assert_not_called()


class TestCodeExecutionSeeder(FrappeTestCase):
	def test_seeder_idempotent_and_schema_safe(self):
		create_code_execution_tools()
		create_code_execution_tools()
		self.assertTrue(frappe.db.exists("Agent Tool Type", "Code Execution"))
		names = frappe.get_all("Agent Tool Function", filters={"tool_name": "run_python"}, pluck="name")
		self.assertEqual(len(names), 1)
		doc = frappe.get_doc("Agent Tool Function", names[0])
		self.assertEqual(doc.types, "Code Execution")
		self.assertEqual(doc.function_path, RUN_PYTHON_PATH)
		self.assertFalse(doc.allowed_for_guest)
		fieldnames = {p.fieldname for p in doc.parameters}
		self.assertIn("code", fieldnames)
		for trusted in ("agent_doc", "conversation", "agent_run"):
			self.assertNotIn(trusted, fieldnames)
			self.assertNotIn(trusted, json.loads(doc.params or "{}").get("properties", {}))

	def test_after_migrate_registers_seeder(self):
		import inspect

		from huf import install

		self.assertIn("create_code_execution_tools()", inspect.getsource(install.after_migrate))
		self.assertIn("create_code_execution_tools()", inspect.getsource(install.after_install))
