"""
Tests for the Agent Execution Approval primitive (plan-doc Verification item 4).

Covers: ``Ask Every Time`` parks the dispatch (Pending approval, no enqueue);
``approve_execution`` enqueues impersonating the ORIGINAL requester (never the
approver); ``reject_execution`` finalizes the audit row with no enqueue;
``Never Allow`` rejects synchronously with no approval row; an expired
approval lazily transitions to Expired on the next decide attempt; an
unauthorized user cannot decide; a decided approval cannot be re-decided.

Run with: bench --site <site> run-tests --app huf --module huf.huf.doctype.agent_execution_approval.test_agent_execution_approval

NOTE (Phase 7 verification): this file requires a live Frappe bench. It was
authored in an environment with NO bench available and has NOT been executed
yet — it py_compiles and its imports resolve, but its first real run is
pending. Do not treat presence in the tree as evidence of a passing run.
"""
import json
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.tools.code_execution import _sha256, run_python, stash_pending_execution
from huf.huf.doctype.agent_execution_approval.agent_execution_approval import (
	approve_execution,
	reject_execution,
)
from huf.install import create_huf_roles

_PENDING_PREFIX = "huf_pending_execution"


class TestAgentExecutionApproval(unittest.TestCase):
	"""Approval-gate lifecycle tests for parked code executions."""

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
		self._approvals = []
		self.provider = self._ensure_provider()
		self.model = self._ensure_model(self.provider)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._approvals:
			try:
				frappe.cache().delete_value(f"{_PENDING_PREFIX}:{name}")
			except Exception:
				pass
			self._delete("Agent Execution Approval", name)
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

	def _make_profile(self, approval_mode="Ask Every Time"):
		profile = frappe.get_doc(
			{
				"doctype": "Execution Profile",
				"profile_name": f"test-profile-{frappe.generate_hash(length=8)}",
				"approval_mode": approval_mode,
				"filesystem_policy": "None",
			}
		)
		profile.insert(ignore_permissions=True)
		self._profiles.append(profile.name)
		return profile.name

	def _make_agent(self, execution_profile):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"test-agent-{frappe.generate_hash(length=8)}",
				"provider": self.provider,
				"model": self.model,
				"allow_code_execution": 1,
				"execution_profile": execution_profile,
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	def _park_execution(self, requester, code="print('parked')"):
		"""Dispatch an Ask Every Time execution as ``requester``; return (call, approval)."""
		profile = self._make_profile(approval_mode="Ask Every Time")
		agent = self._make_agent(profile)
		frappe.set_user(requester)
		result = run_python(code, agent_doc=agent)
		self.assertEqual(result.get("status"), "Pending Approval")
		call = frappe.get_doc("Agent Tool Call", result["agent_tool_call"])
		approval = frappe.get_doc("Agent Execution Approval", result["approval"])
		self._calls.append(call.name)
		self._approvals.append(approval.name)
		return call, approval

	def _make_parked_pair_directly(self, requester, expires_in_hours=24, code="print('direct')"):
		"""Create a parked (call, approval, Redis hold) triple without run_python."""
		code_ref = _sha256(code)
		call = frappe.get_doc(
			{
				"doctype": "Agent Tool Call",
				"tool": "run_python",
				"status": "Queued",
				"tool_args": json.dumps({"code_ref": code_ref}),
				"code_ref": code_ref,
			}
		)
		call.insert(ignore_permissions=True)
		approval = frappe.get_doc(
			{
				"doctype": "Agent Execution Approval",
				"agent_tool_call": call.name,
				"requested_capability": "code_execution.run",
				"code_ref": code_ref,
				"status": "Pending",
				"expires_on": add_to_date(now_datetime(), hours=expires_in_hours),
			}
		)
		approval.insert(ignore_permissions=True)
		stash_pending_execution(
			approval.name, code=code, profile_snapshot={"limits": {}}, acting_user=requester
		)
		self._calls.append(call.name)
		self._approvals.append(approval.name)
		return call, approval

	def _hold_exists(self, approval_name):
		return frappe.cache().get_value(f"{_PENDING_PREFIX}:{approval_name}") is not None

	# -- Ask Every Time --------------------------------------------------------------

	def test_ask_every_time_parks_and_does_not_enqueue(self):
		requester = self._make_user(roles=("Huf User",))
		call, approval = self._park_execution(requester)

		call.reload()
		approval.reload()
		self.assertEqual(approval.status, "Pending")
		self.assertEqual(call.status, "Queued")
		# No execution happened: no exit status, no resource usage recorded.
		self.assertFalse(call.exit_status)
		self.assertFalse(call.resource_usage)
		# The resumable payload is held in Redis, keyed by the approval.
		self.assertTrue(self._hold_exists(approval.name))

	def test_approve_enqueues_and_impersonates_original_requester(self):
		requester = self._make_user(roles=("Huf User",))
		approver = self._make_user(roles=("Huf Manager",))
		call, approval = self._park_execution(requester)

		frappe.set_user(approver)
		with patch("huf.ai.tools.code_execution.enqueue_execution") as mock_enqueue:
			result = approve_execution(approval.name)

		self.assertEqual(result.get("status"), "Approved")
		mock_enqueue.assert_called_once()
		self.assertEqual(mock_enqueue.call_args.args[0], call.name)
		# CRITICAL: the job impersonates the original requester, not the approver.
		self.assertEqual(mock_enqueue.call_args.kwargs.get("acting_user"), requester)
		self.assertNotEqual(
			mock_enqueue.call_args.kwargs.get("acting_user"), approver,
			"the approver's identity must never be substituted for the requester",
		)

		approval.reload()
		self.assertEqual(approval.status, "Approved")
		self.assertEqual(approval.decided_by, approver)
		self.assertTrue(approval.decided_at)
		self.assertFalse(self._hold_exists(approval.name), "consumed hold must be cleared")

	def test_reject_finalizes_audit_row_without_enqueue(self):
		requester = self._make_user(roles=("Huf User",))
		approver = self._make_user(roles=("Huf Manager",))
		call, approval = self._park_execution(requester)

		frappe.set_user(approver)
		with patch("huf.ai.tools.code_execution.enqueue_execution") as mock_enqueue:
			result = reject_execution(approval.name, comment="not needed")

		self.assertEqual(result.get("status"), "Rejected")
		mock_enqueue.assert_not_called()

		approval.reload()
		self.assertEqual(approval.status, "Rejected")
		self.assertEqual(approval.decided_by, approver)
		call.reload()
		self.assertEqual(call.status, "Failed")
		self.assertEqual(call.exit_status, "Error")
		self.assertIn("rejected", (call.error_message or "").lower())
		self.assertFalse(self._hold_exists(approval.name))

	# -- Never Allow -----------------------------------------------------------------

	def test_never_allow_rejects_synchronously(self):
		requester = self._make_user(roles=("Huf User",))
		profile = self._make_profile(approval_mode="Never Allow")
		agent = self._make_agent(profile)

		frappe.set_user(requester)
		with self.assertRaises(frappe.PermissionError):
			run_python("print(1)", agent_doc=agent)

		call_name = frappe.db.get_value(
			"Agent Tool Call", {"tool": "run_python"}, "name", order_by="creation desc"
		)
		self.assertTrue(call_name)
		self._calls.append(call_name)
		call = frappe.get_doc("Agent Tool Call", call_name)
		self.assertEqual(call.status, "Failed")
		# No approval row is created for a synchronous rejection.
		self.assertEqual(
			frappe.db.count("Agent Execution Approval", {"agent_tool_call": call_name}), 0
		)

	# -- expiry / authorization guards ----------------------------------------------------

	def test_expired_approval_lapses_to_expired_on_decide_attempt(self):
		requester = self._make_user(roles=("Huf User",))
		approver = self._make_user(roles=("Huf Manager",))
		call, approval = self._make_parked_pair_directly(requester, expires_in_hours=-1)

		frappe.set_user(approver)
		with patch("huf.ai.tools.code_execution.enqueue_execution") as mock_enqueue:
			with self.assertRaises(frappe.ValidationError):
				approve_execution(approval.name)

		mock_enqueue.assert_not_called()
		approval.reload()
		self.assertEqual(approval.status, "Expired")
		call.reload()
		self.assertEqual(call.status, "Failed")
		self.assertFalse(self._hold_exists(approval.name))

	def test_unauthorized_user_cannot_decide(self):
		requester = self._make_user(roles=("Huf User",))
		outsider = self._make_user(roles=("Huf User",))
		call, approval = self._make_parked_pair_directly(requester)

		frappe.set_user(outsider)
		with patch("huf.ai.tools.code_execution.enqueue_execution") as mock_enqueue:
			with self.assertRaises(frappe.PermissionError):
				approve_execution(approval.name)

		mock_enqueue.assert_not_called()
		approval.reload()
		self.assertEqual(approval.status, "Pending")
		self.assertTrue(self._hold_exists(approval.name), "undecided hold must survive")

	def test_decided_approval_cannot_be_re_decided(self):
		requester = self._make_user(roles=("Huf User",))
		approver = self._make_user(roles=("Huf Manager",))
		call, approval = self._make_parked_pair_directly(requester)

		frappe.set_user(approver)
		with patch("huf.ai.tools.code_execution.enqueue_execution"):
			approve_execution(approval.name)
			with self.assertRaises(frappe.ValidationError):
				approve_execution(approval.name)
			with self.assertRaises(frappe.ValidationError):
				reject_execution(approval.name)

		approval.reload()
		self.assertEqual(approval.status, "Approved")


if __name__ == "__main__":
	unittest.main()
