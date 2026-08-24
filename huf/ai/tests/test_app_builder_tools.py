# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for the App-builder additions to huf.ai.tools.builder — list_agents,
get_agent, list_apps, get_app, draft_app, update_app, install_app.

Follows the exact conventions of huf.ai.tests.test_builder_tools: the
_LazyModule import guard, capability-denial tests via patched frappe.get_roles,
and the two-phase preview/confirm shape (mocked for the read/discovery tools,
against the real DB for draft_app/install_app to also exercise
apps_loader.create_app_from_agent/install_app).

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_app_builder_tools
"""

from unittest.mock import patch

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


class TestAppBuilderCapability(IntegrationTestCase):
	"""Every new App-builder tool must refuse users without builder roles."""

	def _assert_denied(self, func, **kwargs):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(frappe.PermissionError, func, **kwargs)

	def test_list_agents_denied(self):
		self._assert_denied(builder.list_agents)

	def test_get_agent_denied(self):
		self._assert_denied(builder.get_agent, agent_name="X")

	def test_list_apps_denied(self):
		self._assert_denied(builder.list_apps)

	def test_get_app_denied(self):
		self._assert_denied(builder.get_app, app_id="x")

	def test_draft_app_denied(self):
		self._assert_denied(
			builder.draft_app, app_id="x", title="X", agent_name="Test Agent"
		)

	def test_update_app_denied(self):
		self._assert_denied(builder.update_app, app_id="x", title="New Title")

	def test_install_app_denied(self):
		self._assert_denied(builder.install_app, app_id="x")


class TestListAndGetAgent(IntegrationTestCase):
	def test_list_agents_respects_limit(self):
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch(
				"frappe.get_list",
				return_value=[{"agent_name": "A", "description": "", "disabled": 0, "is_system": 0}],
			),
		):
			result = builder.list_agents(limit=5)
		self.assertEqual(result["limit"], 5)
		self.assertEqual(len(result["agents"]), 1)

	def test_get_agent_excludes_instructions(self):
		fake_agent = type(
			"FakeAgent",
			(),
			{
				"agent_name": "Test Agent",
				"description": "desc",
				"provider": "Test Provider",
				"model": "test-model",
				"disabled": 0,
				"is_system": 0,
				"allow_chat": 1,
				"instructions": "SECRET PROMPT",
			},
		)()
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", return_value=fake_agent),
		):
			result = builder.get_agent("Test Agent")
		self.assertEqual(result["agent_name"], "Test Agent")
		self.assertNotIn("instructions", result)


class TestListAndGetApp(IntegrationTestCase):
	def test_list_apps_respects_limit(self):
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.has_permission", return_value=True),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"app_id": "x",
						"title": "X",
						"description": "",
						"route": "/apps/x",
						"category": "Other",
						"enabled": 0,
					}
				],
			),
		):
			result = builder.list_apps(limit=5)
		self.assertEqual(result["limit"], 5)
		self.assertEqual(len(result["apps"]), 1)


class TestDraftApp(IntegrationTestCase):
	"""draft_app against the real DB — creates a temp Agent to back the App."""

	AGENT_NAME = "Test App Builder Agent"
	APP_ID = "test-app-builder-app"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Agent", cls.AGENT_NAME):
			provider = frappe.db.get_value("AI Provider", {}, "name")
			model = frappe.db.get_value("AI Model", {}, "name")
			if provider and model:
				frappe.get_doc(
					{
						"doctype": "Agent",
						"agent_name": cls.AGENT_NAME,
						"provider": provider,
						"model": model,
						"instructions": "Test agent for App builder tests.",
						"prompt_mode": "Local",
						"disabled": 1,
					}
				).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		for app_id in (cls.APP_ID,):
			if frappe.db.exists("HUF App", app_id):
				frappe.delete_doc("HUF App", app_id, ignore_permissions=True, force=True)
		if frappe.db.exists("Agent", cls.AGENT_NAME):
			frappe.delete_doc("Agent", cls.AGENT_NAME, ignore_permissions=True, force=True)
		super().tearDownClass()

	def setUp(self):
		if not frappe.db.exists("Agent", self.AGENT_NAME):
			self.skipTest("No AI Provider/AI Model configured in this environment.")
		if frappe.db.exists("HUF App", self.APP_ID):
			frappe.delete_doc("HUF App", self.APP_ID, ignore_permissions=True, force=True)

	def test_preview_returns_confirm_required_without_mutating(self):
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			result = builder.draft_app(
				app_id=self.APP_ID,
				title="Test App",
				agent_name=self.AGENT_NAME,
				confirm=False,
			)
		self.assertTrue(result["confirm_required"])
		self.assertFalse(result["created"])
		self.assertEqual(result["diff"]["agent"], self.AGENT_NAME)
		self.assertFalse(frappe.db.exists("HUF App", self.APP_ID))

	def test_confirm_creates_record(self):
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			result = builder.draft_app(
				app_id=self.APP_ID,
				title="Test App",
				agent_name=self.AGENT_NAME,
				confirm=True,
			)
		self.assertTrue(result["created"])
		self.assertTrue(frappe.db.exists("HUF App", self.APP_ID))

	def test_rejects_unknown_agent(self):
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			self.assertRaises(
				frappe.ValidationError,
				builder.draft_app,
				app_id=self.APP_ID,
				title="Test App",
				agent_name="Does Not Exist Agent",
				confirm=True,
			)
		self.assertFalse(frappe.db.exists("HUF App", self.APP_ID))

	def test_install_app_idempotent_across_two_confirmed_calls(self):
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			builder.draft_app(
				app_id=self.APP_ID,
				title="Test App",
				agent_name=self.AGENT_NAME,
				confirm=True,
			)
			first = builder.install_app(self.APP_ID, confirm=True)
			second = builder.install_app(self.APP_ID, confirm=True)

		self.assertTrue(first["installed"])
		self.assertTrue(second["installed"])
		self.assertEqual(
			frappe.db.count("HUF App", filters={"app_id": self.APP_ID}), 1
		)

	def test_install_app_idempotent_across_preview_and_confirm_branches(self):
		"""Regression: tool-layer install_app idempotency across preview/confirm.

		The tool-layer install_app has its own confirm-preview branch that could
		theoretically diverge from the domain-service function's idempotency.
		This test validates that the preview (confirm=False) branch never mutates
		state, and confirm (confirm=True) calls remain idempotent even after
		interleaved preview calls, keeping HUF App record count at 1.
		"""
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			# Create and draft the app
			builder.draft_app(
				app_id=self.APP_ID,
				title="Test App",
				agent_name=self.AGENT_NAME,
				confirm=True,
			)

			# Preview: confirm=False should not mutate, should show not yet installed
			preview1 = builder.install_app(self.APP_ID, confirm=False)
			self.assertFalse(preview1["installed"])
			self.assertTrue(preview1["confirm_required"])
			self.assertFalse(preview1["already_installed"])
			self.assertEqual(
				frappe.db.count("HUF App", filters={"app_id": self.APP_ID}), 1,
				"preview call must not create new record"
			)

			# Confirm: confirm=True should install
			confirm1 = builder.install_app(self.APP_ID, confirm=True)
			self.assertTrue(confirm1["installed"])
			self.assertEqual(
				frappe.db.count("HUF App", filters={"app_id": self.APP_ID}), 1,
				"confirm call must not duplicate record"
			)

			# Preview again: should show already installed
			preview2 = builder.install_app(self.APP_ID, confirm=False)
			self.assertFalse(preview2["installed"])
			self.assertTrue(preview2["confirm_required"])
			self.assertTrue(preview2["already_installed"])
			self.assertEqual(
				frappe.db.count("HUF App", filters={"app_id": self.APP_ID}), 1,
				"preview after confirm must not create new record"
			)

			# Confirm again: should be idempotent
			confirm2 = builder.install_app(self.APP_ID, confirm=True)
			self.assertTrue(confirm2["installed"])
			self.assertEqual(
				frappe.db.count("HUF App", filters={"app_id": self.APP_ID}), 1,
				"second confirm must remain idempotent"
			)


class TestSetAppIconCapability(IntegrationTestCase):
	"""set_app_icon must refuse users without builder roles."""

	def _assert_denied(self, **kwargs):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(frappe.PermissionError, builder.set_app_icon, **kwargs)

	def test_set_app_icon_denied(self):
		self._assert_denied(
			app_id="test-app", source="path", value="/assets/icon.png"
		)


class TestSetAppIcon(IntegrationTestCase):
	"""set_app_icon validation and two-phase contract tests."""

	AGENT_NAME = "Test Icon Builder Agent"
	APP_ID = "test-icon-builder-app"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Agent", cls.AGENT_NAME):
			provider = frappe.db.get_value("AI Provider", {}, "name")
			model = frappe.db.get_value("AI Model", {}, "name")
			if provider and model:
				frappe.get_doc(
					{
						"doctype": "Agent",
						"agent_name": cls.AGENT_NAME,
						"provider": provider,
						"model": model,
						"instructions": "Test agent for icon builder tests.",
						"prompt_mode": "Local",
						"disabled": 1,
					}
				).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		for app_id in (cls.APP_ID,):
			if frappe.db.exists("HUF App", app_id):
				frappe.delete_doc("HUF App", app_id, ignore_permissions=True, force=True)
		if frappe.db.exists("Agent", cls.AGENT_NAME):
			frappe.delete_doc("Agent", cls.AGENT_NAME, ignore_permissions=True, force=True)
		super().tearDownClass()

	def setUp(self):
		if not frappe.db.exists("Agent", self.AGENT_NAME):
			self.skipTest("No AI Provider/AI Model configured in this environment.")
		if frappe.db.exists("HUF App", self.APP_ID):
			frappe.delete_doc("HUF App", self.APP_ID, ignore_permissions=True, force=True)
		# Create a test app to work with
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			builder.draft_app(
				app_id=self.APP_ID,
				title="Test App for Icon",
				agent_name=self.AGENT_NAME,
				confirm=True,
			)

	def test_set_app_icon_path_rejects_invalid_path(self):
		"""Paths must start with '/' and not contain URL schemes."""
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			# Path without leading slash
			self.assertRaises(
				frappe.ValidationError,
				builder.set_app_icon,
				app_id=self.APP_ID,
				source="path",
				value="assets/icon.png",
				confirm=False,
			)

	def test_set_app_icon_path_rejects_url_scheme(self):
		"""Paths must not contain URL schemes."""
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			# Path with URL scheme
			self.assertRaises(
				frappe.ValidationError,
				builder.set_app_icon,
				app_id=self.APP_ID,
				source="path",
				value="https://example.com/icon.png",
				confirm=False,
			)

	def test_set_app_icon_uploaded_rejects_nonexistent_file(self):
		"""File doc must exist."""
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			self.assertRaises(
				frappe.ValidationError,
				builder.set_app_icon,
				app_id=self.APP_ID,
				source="uploaded",
				value="nonexistent-file-id",
				confirm=False,
			)

	def test_set_app_icon_preview_does_not_mutate(self):
		"""preview (confirm=False) must not change the app's icon."""
		original_icon = frappe.db.get_value("HUF App", self.APP_ID, "icon") or ""

		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			result = builder.set_app_icon(
				app_id=self.APP_ID,
				source="path",
				value="/assets/new-icon.png",
				confirm=False,
			)

		# Check response shape
		self.assertFalse(result["set"])
		self.assertTrue(result["confirm_required"])

		# Check icon wasn't changed
		current_icon = frappe.db.get_value("HUF App", self.APP_ID, "icon") or ""
		self.assertEqual(current_icon, original_icon)


