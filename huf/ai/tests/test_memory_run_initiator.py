"""Recall and capture follow the user who started the run, not the session name."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_frappe = sys.modules.get("frappe")
if isinstance(_frappe, MagicMock):
	# Bench-less stub: keep @frappe.whitelist() from replacing functions with mocks.
	_frappe.whitelist = lambda *a, **k: (lambda fn: fn)

from huf.ai import memory_tools
from huf.ai.memory import extraction
from huf.ai.tests import test_memory_default_policy as base

AI_DIR = Path(__file__).resolve().parents[1]


class InitiatorCase(base.MemoryCase):
	def setUp(self):
		super().setUp()
		# A run in u1's conversation that Administrator started.
		self.f.tables["Agent Run"]["AR"] = {
			"agent": "A",
			"conversation": "C1",
			"run_kind": "agent",
			"owner": "Administrator",
		}

	def as_run(self, run_id, session_user="Administrator"):
		self.f.session.user = session_user
		self.f.flags.huf_current_agent_run_id = run_id

	def search(self, run_id):
		return memory_tools.search_memory_records(
			query="employee", agent_name="A", conversation_id="C1", agent_run_id=run_id
		)["results"]


class TestRecall(InitiatorCase):
	def test_administrator_chatting_in_another_users_conversation_recalls_nothing(self):
		self.save()
		row = {"scope_type": "User", "scope_key": "u1", "agent": "A"}
		for run_id in (None, "AR"):  # streaming sets no run flag; sync runs do
			self.as_run(run_id)
			self.assertIsNone(self.recall(conversation="C1"), run_id)
			self.assertEqual(self.search(run_id), [], run_id)
			self.assertFalse(memory_tools._can_read_memory(row, "C1", "A", strict=True), run_id)

	def test_drained_owner_run_still_recalls(self):
		self.save()
		self.as_run("R1")
		self.assertIn("Vaishna", self.recall(conversation="C1"))
		self.assertEqual(len(self.search("R1")), 1)

	def test_requester_user_wins_over_run_owner(self):
		self.save()
		self.f.tables["Agent Run"]["R1"]["requester_user"] = "u2"
		self.as_run("R1", session_user="u1")
		self.assertIsNone(self.recall(conversation="C1"))

	def test_explicit_policy_injection_is_denied_too(self):
		policy = self.f.policy()
		self.f.records.append(
			{"title": "t", "summary_text": "x", "status": "Active", "scope_type": "User", "scope_key": "u1"}
		)
		self.as_run("AR")
		self.assertIsNone(memory_tools.get_injected_memory_text("P", policy, conversation_id="C1"))


class TestCapture(InitiatorCase):
	def test_tool_save_from_non_owner_run_is_skipped(self):
		self.as_run("AR")
		self.assertTrue(self.save(agent_run_id="AR")["skipped"])
		self.f.policy()
		result = self.save(agent_name="P", agent_run_id="AR", scope_type="User")
		self.assertTrue(result["skipped"])
		self.assertEqual(self.f.records, [])

	def extract(self, run_id):
		self.f.session.user = "Administrator"
		run_agent_sync = MagicMock(return_value={"success": False})
		manager = MagicMock()
		history = manager.return_value.get_conversation_history
		history.return_value = [{"role": "user", "content": "I like tea"}]
		modules = {
			"huf.ai.agent.integration": SimpleNamespace(run_agent_sync=run_agent_sync),
			"huf.ai.conversation_manager": SimpleNamespace(ConversationManager=manager),
		}
		runs = [
			base.Row(v, name=k) for k, v in self.f.tables["Agent Run"].items() if v["conversation"] == "C1"
		]
		with patch.dict(sys.modules, modules), patch.object(self.f, "get_all", return_value=runs):
			extraction.extract_memory_from_run(run_id)
		return run_agent_sync, history

	def test_extraction_skips_non_owner_run(self):
		run_agent_sync, _ = self.extract("AR")
		run_agent_sync.assert_not_called()

	def test_extraction_of_owner_run_leaves_out_non_owner_turns(self):
		run_agent_sync, history = self.extract("R1")
		run_agent_sync.assert_called_once()
		self.assertEqual(history.call_args.kwargs["exclude_runs"], {"AR"})


class TestWiring(unittest.TestCase):
	def test_history_filters_excluded_runs(self):
		src = (AI_DIR / "conversation_manager.py").read_text()
		self.assertIn('"agent_run",', src)
		self.assertIn('m.get("agent_run") not in exclude_runs', src)

	def test_cancelled_orchestration_step_uses_safe_commit(self):
		src = (AI_DIR / "orchestration" / "orchestrator.py").read_text()
		block = src[
			src.index('if current_status == "Cancelled":') : src.index(
				'return "cancelled"', src.index('if current_status == "Cancelled":')
			)
		]
		self.assertIn("safe_commit()", block)
		self.assertNotIn("db.commit", block)


if __name__ == "__main__":
	unittest.main()
