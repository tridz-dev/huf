# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for huf.ai.tools.builder — the hub builder tools.

Covers:
- capability gating: every mutating tool throws PermissionError for users
  without System Manager / Huf Manager roles
- create_huf_table: happy path wrapping the HUF Data Table API
- list_table_rows / add_table_row / update_table_row / delete_table_row:
  happy path against a real temp table, plus the two-phase contract
  (no write without confirm=True)
- draft_agent: creates a disabled draft; warns when the provider has no key
- update_agent_prompt / attach_agent_tools / publish_agent: two-phase
  contract — no mutation without confirm=True
- publish_agent: refuses when the provider has no API key
- create_agent_tool: declarative document tools bound to a reference_doctype;
  rejects Custom Function, function_path/base_url, and unknown doctypes

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_builder_tools
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase


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


class TestBuilderCapability(IntegrationTestCase):
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
		self._assert_denied(
			builder.create_agent_tool,
			tool_name="t",
			description="d",
			types="Create Document",
			reference_doctype="ToDo",
		)

	def test_list_table_rows_denied(self):
		self._assert_denied(builder.list_table_rows, table_name="X")

	def test_add_table_row_denied(self):
		self._assert_denied(builder.add_table_row, table_name="X", data={"a": 1})

	def test_update_table_row_denied(self):
		self._assert_denied(builder.update_table_row, table_name="X", row_name="1", data={"a": 1})

	def test_delete_table_row_denied(self):
		self._assert_denied(builder.delete_table_row, table_name="X", row_name="1")

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


class TestCreateHufTable(IntegrationTestCase):
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


class TestDraftAgent(IntegrationTestCase):
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

	def test_draft_is_chat_enabled_by_default(self):
		"""Hub-built agents must appear in chat pickers (allow_chat=1)."""
		result, captured = self._draft()
		self.assertEqual(captured[0]["allow_chat"], 1)
		self.assertTrue(result["allow_chat"])

	def test_allow_chat_string_coercion(self):
		"""allow_chat="false" (string) must not create a chat-enabled agent."""
		captured = []

		def _exists_router(doctype, name=None):
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
				side_effect=_get_doc_router(provider_key="sk-test", captured=captured),
			),
		):
			result = builder.draft_agent(
				agent_name="Headless Agent",
				provider="Test Provider",
				model="test-model",
				instructions="x",
				allow_chat="false",
				confirm=True,
			)
		self.assertEqual(captured[0]["allow_chat"], 0)
		self.assertFalse(result["allow_chat"])

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


class TestUpdateAgentPrompt(IntegrationTestCase):
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

	def test_non_system_agent_editable_for_builder_with_write_permission(self):
		agent = _FakeAgent(is_system=0)
		result = self._run(agent, roles=MANAGER_ROLES, instructions="new", confirm=True)
		self.assertTrue(result["updated"])

	def test_builder_without_agent_write_permission_denied(self):
		"""Builder capability alone is not enough — Agent write permission is required."""
		agent = _FakeAgent(is_system=0)
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=False),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", side_effect=_get_doc_router(agent=agent)),
		):
			self.assertRaises(
				frappe.PermissionError,
				builder.update_agent_prompt,
				agent.agent_name,
				instructions="new",
			)
		self.assertFalse(agent.saved)


class TestAttachAgentTools(IntegrationTestCase):
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


class TestPublishAgent(IntegrationTestCase):
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


