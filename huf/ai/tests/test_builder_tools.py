# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for huf.ai.tools.builder — the hub builder tools.

Covers:
- capability gating: every mutating tool throws PermissionError for users
  without System Manager / Huf Manager roles
- create_huf_table: happy path wrapping the HUF Data Table API
- draft_agent: creates a disabled draft; warns when the provider has no key
- update_agent_prompt / attach_agent_tools / publish_agent: two-phase
  contract — no mutation without confirm=True
- publish_agent: refuses when the provider has no API key
- create_agent_tool: declarative-only creation; rejects function_path/base_url

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_builder_tools
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class _LazyModule:
    """Defer heavy app imports until first use.

    bench run-tests discovers (imports) test modules before frappe.init
    completes on some Frappe versions; importing huf.ai.tools.builder eagerly
    pulls tool_registry, whose module-level frappe.logger() call then crashes
    discovery.
    """

    def __init__(self, module_path):
        self._module_path = module_path

    def __getattr__(self, name):
        import importlib

        return getattr(importlib.import_module(self._module_path), name)


builder = _LazyModule("huf.ai.tools.builder")

BUILDER_ROLES = ["System Manager"]
MANAGER_ROLES = ["Huf Manager"]
DENIED_ROLES = ["Huf User"]


class _FakeAgent:
	"""Minimal stand-in for an Agent document."""

	def __init__(self, **kwargs):
		self.agent_name = kwargs.pop("agent_name", "Test Agent")
		self.name = self.agent_name
		self.provider = kwargs.pop("provider", "Test Provider")
		self.model = kwargs.pop("model", "test-model")
		self.instructions = kwargs.pop("instructions", "old instructions")
		self.agent_prompt = kwargs.pop("agent_prompt", "")
		self.prompt_mode = kwargs.pop("prompt_mode", "Local")
		self.disabled = kwargs.pop("disabled", 1)
		self.is_system = kwargs.pop("is_system", 0)
		self.agent_tool = kwargs.pop("agent_tool", [])
		self.saved = False

	def get(self, field, default=None):
		return self.__dict__.get(field, default)

	def set(self, field, value):
		setattr(self, field, value)

	def save(self):
		self.saved = True


def _provider_doc(api_key="sk-test"):
	doc = MagicMock()
	doc.get_password.return_value = api_key
	return doc


def _get_doc_router(agent=None, provider_key="sk-test", captured=None):
	"""Route frappe.get_doc calls to fakes based on the first argument.

	New-document dict payloads are recorded in ``captured`` (if given) and
	answered with a MagicMock carrying an ``insert`` method.
	"""

	def _get_doc(first, *args, **kwargs):
		if first == "Agent":
			return agent
		if first == "AI Provider":
			return _provider_doc(provider_key)
		if isinstance(first, dict):
			if captured is not None:
				captured.append(first)
			new_doc = MagicMock()
			new_doc.name = first.get("agent_name") or first.get("tool_name")
			return new_doc
		return MagicMock()

	return _get_doc


