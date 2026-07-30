# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch


def _get_permission_query_conditions():
	"""Defer controller import until test time (bench run-tests discovers test
	modules before frappe.init completes on some Frappe versions)."""
	from huf.huf.doctype.agent.agent import get_permission_query_conditions

	return get_permission_query_conditions

NON_MANAGER_ROLES = ["Huf User"]
MANAGER_ROLES = ["System Manager"]


def _any_model_and_provider():
    rows = frappe.get_all("AI Model", fields=["name", "provider"], limit=1)
    if not rows:
        return None, None
    return rows[0].name, rows[0].provider


class TestAgentSaveRoundtrip(IntegrationTestCase):
	"""Regression guard: basic insert/reload/delete must not silently fail.

	This catches the most common regression pattern where an unrelated merge
	breaks the agent save path (missing required field, broken hook, etc.)
	without any obvious error in the UI.
	"""

	def setUp(self):
		self._names = []
		rows = frappe.get_all("AI Model", fields=["name", "provider"], limit=1)
		if not rows:
			self.skipTest("no AI Model records on this site")
		self.model = rows[0].name
		self.provider = rows[0].provider

	def tearDown(self):
		for name in self._names:
			try:
				frappe.db.delete("Agent", {"name": name})
			except Exception:
				pass
		frappe.db.commit()

	def test_agent_insert_and_reload(self):
		doc = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "__regression_probe__",
			"provider": self.provider,
			"model": self.model,
			"instructions": "regression probe",
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		reloaded = frappe.get_doc("Agent", doc.name)
		self.assertEqual(reloaded.agent_name, "__regression_probe__")
		self.assertEqual(reloaded.provider, self.provider)
		self.assertEqual(reloaded.model, self.model)

	def test_agent_with_child_tables_saves(self):
		"""Regression guard: agents with empty child-table fields must save cleanly.

		Catches schema drift where a child table definition change causes 'Table
		field ... does not exist' or similar errors on save without the user seeing
		an obvious message.
		"""
		doc = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "__regression_table_probe__",
			"provider": self.provider,
			"model": self.model,
			"instructions": "table regression probe",
			"agent_tool": [],
			"agent_mcp_server": [],
			"agent_knowledge": [],
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		reloaded = frappe.get_doc("Agent", doc.name)
		self.assertEqual(reloaded.agent_name, "__regression_table_probe__")
		self.assertIsInstance(reloaded.agent_tool, list)
		self.assertIsInstance(reloaded.agent_mcp_server, list)
		self.assertIsInstance(reloaded.agent_knowledge, list)

	def test_agent_field_update_persists(self):
		doc = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "__regression_update_probe__",
			"provider": self.provider,
			"model": self.model,
			"instructions": "initial instructions",
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		doc.instructions = "updated instructions"
		doc.save(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value("Agent", doc.name, "instructions"),
			"updated instructions",
		)


class TestAgent(IntegrationTestCase):
    def test_system_agent_delete_guard(self):
        """Deleting an is_system agent should be blocked outside install/migrate/uninstall."""
        agent = frappe.new_doc("Agent")
        agent.agent_name = "__test_system_agent__"
        agent.is_system = 1

        with self.assertRaises(frappe.ValidationError):
            agent.on_trash()

    def test_system_agent_rename_guard(self):
        """Renaming an is_system agent should be blocked outside install/migrate/uninstall."""
        agent = frappe.new_doc("Agent")
        agent.agent_name = "__test_system_agent__"
        agent.is_system = 1

        with self.assertRaises(frappe.ValidationError):
            agent.before_rename("__test_system_agent__", "__renamed_system_agent__")