class TestCreateAgentTool(IntegrationTestCase):
	"""create_agent_tool against the real DB (runs as Administrator).

	Uses a temp huf data table so parameter validation runs against a real
	dynamic DocType with a Select field.
	"""

	TABLE_NAME = "Test Builder Tool Params"
	DOCTYPE_NAME = f"HF {TABLE_NAME}"
	TOOL_NAMES = (
		"test_add_table_row_tool",
		"test_list_table_rows_tool",
		"test_dropped_params_tool",
		"test_duplicate_tool",
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from huf.huf.doctype.huf_data_table.api import create_data_table

		if not frappe.db.exists("Huf Data Table", {"table_name": cls.TABLE_NAME}):
			create_data_table(
				table_name=cls.TABLE_NAME,
				fields=[
					{"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1},
					{"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Open\nClosed"},
				],
			)
		# Clean leftovers from interrupted previous runs.
		for tool_name in cls.TOOL_NAMES:
			if frappe.db.exists("Agent Tool Function", tool_name):
				frappe.delete_doc("Agent Tool Function", tool_name, force=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		from huf.huf.doctype.huf_data_table.api import delete_data_table

		for tool_name in cls.TOOL_NAMES:
			if frappe.db.exists("Agent Tool Function", tool_name):
				frappe.delete_doc("Agent Tool Function", tool_name, force=True)
		registry = frappe.db.get_value("Huf Data Table", {"table_name": cls.TABLE_NAME}, "name")
		if registry:
			try:
				delete_data_table(registry)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDownClass()

	def test_happy_path_two_phase(self):
		preview = builder.create_agent_tool(
			tool_name="test_add_table_row_tool",
			description="Add a row to the test table",
			types="Create Document",
			reference_doctype=self.DOCTYPE_NAME,
			parameters=[{"fieldname": "title", "type": "string", "required": 1}],
		)
		self.assertFalse(preview["created"])
		self.assertTrue(preview["confirm_required"])
		self.assertEqual(preview["diff"]["payload"]["types"], "Create Document")
		self.assertEqual(preview["diff"]["payload"]["reference_doctype"], self.DOCTYPE_NAME)
		self.assertFalse(frappe.db.exists("Agent Tool Function", "test_add_table_row_tool"))

		result = builder.create_agent_tool(
			tool_name="test_add_table_row_tool",
			description="Add a row to the test table",
			types="Create Document",
			reference_doctype=self.DOCTYPE_NAME,
			parameters=[{"fieldname": "title", "type": "string", "required": 1}],
			confirm=True,
		)
		self.assertTrue(result["created"])
		self.assertEqual(result["tool_name"], "test_add_table_row_tool")
		self.assertEqual(result["dropped_params"], [])
		self.assertIn("attach_agent_tools", result["message"])

		doc = frappe.get_doc("Agent Tool Function", "test_add_table_row_tool")
		self.assertEqual(doc.types, "Create Document")
		self.assertEqual(doc.reference_doctype, self.DOCTYPE_NAME)
		self.assertFalse(doc.function_path)
		self.assertEqual([p.fieldname for p in doc.parameters], ["title"])

	def test_custom_function_rejected(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			builder.create_agent_tool(
				tool_name="test_add_table_row_tool",
				description="d",
				types="Custom Function",
				reference_doctype=self.DOCTYPE_NAME,
				confirm=True,
			)
		self.assertIn("not supported", str(ctx.exception))
		self.assertIn("declarative document tools", str(ctx.exception))
		self.assertFalse(frappe.db.exists("Agent Tool Function", "test_add_table_row_tool"))

	def test_function_path_rejected(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			builder.create_agent_tool(
				tool_name="test_add_table_row_tool",
				description="d",
				types="Create Document",
				reference_doctype=self.DOCTYPE_NAME,
				function_path="os.system",
				confirm=True,
			)
		self.assertIn("function_path", str(ctx.exception))
		self.assertFalse(frappe.db.exists("Agent Tool Function", "test_add_table_row_tool"))

	def test_missing_or_bogus_reference_doctype_rejected(self):
		for bogus in ("", "No Such Doctype"):
			with self.assertRaises(frappe.ValidationError) as ctx:
				builder.create_agent_tool(
					tool_name="test_add_table_row_tool",
					description="d",
					types="Create Document",
					reference_doctype=bogus,
					confirm=True,
				)
			self.assertIn("does not exist", str(ctx.exception))

	def test_select_param_options_autofilled(self):
		result = builder.create_agent_tool(
			tool_name="test_list_table_rows_tool",
			description="List rows filtered by status",
			types="Get List",
			reference_doctype=self.DOCTYPE_NAME,
			parameters=[{"fieldname": "status", "type": "string"}],
			confirm=True,
		)
		self.assertTrue(result["created"])

		doc = frappe.get_doc("Agent Tool Function", result["tool_name"])
		self.assertEqual(doc.parameters[0].fieldname, "status")
		self.assertEqual(doc.parameters[0].options, "Open\nClosed")

	def test_unknown_field_param_dropped(self):
		result = builder.create_agent_tool(
			tool_name="test_dropped_params_tool",
			description="Add a row",
			types="Create Document",
			reference_doctype=self.DOCTYPE_NAME,
			parameters=[
				{"fieldname": "title", "type": "string"},
				{"fieldname": "not_a_field", "type": "string"},
			],
			confirm=True,
		)
		self.assertTrue(result["created"])
		self.assertEqual(result["dropped_params"], ["not_a_field"])

		doc = frappe.get_doc("Agent Tool Function", result["tool_name"])
		self.assertEqual([p.fieldname for p in doc.parameters], ["title"])

	def test_duplicate_rejected(self):
		builder.create_agent_tool(
			tool_name="test_duplicate_tool",
			description="d",
			types="Get List",
			reference_doctype=self.DOCTYPE_NAME,
			confirm=True,
		)
		self.assertRaises(
			frappe.ValidationError,
			builder.create_agent_tool,
			tool_name="test_duplicate_tool",
			description="d",
			types="Get List",
			reference_doctype=self.DOCTYPE_NAME,
			confirm=True,
		)


class TestTableRowTools(IntegrationTestCase):
	"""Row-level tools against a real temp huf data table (runs as Administrator)."""

	TABLE_NAME = "Test Builder Rows"
	DOCTYPE_NAME = f"HF {TABLE_NAME}"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from huf.huf.doctype.huf_data_table.api import create_data_table

		if not frappe.db.exists("Huf Data Table", {"table_name": cls.TABLE_NAME}):
			create_data_table(
				table_name=cls.TABLE_NAME,
				fields=[
					{"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1},
					{"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Open\nClosed"},
				],
			)
			frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		from huf.huf.doctype.huf_data_table.api import delete_data_table

		registry = frappe.db.get_value("Huf Data Table", {"table_name": cls.TABLE_NAME}, "name")
		if registry:
			try:
				delete_data_table(registry)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDownClass()

	def _count(self):
		return frappe.db.count(self.DOCTYPE_NAME)

	def test_add_row_two_phase(self):
		before = self._count()
		preview = builder.add_table_row(self.TABLE_NAME, {"title": "first", "status": "Open"})
		self.assertFalse(preview["created"])
		self.assertTrue(preview["confirm_required"])
		self.assertEqual(preview["diff"]["data"]["title"], "first")
		self.assertEqual(self._count(), before)

		result = builder.add_table_row(self.TABLE_NAME, {"title": "first", "status": "Open"}, confirm=True)
		self.assertTrue(result["created"])
		self.assertEqual(self._count(), before + 1)
		self.assertEqual(frappe.db.get_value(self.DOCTYPE_NAME, result["row"], "status"), "Open")

	def test_add_row_drops_unknown_fields(self):
		result = builder.add_table_row(
			self.TABLE_NAME, {"title": "clean", "not_a_field": "x"}, confirm=True
		)
		self.assertTrue(result["created"])
		self.assertNotIn("not_a_field", result["diff"]["data"])

	def test_add_row_accepts_json_string_data(self):
		preview = builder.add_table_row(self.TABLE_NAME, '{"title": "json", "status": "Open"}')
		self.assertEqual(preview["diff"]["data"]["title"], "json")

	def test_list_rows(self):
		row = builder.add_table_row(self.TABLE_NAME, {"title": "listed", "status": "Open"}, confirm=True)
		result = builder.list_table_rows(self.TABLE_NAME, filters={"status": "Open"})
		self.assertEqual(result["doctype"], self.DOCTYPE_NAME)
		self.assertGreaterEqual(result["total"], 1)
		self.assertIn(row["row"], [r["name"] for r in result["rows"]])

		filtered = builder.list_table_rows(self.TABLE_NAME, filters={"status": "Closed"})
		self.assertNotIn(row["row"], [r["name"] for r in filtered["rows"]])

	def test_update_row_two_phase(self):
		row = builder.add_table_row(self.TABLE_NAME, {"title": "before", "status": "Open"}, confirm=True)

		preview = builder.update_table_row(self.TABLE_NAME, row["row"], {"status": "Closed"})
		self.assertFalse(preview["updated"])
		self.assertTrue(preview["confirm_required"])
		self.assertEqual(preview["diff"]["status"], {"old": "Open", "new": "Closed"})
		self.assertEqual(frappe.db.get_value(self.DOCTYPE_NAME, row["row"], "status"), "Open")

		result = builder.update_table_row(self.TABLE_NAME, row["row"], {"status": "Closed"}, confirm=True)
		self.assertTrue(result["updated"])
		self.assertEqual(frappe.db.get_value(self.DOCTYPE_NAME, row["row"], "status"), "Closed")

	def test_update_missing_row_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			builder.update_table_row,
			self.TABLE_NAME,
			"no-such-row",
			{"status": "Closed"},
		)

	def test_delete_row_two_phase(self):
		row = builder.add_table_row(self.TABLE_NAME, {"title": "doomed", "status": "Open"}, confirm=True)

		preview = builder.delete_table_row(self.TABLE_NAME, row["row"])
		self.assertFalse(preview["deleted"])
		self.assertTrue(preview["confirm_required"])
		self.assertTrue(frappe.db.exists(self.DOCTYPE_NAME, row["row"]))

		result = builder.delete_table_row(self.TABLE_NAME, row["row"], confirm=True)
		self.assertTrue(result["deleted"])
		self.assertFalse(frappe.db.exists(self.DOCTYPE_NAME, row["row"]))

	def test_delete_missing_row_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			builder.delete_table_row,
			self.TABLE_NAME,
			"no-such-row",
		)

	def test_unknown_table_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			builder.list_table_rows,
			"No Such Table",
		)

	def test_confirm_string_coercion(self):
		"""LLMs send confirm as a JSON string — "false" must preview, "true" must write."""
		before = self._count()
		preview = builder.add_table_row(
			self.TABLE_NAME, {"title": "str-false", "status": "Open"}, confirm="false"
		)
		self.assertFalse(preview["created"])
		self.assertTrue(preview["confirm_required"])
		self.assertEqual(self._count(), before)

		result = builder.add_table_row(
			self.TABLE_NAME, {"title": "str-true", "status": "Open"}, confirm="true"
		)
		self.assertTrue(result["created"])
		self.assertEqual(self._count(), before + 1)

	def test_create_existing_table_returns_already_exists(self):
		"""Creating over an existing table must not throw — returns schema for recovery."""
		result = builder.create_huf_table(
			self.TABLE_NAME,
			fields=[{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
			confirm=True,
		)
		self.assertFalse(result["created"])
		self.assertTrue(result["already_exists"])
		self.assertEqual(result["table"], self.TABLE_NAME)
		self.assertEqual(result["doctype"], self.DOCTYPE_NAME)
		self.assertIn("schema", result)
		self.assertIn("already exists", result["message"])


class TestAsBool(IntegrationTestCase):
	def test_truthy_strings(self):
		for value in ("true", "True", "TRUE", "1", "yes", "YES", 1, True):
			self.assertTrue(builder._as_bool(value), value)

	def test_falsy_values(self):
		for value in ("false", "False", "0", "no", "", "nope", 0, False, None):
			self.assertFalse(builder._as_bool(value), value)


class TestListProviderOptions(IntegrationTestCase):
	def _run(self):
		def _get_all(doctype, filters=None, pluck=None, order_by=None, **kwargs):
			if doctype == "AI Provider":
				return ["Keyed Provider", "Plain Provider"]
			return ["test-model", "text-embedding-3-small"]

		def _get_doc(doctype, name=None, *args, **kwargs):
			return _provider_doc("sk-super-secret" if name == "Keyed Provider" else "")

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_all", side_effect=_get_all),
			patch("frappe.get_doc", side_effect=_get_doc),
		):
			return builder.list_provider_options()

	def test_configured_flags_and_models(self):
		result = self._run()

		providers = {p["name"]: p for p in result["providers"]}
		self.assertTrue(providers["Keyed Provider"]["configured"])
		self.assertFalse(providers["Plain Provider"]["configured"])
		self.assertEqual(
			providers["Keyed Provider"]["models"], ["test-model", "text-embedding-3-small"]
		)

	def test_suggested_is_first_configured_provider_chat_model(self):
		result = self._run()
		# text-embedding-3-small is a non-chat model and must be skipped.
		self.assertEqual(
			result["suggested"], {"provider": "Keyed Provider", "model": "test-model"}
		)

	def test_no_key_material_in_result(self):
		import json

		result = self._run()
		self.assertNotIn("sk-super-secret", json.dumps(result, default=str))

	def test_denied_without_builder_role(self):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(frappe.PermissionError, builder.list_provider_options)


ask_user_mod = _LazyModule("huf.ai.tools.ask_user")


class TestAskUser(IntegrationTestCase):
	def _run(self, **kwargs):
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			return ask_user_mod.ask_user(**kwargs)

	def test_bad_kind_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			question="Pick one?",
			kind="dropdown",
		)

	def test_missing_question_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			question="",
			kind="input",
		)

	def test_choice_kind_requires_options(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			question="Pick one?",
			kind="single_choice",
		)

	def test_valid_payload_returns_fenced_block(self):
		import json

		result = self._run(
			question="Which provider?",
			kind="single_choice",
			options=[
				{"id": "openai", "label": "OpenAI", "icon": "Bot"},
				{"id": "gemini", "label": "Gemini", "description": "Google"},
			],
			note="You can change this later.",
		)

		self.assertTrue(result["block"].startswith("```ask-user\n"))
		self.assertTrue(result["block"].endswith("\n```"))
		payload = json.loads(result["block"][len("```ask-user\n") : -len("\n```")])
		self.assertEqual(payload, result["ask_user"])
		self.assertEqual(payload["kind"], "single_choice")
		self.assertEqual(payload["options"][0]["icon"], "Bot")
		self.assertTrue(payload["allow_free_text"])
		self.assertEqual(payload["note"], "You can change this later.")
		self.assertIn("verbatim", result["instruction"])

	def test_invalid_icon_dropped_with_warning(self):
		result = self._run(
			question="Pick one?",
			kind="single_choice",
			options=[
				{"id": "a", "label": "A", "icon": "NotARealIcon"},
				{"id": "b", "label": "B", "icon": "Check"},
			],
		)

		options = {o["id"]: o for o in result["ask_user"]["options"]}
		self.assertNotIn("icon", options["a"])
		self.assertEqual(options["b"]["icon"], "Check")
		self.assertIn("NotARealIcon", result["warning"])

	def test_options_accept_json_string(self):
		result = self._run(
			question="Sure?",
			kind="yes_no",
			options='[{"id": "y", "label": "Yes"}]',
		)
		self.assertEqual(result["ask_user"]["options"], [{"id": "y", "label": "Yes"}])

	def test_allow_free_text_string_coercion(self):
		result = self._run(question="Name?", kind="input", allow_free_text="false")
		self.assertFalse(result["ask_user"]["allow_free_text"])

	def test_password_requires_secure_target(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			question="Enter the provider key",
			kind="password",
		)

	def test_password_payload_contains_request_metadata_only(self):
		with patch(
			"huf.ai.tools.ask_user.create_secret_request",
			return_value={
				"request_id": "opaque-request",
				"conversation_id": "conv-1",
				"target": {"type": "provider_api_key", "provider_name": "OpenAI"},
				"target_label": "API key for OpenAI",
				"expires_in": 600,
			},
		):
			result = self._run(
				question="Enter the provider key",
				kind="password",
				secure_target={"type": "provider_api_key", "provider_name": "OpenAI"},
				conversation_id="conv-1",
			)

		self.assertEqual(result["ask_user"]["kind"], "password")
		self.assertFalse(result["ask_user"]["allow_free_text"])
		self.assertNotIn("secret", result["block"])
		self.assertIn("opaque-request", result["block"])

	def test_secure_target_rejected_for_normal_kind(self):
		self.assertRaises(
			frappe.ValidationError,
			self._run,
			question="Name?",
			kind="input",
			secure_target={"type": "provider_api_key", "provider_name": "OpenAI"},
		)

	def test_denied_without_builder_role(self):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(
				frappe.PermissionError,
				ask_user_mod.ask_user,
				question="Hi?",
				kind="input",
			)


sdk_tools = _LazyModule("huf.ai.sdk_tools")


class TestMergeRunContext(IntegrationTestCase):
	"""BUG-1 regression: run-context injection must not clobber explicit LLM args."""

	def test_args_json_agent_name_wins(self):
		args = {"agent_name": "car search"}
		ctx = {
			"agent_name": "Hub Orchestrator",
			"conversation_id": "conv-1",
			"agent_run_id": "run-1",
		}
		merged = sdk_tools._merge_run_context(args, ctx)

		self.assertEqual(merged["agent_name"], "car search")
		self.assertEqual(merged["conversation_id"], "conv-1")
		self.assertEqual(merged["agent_run_id"], "run-1")

	def test_ctx_value_injected_when_absent(self):
		merged = sdk_tools._merge_run_context({}, {"agent_name": "Hub Orchestrator"})
		self.assertEqual(merged["agent_name"], "Hub Orchestrator")

	def test_blank_llm_value_is_overridden_by_ctx(self):
		"""A key present but EMPTY must not block injection.

		This was a plain setdefault, which only fills a missing key. Models
		routinely emit ids they cannot know as "" - observed live: gemini sent
		{"conversation_id": ""} to list_document_artifacts, setdefault kept the
		empty string, and the tool failed with "'conversation_id' is required"
		while the run context held the real id the whole time. Every
		context-injected tool was exposed, not just the document ones.
		"""
		ctx = {"conversation_id": "conv-1", "agent_run_id": "run-1", "agent_name": "Real Agent"}

		for blank in ("", "   ", None):
			merged = sdk_tools._merge_run_context({"conversation_id": blank}, ctx)
			self.assertEqual(merged["conversation_id"], "conv-1", f"blank={blank!r}")

		# A real value the model supplied still wins.
		merged = sdk_tools._merge_run_context({"conversation_id": "conv-explicit"}, ctx)
		self.assertEqual(merged["conversation_id"], "conv-explicit")

	def test_sdk_toolcontext_wrapping(self):
		ctx = SimpleNamespace(context={"agent_name": "Hub Orchestrator"})
		merged = sdk_tools._merge_run_context({"agent_name": "explicit"}, ctx)
		self.assertEqual(merged["agent_name"], "explicit")

	def test_none_ctx_is_noop(self):
		args = {"agent_name": "explicit"}
		merged = sdk_tools._merge_run_context(args, None)
		self.assertEqual(merged, {"agent_name": "explicit"})
