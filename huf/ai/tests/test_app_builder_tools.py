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