class TestSystemAgentLocking(IntegrationTestCase):
    """Guards for system-agent (is_system=1) locking: immutability and list hiding.

    DB-backed: real inserts/saves so the guards run through the full controller
    path (in-memory new_doc construction is unreliable across test harnesses).
    """

    SYSTEM = "__test_system_lock__"
    NORMAL = "__test_normal_lock__"

    def setUp(self):
        self._cleanup()
        model, provider = _any_model_and_provider()
        if not model:
            self.skipTest("no AI Model records on this site")
        self.model = model
        self.provider = provider
        frappe.get_doc(
            {
                "doctype": "Agent",
                "agent_name": self.SYSTEM,
                "is_system": 1,
                "provider": provider,
                "model": model,
                "instructions": "original instructions",
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        # Raw delete: on_trash blocks system-agent deletion by design.
        for name in (self.SYSTEM, self.NORMAL):
            if frappe.db.exists("Agent", name):
                frappe.db.delete("Agent", {"name": name})

    def test_protected_field_edit_blocked_for_non_manager(self):
        """Non-System-Managers cannot edit protected fields on a system agent."""
        agent = frappe.get_doc("Agent", self.SYSTEM)
        agent.instructions = "tampered instructions"

        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent.save(ignore_permissions=True)

    def test_protected_field_edit_allowed_for_system_manager(self):
        """System Managers can still edit protected fields on a system agent."""
        agent = frappe.get_doc("Agent", self.SYSTEM)
        agent.instructions = "manager update"

        with patch("frappe.get_roles", return_value=MANAGER_ROLES):
            agent.save(ignore_permissions=True)

        self.assertEqual(
            frappe.db.get_value("Agent", self.SYSTEM, "instructions"), "manager update"
        )

    def test_tool_table_edit_blocked_for_non_manager(self):
        """Changing the agent_tool child table is also locked for non-managers."""
        tools = frappe.get_all("Agent Tool Function", pluck="name", limit=1)
        if not tools:
            self.skipTest("no Agent Tool Function records on this site")

        agent = frappe.get_doc("Agent", self.SYSTEM)
        agent.append("agent_tool", {"tool": tools[0]})

        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent.save(ignore_permissions=True)

    def test_is_system_flip_blocked_for_non_manager(self):
        """Regression guard: non-managers cannot flip is_system on an existing agent."""
        frappe.get_doc(
            {
                "doctype": "Agent",
                "agent_name": self.NORMAL,
                "is_system": 0,
                "provider": self.provider,
                "model": self.model,
                "instructions": "normal agent instructions",
            }
        ).insert(ignore_permissions=True)

        agent = frappe.get_doc("Agent", self.NORMAL)
        agent.is_system = 1

        with patch("frappe.get_roles", return_value=NON_MANAGER_ROLES):
            with self.assertRaises(frappe.ValidationError):
                agent.save(ignore_permissions=True)

    def test_permission_query_conditions_hide_system_agents(self):
        """Non-System-Manager list queries exclude system agents."""
        conditions = _get_permission_query_conditions()("Guest")
        self.assertIsNotNone(conditions)
        self.assertIn("`tabAgent`.is_system = 0", conditions)

    def test_permission_query_conditions_unrestricted_for_system_manager(self):
        """System Managers still see all agents (no conditions)."""
        if "System Manager" not in frappe.get_roles():
            self.skipTest("test session user is not a System Manager")
        self.assertIsNone(_get_permission_query_conditions()(frappe.session.user))


# Python execution gating tests from PR #358.
import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tools.code_execution import run_python
from huf.install import create_huf_roles


class TestAgentCodeExecution(IntegrationTestCase):
	"""Agent code-execution gate tests (dispatch-level has_permission checks)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_huf_roles()
		cls._orig_kill_switch = frappe.conf.get("huf_python_execution_enabled")
		frappe.conf["huf_python_execution_enabled"] = True

	@classmethod
	def tearDownClass(cls):
		if cls._orig_kill_switch is None:
			frappe.conf.pop("huf_python_execution_enabled", None)
		else:
			frappe.conf["huf_python_execution_enabled"] = cls._orig_kill_switch
		super().tearDownClass()

	def setUp(self):
		self._users = []
		self._agents = []
		self._profiles = []
		self._calls = []
		self.provider = self._ensure_provider()
		self.model = self._ensure_model(self.provider)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._calls:
			self._delete("Agent Tool Call", name)
		for name in self._agents:
			self._delete("Agent", name)
		for name in self._profiles:
			self._delete("Execution Profile", name)
		for name in self._users:
			self._delete("User", name)
		frappe.db.commit()

	def _delete(self, doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	def _ensure_provider(self):
		existing = frappe.db.get_value("AI Provider", {}, "name")
		if existing:
			return existing
		provider = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Test Provider {frappe.generate_hash(length=6)}",
				"api_key": "test-key-not-used",
				"provider_brand": "openai",
			}
		)
		provider.insert(ignore_permissions=True)
		return provider.name

	def _ensure_model(self, provider):
		existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
		if existing:
			return existing
		model = frappe.get_doc(
			{
				"doctype": "AI Model",
				"model_name": f"test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		model.insert(ignore_permissions=True)
		return model.name

	def _make_user(self, roles=()):
		email = f"huf-exec-test-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ExecTest",
				"send_welcome_email": 0,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_profile(self, approval_mode="Auto Approve", disabled=0):
		profile = frappe.get_doc(
			{
				"doctype": "Execution Profile",
				"profile_name": f"test-profile-{frappe.generate_hash(length=8)}",
				"approval_mode": approval_mode,
				"filesystem_policy": "None",
				"disabled": disabled,
			}
		)
		profile.insert(ignore_permissions=True)
		self._profiles.append(profile.name)
		return profile.name

	def _make_agent(self, allow_code_execution=0, execution_profile=None):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"test-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test code execution agent instructions",
				"provider": self.provider,
				"model": self.model,
				"allow_code_execution": allow_code_execution,
				"execution_profile": execution_profile,
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	# -- gate tests ---------------------------------------------------------------

	def test_dispatch_denied_when_agent_flag_off(self):
		profile = self._make_profile()
		agent = self._make_agent(allow_code_execution=0, execution_profile=profile)
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_python("print(1)", agent_doc=agent)

	def test_dispatch_denied_when_no_execution_profile(self):
		agent = self._make_agent(allow_code_execution=1, execution_profile=None)
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_python("print(1)", agent_doc=agent)

	def test_dispatch_denied_when_profile_disabled(self):
		profile = self._make_profile(disabled=1)
		agent = self._make_agent(allow_code_execution=1, execution_profile=profile)
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_python("print(1)", agent_doc=agent)

	def test_dispatch_denied_without_capability(self):
		profile = self._make_profile()
		agent = self._make_agent(allow_code_execution=1, execution_profile=profile)
		# A user with no Huf role holds no capabilities at all.
		user = self._make_user(roles=())
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			run_python("print(1)", agent_doc=agent)

	def test_dispatch_allowed_when_fully_enabled(self):
		profile = self._make_profile()
		agent = self._make_agent(allow_code_execution=1, execution_profile=profile)
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)

		result = run_python("print('agent gate ok')", agent_doc=agent)
		self.assertTrue(result.get("success"))
		self.assertEqual(result.get("status"), "Queued")
		self.assertTrue(result.get("code_ref"))

		call_name = result.get("agent_tool_call")
		self._calls.append(call_name)
		call = frappe.get_doc("Agent Tool Call", call_name)
		self.assertEqual(call.execution_profile, profile)
		self.assertTrue(call.execution_profile_snapshot)
		self.assertTrue(call.code_ref)
		# In test mode frappe.enqueue runs inline; either way the row must not be
		# stuck at the pre-dispatch "Started" state.
		self.assertIn(call.status, ("Queued", "Completed"))
		if call.status == "Completed":
			self.assertEqual(call.exit_status, "Ok")
