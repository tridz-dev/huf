# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for Agent-level gating of Python code execution: ``allow_code_execution``
and ``execution_profile`` must both be set, the profile must be enabled, and
the acting user must hold ``code_execution.run`` before ``run_python``
dispatches anything.

Run with: bench --site <site> run-tests --app huf --module huf.huf.doctype.agent.test_agent

NOTE (Phase 7 verification): this file requires a live Frappe bench. It was
authored in an environment with NO bench available and has NOT been executed
yet — it py_compiles and its imports resolve, but its first real run is
pending. Do not treat presence in the tree as evidence of a passing run.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.tools.code_execution import run_python
from huf.install import create_huf_roles


class TestAgent(FrappeTestCase):
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
