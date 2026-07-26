"""
Shared-directory → ``Agent Context Artifact`` write-back tests (plan-doc
Verification item 5).

An execution under a Shared-Directory-policy profile writes a file; after the
run the new file must appear as an ``Agent Context Artifact`` linked to the
same conversation, and the shared directory must stay within
``execution_shared_dir_limit_mb``. A run that leaves the directory over cap
fails with ``limits_hit`` and writes back nothing.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_code_execution_artifacts

NOTE (Phase 7 verification): this file requires a live Frappe bench. It was
authored in an environment with NO bench available and has NOT been executed
yet — it py_compiles and its imports resolve, but its first real run is
pending. Do not treat presence in the tree as evidence of a passing run.
"""
import json
import shutil
import unittest

import frappe

from huf.ai.tools.code_execution import _shared_dir_for_conversation, run_python
from huf.install import create_huf_roles


class TestCodeExecutionArtifacts(unittest.TestCase):
	"""Artifact write-back + shared-directory cap enforcement."""

	@classmethod
	def setUpClass(cls):
		create_huf_roles()
		cls._orig_kill_switch = frappe.conf.get("huf_python_execution_enabled")
		frappe.conf["huf_python_execution_enabled"] = True

	@classmethod
	def tearDownClass(cls):
		if cls._orig_kill_switch is None:
			frappe.conf.pop("huf_python_execution_enabled", None)
		else:
			frappe.conf["huf_python_execution_enabled"] = cls._orig_kill_switch

	def setUp(self):
		self._users = []
		self._agents = []
		self._profiles = []
		self._calls = []
		self._conversations = []
		self._artifacts = []
		self._files = []
		self.provider = self._ensure_provider()
		self.model = self._ensure_model(self.provider)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._artifacts:
			self._delete("Agent Context Artifact", name)
		for name in self._files:
			self._delete("File", name)
		for name in self._calls:
			self._delete("Agent Tool Call", name)
		for name in self._conversations:
			self._delete("Agent Conversation", name)
			# The shared dir lives outside the DB; remove it explicitly.
			try:
				shutil.rmtree(_shared_dir_for_conversation(name), ignore_errors=True)
			except Exception:
				pass
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

	def _make_profile(self):
		profile = frappe.get_doc(
			{
				"doctype": "Execution Profile",
				"profile_name": f"test-profile-{frappe.generate_hash(length=8)}",
				"approval_mode": "Auto Approve",
				"filesystem_policy": "Shared Directory",
			}
		)
		profile.insert(ignore_permissions=True)
		self._profiles.append(profile.name)
		return profile.name

	def _make_agent(self, execution_profile, shared_dir_limit_mb=10):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"test-agent-{frappe.generate_hash(length=8)}",
				"provider": self.provider,
				"model": self.model,
				"allow_code_execution": 1,
				"execution_profile": execution_profile,
				"execution_shared_dir_limit_mb": shared_dir_limit_mb,
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	def _make_conversation(self, agent):
		conversation = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"agent": agent.name,
				"title": f"artifact-test-{frappe.generate_hash(length=6)}",
				"session_id": f"test-session-{frappe.generate_hash(length=10)}",
				"is_active": 1,
			}
		)
		conversation.insert(ignore_permissions=True)
		self._conversations.append(conversation.name)
		return conversation

	def _run_and_get_call(self, code, agent, conversation):
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		result = run_python(code, agent_doc=agent, conversation=conversation)
		call_name = result.get("agent_tool_call")
		self.assertTrue(call_name)
		self._calls.append(call_name)
		return frappe.get_doc("Agent Tool Call", call_name)

	def _artifacts_for(self, conversation_name):
		rows = frappe.get_all(
			"Agent Context Artifact",
			filters={"conversation": conversation_name, "artifact_type": "File"},
			fields=["name", "payload_file", "context_policy"],
		)
		for row in rows:
			if row.name not in self._artifacts:
				self._artifacts.append(row.name)
		return rows

	@staticmethod
	def _usage(call):
		usage = call.resource_usage
		if isinstance(usage, str):
			usage = json.loads(usage)
		return usage or {}

	# -- write-back PoC ---------------------------------------------------------------

	def test_written_file_appears_as_conversation_artifact(self):
		profile = self._make_profile()
		agent = self._make_agent(profile, shared_dir_limit_mb=10)
		conversation = self._make_conversation(agent)

		code = (
			"with open('analysis-output.csv', 'w') as f:\n"
			"\tf.write('col_a,col_b\\n1,2\\n3,4\\n')\n"
			"print('csv written')\n"
		)
		call = self._run_and_get_call(code, agent, conversation)

		self.assertEqual(call.status, "Completed", call.error_message)
		self.assertEqual(call.exit_status, "Ok")

		artifacts = self._artifacts_for(conversation.name)
		self.assertEqual(len(artifacts), 1, "exactly one new artifact for the written file")
		payload_file = artifacts[0].get("payload_file")
		self.assertTrue(payload_file, "artifact must carry an attached file")

		file_name = frappe.db.get_value("File", {"file_url": payload_file}, "name")
		self.assertTrue(file_name, "payload_file must resolve to a File record")
		self._files.append(file_name)
		file_doc = frappe.get_doc("File", file_name)
		with open(file_doc.get_full_path(), "rb") as fh:
			self.assertEqual(fh.read(), b"col_a,col_b\n1,2\n3,4\n")

		usage = self._usage(call)
		self.assertEqual(usage.get("artifacts_written"), 1)
		self.assertLessEqual(usage.get("shared_dir_bytes", 0), 10 * 1024 * 1024)

	# -- cap enforcement -----------------------------------------------------------------

	def test_over_cap_output_fails_without_writeback(self):
		profile = self._make_profile()
		agent = self._make_agent(profile, shared_dir_limit_mb=1)
		conversation = self._make_conversation(agent)

		# A single 2MB file breaches the 1MB directory cap (but not the fixed
		# 50MB per-file rlimit, so the run itself completes).
		code = (
			"with open('too-big.bin', 'wb') as f:\n"
			"\tf.write(b'x' * (2 * 1024 * 1024))\n"
			"print('big file written')\n"
		)
		call = self._run_and_get_call(code, agent, conversation)

		self.assertEqual(call.status, "Failed")
		self.assertEqual(call.limits_hit, 1)
		self.assertIn("cap", (call.error_message or "").lower())
		self.assertEqual(self._artifacts_for(conversation.name), [], "no artifacts on cap breach")

	# -- fail-closed without a conversation ------------------------------------------------

	def test_shared_directory_without_conversation_fails_closed(self):
		profile = self._make_profile()
		agent = self._make_agent(profile)

		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		result = run_python("print('no conversation')", agent_doc=agent)
		call_name = result.get("agent_tool_call")
		self._calls.append(call_name)
		call = frappe.get_doc("Agent Tool Call", call_name)
		self.assertEqual(call.status, "Failed")
		self.assertIn("conversation", (call.error_message or "").lower())


if __name__ == "__main__":
	unittest.main()