class TestResolveRecentResource(IntegrationTestCase):
	"""Tests for builder.resolve_recent_resource ("make that an App" resolution)."""

	def _make_conversation(self, conversation_data=None):
		conversation = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": f"resolve-recent-test-{frappe.generate_hash(length=6)}",
				"session_id": f"test-session-{frappe.generate_hash(length=10)}",
				"is_active": 1,
				"conversation_data": (
					frappe.as_json(conversation_data) if conversation_data is not None else None
				),
			}
		)
		conversation.insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"Agent Conversation", conversation.name, ignore_permissions=True, force=True
			)
		)
		return conversation.name

	def test_denied_without_builder_role(self):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(
				frappe.PermissionError,
				builder.resolve_recent_resource,
				resource_type="agent",
			)

	def test_returns_not_found_on_empty_conversation(self):
		conversation_id = self._make_conversation()
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			result = builder.resolve_recent_resource(
				resource_type="agent", conversation_id=conversation_id
			)
		self.assertFalse(result["found"])
		self.assertIn("No recent agent found", result["message"])

	def test_returns_not_found_with_no_conversation_id(self):
		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			result = builder.resolve_recent_resource(resource_type="app", conversation_id=None)
		self.assertFalse(result["found"])

	def test_returns_most_recent_matching_entry(self):
		conversation_data = {
			"_recent_resources": [
				{"type": "app", "name": "newest-app", "created_at": "2026-08-24 12:00:00"},
				{"type": "agent", "name": "newest-agent", "created_at": "2026-08-24 11:00:00"},
				{"type": "agent", "name": "older-agent", "created_at": "2026-08-24 10:00:00"},
			]
		}
		conversation_id = self._make_conversation(conversation_data)

		with patch("frappe.get_roles", return_value=BUILDER_ROLES):
			result = builder.resolve_recent_resource(
				resource_type="agent", conversation_id=conversation_id
			)

		self.assertTrue(result["found"])
		self.assertEqual(result["name"], "newest-agent")
		self.assertEqual(result["type"], "agent")