class TestBuilderCapability(FrappeTestCase):
	"""Every builder tool must refuse users without builder roles."""

	def _assert_denied(self, func, **kwargs):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(frappe.PermissionError, func, **kwargs)

	def test_create_huf_table_denied(self):
		self._assert_denied(builder.create_huf_table, table_name="X", fields=[])

	def test_draft_agent_denied(self):
		self._assert_denied(
			builder.draft_agent,
			agent_name="A",
			provider="P",
			model="M",
			instructions="i",
		)

	def test_update_agent_prompt_denied(self):
		self._assert_denied(builder.update_agent_prompt, agent_name="A", instructions="i")

	def test_attach_agent_tools_denied(self):
		self._assert_denied(builder.attach_agent_tools, agent_name="A", tool_names=[])

	def test_publish_agent_denied(self):
		self._assert_denied(builder.publish_agent, agent_name="A")

	def test_create_agent_tool_denied(self):
		self._assert_denied(builder.create_agent_tool, tool_name="t", description="d")

	def test_huf_manager_allowed(self):
		"""Huf Manager passes the capability gate (fails later on missing fixtures)."""
		with (
			patch("frappe.get_roles", return_value=MANAGER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", side_effect=_get_doc_router(agent=_FakeAgent())),
		):
			result = builder.publish_agent("Test Agent", confirm=False)
			self.assertTrue(result["confirm_required"])


class TestCreateHufTable(FrappeTestCase):
	def test_happy_path(self):
		create_result = {
			"success": True,
			"data": {"name": "HDT-0001", "table_name": "Feedback", "doctype_name": "HF Feedback"},
		}
		schema = {"name": "HDT-0001", "doctype_name": "HF Feedback", "fields": []}
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch(
				"huf.huf.doctype.huf_data_table.api.create_data_table", return_value=create_result
			) as mock_create,
			patch("huf.huf.doctype.huf_data_table.api.get_table_schema", return_value=schema),
		):
			result = builder.create_huf_table(
				table_name="Feedback",
				fields=[{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
				description="Customer feedback",
				confirm=True,
			)

		self.assertTrue(result["created"])
		self.assertEqual(result["doctype"], "HF Feedback")
		self.assertEqual(result["schema"], schema)
		mock_create.assert_called_once()


class TestDraftAgent(FrappeTestCase):
	def _draft(self, provider_key="sk-test"):
		captured = []

		def _exists_router(doctype, name=None):
			# The Agent itself must NOT exist (happy path); providers/models do.
			if doctype == "Agent":
				return False
			return True

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", side_effect=_exists_router),
			patch(
				"huf.ai.tools.builder._sanitize_for_doctype",
				side_effect=lambda doctype, data: data,
			),
			patch(
				"frappe.get_doc",
				side_effect=_get_doc_router(provider_key=provider_key, captured=captured),
			),
		):
			result = builder.draft_agent(
				agent_name="New Agent",
				provider="Test Provider",
				model="test-model",
				instructions="Be helpful.",
				confirm=True,
			)
		return result, captured

	def test_happy_path_creates_disabled_draft(self):
		result, captured = self._draft()
		self.assertTrue(result["created"])
		self.assertEqual(result["agent"], "New Agent")
		self.assertTrue(result["disabled"])
		self.assertNotIn("warning", result)

		payload = captured[0]
		self.assertEqual(payload["disabled"], 1)
		self.assertEqual(payload["prompt_mode"], "Local")
		self.assertEqual(payload["instructions"], "Be helpful.")

	def test_draft_warns_without_provider_key(self):
		result, _ = self._draft(provider_key="")
		self.assertTrue(result["created"])
		self.assertIn("warning", result)
		self.assertIn("no API key", result["warning"])

	def test_duplicate_agent_rejected(self):
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.db.exists", return_value=True),
		):
			# First exists() call is for the Agent itself -> duplicate
			self.assertRaises(
				frappe.ValidationError,
				builder.draft_agent,
				agent_name="New Agent",
				provider="Test Provider",
				model="test-model",
				instructions="x",
			)

	def test_missing_provider_rejected(self):
		def _exists(doctype, name=None):
			return doctype != "AI Provider"

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.db.exists", side_effect=_exists),
		):
			self.assertRaises(
				frappe.ValidationError,
				builder.draft_agent,
				agent_name="New Agent",
				provider="Nope",
				model="test-model",
				instructions="x",
			)


class TestUpdateAgentPrompt(FrappeTestCase):
	def _run(self, agent, roles=BUILDER_ROLES, **kwargs):
		with (
			patch("frappe.get_roles", return_value=roles),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", side_effect=_get_doc_router(agent=agent)),
		):
			return builder.update_agent_prompt(agent.agent_name, **kwargs)

	def test_preview_does_not_save(self):
		agent = _FakeAgent()
		result = self._run(agent, instructions="new instructions", confirm=False)

		self.assertFalse(result["updated"])
		self.assertTrue(result["confirm_required"])
		self.assertEqual(
			result["diff"]["instructions"], {"old": "old instructions", "new": "new instructions"}
		)
		self.assertFalse(agent.saved)
		self.assertEqual(agent.instructions, "old instructions")

	def test_confirm_applies_and_saves(self):
		agent = _FakeAgent()
		result = self._run(agent, instructions="new instructions", confirm=True)

		self.assertTrue(result["updated"])
		self.assertTrue(agent.saved)
		self.assertEqual(agent.instructions, "new instructions")

	def test_agent_prompt_switches_to_template_mode(self):
		agent = _FakeAgent()
		result = self._run(agent, agent_prompt="Some Template", confirm=False)

		self.assertEqual(result["diff"]["agent_prompt"]["new"], "Some Template")
		self.assertEqual(result["diff"]["prompt_mode"], {"old": "Local", "new": "Template"})

	def test_noop_when_nothing_changes(self):
		agent = _FakeAgent()
		result = self._run(agent, instructions="old instructions", confirm=True)

		self.assertFalse(result["updated"])
		self.assertFalse(agent.saved)

	def test_system_agent_locked_for_huf_manager(self):
		agent = _FakeAgent(is_system=1)
		self.assertRaises(
			frappe.PermissionError,
			self._run,
			agent,
			roles=MANAGER_ROLES,
			instructions="new",
		)

	def test_system_agent_editable_for_system_manager(self):
		agent = _FakeAgent(is_system=1)
		result = self._run(agent, roles=BUILDER_ROLES, instructions="new", confirm=True)
		self.assertTrue(result["updated"])


class TestAttachAgentTools(FrappeTestCase):
	def _run(self, agent, **kwargs):
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", side_effect=_get_doc_router(agent=agent)),
		):
			return builder.attach_agent_tools(agent.agent_name, **kwargs)

	def test_preview_shows_current_vs_proposed(self):
		agent = _FakeAgent(agent_tool=[SimpleNamespace(tool="run_flow")])
		result = self._run(agent, tool_names=["run_flow", "get_list"], confirm=False)

		self.assertFalse(result["updated"])
		self.assertEqual(result["diff"]["agent_tool"]["old"], ["run_flow"])
		self.assertEqual(result["diff"]["agent_tool"]["new"], ["run_flow", "get_list"])
		self.assertFalse(agent.saved)

	def test_confirm_replaces_tool_rows(self):
		agent = _FakeAgent(agent_tool=[SimpleNamespace(tool="run_flow")])
		result = self._run(agent, tool_names=["get_list"], confirm=True)

		self.assertTrue(result["updated"])
		self.assertTrue(agent.saved)
		self.assertEqual([row["tool"] for row in agent.agent_tool], ["get_list"])

	def test_accepts_json_string_tool_names(self):
		agent = _FakeAgent()
		result = self._run(agent, tool_names='["get_list"]', confirm=False)
		self.assertEqual(result["diff"]["agent_tool"]["new"], ["get_list"])

	def test_unknown_tool_rejected(self):
		agent = _FakeAgent()
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch(
				"frappe.db.exists",
				side_effect=lambda doctype, name=None: doctype == "Agent",
			),
			patch("frappe.get_doc", side_effect=_get_doc_router(agent=agent)),
		):
			self.assertRaises(
				frappe.ValidationError,
				builder.attach_agent_tools,
				agent.agent_name,
				tool_names=["missing_tool"],
			)
		self.assertFalse(agent.saved)


class TestPublishAgent(FrappeTestCase):
	def _run(self, agent, provider_key="sk-test", **kwargs):
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", side_effect=_get_doc_router(agent=agent, provider_key=provider_key)),
		):
			return builder.publish_agent(agent.agent_name, **kwargs)

	def test_preview_does_not_save(self):
		agent = _FakeAgent(disabled=1)
		result = self._run(agent, confirm=False)

		self.assertFalse(result["published"])
		self.assertTrue(result["confirm_required"])
		self.assertEqual(result["diff"]["disabled"], {"old": 1, "new": 0})
		self.assertFalse(agent.saved)
		self.assertEqual(agent.disabled, 1)

	def test_confirm_publishes(self):
		agent = _FakeAgent(disabled=1)
		result = self._run(agent, confirm=True)

		self.assertTrue(result["published"])
		self.assertTrue(result["changed"])
		self.assertEqual(agent.disabled, 0)
		self.assertTrue(agent.saved)

	def test_refuses_without_provider_key(self):
		agent = _FakeAgent(disabled=1)
		result = self._run(agent, provider_key="", confirm=True)

		self.assertFalse(result["published"])
		self.assertIn("no API key", result["error"])
		self.assertIn("remediation", result)
		self.assertFalse(agent.saved)
		self.assertEqual(agent.disabled, 1)

	def test_already_published_is_noop(self):
		agent = _FakeAgent(disabled=0)
		result = self._run(agent, confirm=True)

		self.assertTrue(result["published"])
		self.assertFalse(result["changed"])
		self.assertFalse(agent.saved)


class TestCreateAgentTool(FrappeTestCase):
	def _run(self, exists=False, **kwargs):
		captured = []

		def _exists(doctype, name=None):
			if doctype == "Agent Tool Function":
				return exists
			return True  # Agent Tool Type "Builder" assumed present

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", side_effect=_exists),
			patch(
				"huf.ai.tools.builder._sanitize_for_doctype",
				side_effect=lambda doctype, data: dict(data),
			),
			patch("frappe.get_doc", side_effect=_get_doc_router(captured=captured)),
		):
			return builder.create_agent_tool(confirm=True, **kwargs), captured

	def test_happy_path_declarative_only(self):
		result, captured = self._run(
			tool_name="my_tool",
			description="Does a thing",
			parameters=[{"fieldname": "query", "type": "string", "required": 1}],
		)

		self.assertTrue(result["created"])
		self.assertEqual(result["tool_name"], "my_tool")
		self.assertTrue(result["requires_admin_completion"])

		payload = captured[0]
		self.assertEqual(payload["types"], "Custom Function")
		self.assertNotIn("function_path", payload)
		self.assertNotIn("base_url", payload)
		self.assertEqual(payload["parameters"][0]["fieldname"], "query")
		self.assertEqual(payload["parameters"][0]["label"], "Query")

	def test_rejects_function_path(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			tool_name="my_tool",
			description="d",
			function_path="os.system",
		)

	def test_rejects_base_url(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			tool_name="my_tool",
			description="d",
			base_url="https://evil.example.com",
		)

	def test_duplicate_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			exists=True,
			tool_name="my_tool",
			description="d",
		)
