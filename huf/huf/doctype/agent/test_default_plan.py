"""Default plan generation: only when empty, no parent save, status reported.

Pure unit tests (frappe is mocked) so they also run without a bench.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from huf.huf.doctype.agent import default_plan as dp


def _agent(name="AG-1"):
	doc = MagicMock()
	doc.name = name
	doc.provider = "P"
	doc.model = "M"
	return doc


def _stub_modules(response="1. one\n2. two", raises=None):
	run = MagicMock(return_value={"response": response, "agent_run_id": "RUN-1"})
	if raises:
		run.side_effect = raises
	integration = types.ModuleType("huf.ai.agent.integration")
	integration.run_agent_sync = run
	orchestrator = types.ModuleType("huf.ai.orchestration.orchestrator")
	orchestrator.parse_plan_steps = lambda text: [
		line.split(". ", 1)[1] for line in text.splitlines() if ". " in line
	]
	resolver = types.ModuleType("huf.ai.prompt_resolver")
	resolver.resolve_prompt = lambda doc: "do the thing"
	mods = {
		"huf.ai.agent.integration": integration,
		"huf.ai.orchestration.orchestrator": orchestrator,
		"huf.ai.prompt_resolver": resolver,
	}
	return patch.dict(sys.modules, mods), run


class TestDefaultPlan(unittest.TestCase):
	def test_existing_plan_is_never_overwritten(self):
		agent = _agent()
		mods, run = _stub_modules()
		with mods, patch.object(dp, "frappe") as fr, patch.object(dp, "plan_is_empty", return_value=False):
			self.assertIsNone(dp.generate_default_plan(agent))
		run.assert_not_called()
		agent.save.assert_not_called()
		fr.enqueue.assert_not_called()

	def test_generates_rows_without_saving_parent(self):
		agent = _agent()
		mods, run = _stub_modules()
		with (
			mods,
			patch.object(dp, "frappe") as fr,
			patch.object(dp, "plan_is_empty", return_value=True),
			patch.object(dp, "write_rows", return_value=True) as write,
		):
			result = dp.generate_default_plan(agent)
		self.assertEqual(result, ("RUN-1", ["one", "two"]))
		write.assert_called_once_with("AG-1", ["one", "two"])
		agent.save.assert_not_called()
		self.assertTrue(fr.publish_realtime.called)
		self.assertEqual(fr.publish_realtime.call_args_list[-1].args[1]["state"], "done")

	def test_failure_is_reported_not_raised(self):
		agent = _agent()
		mods, _run = _stub_modules(raises=RuntimeError("provider down"))
		with (
			mods,
			patch.object(dp, "frappe") as fr,
			patch.object(dp, "plan_is_empty", return_value=True),
			patch.object(dp, "write_rows") as write,
		):
			self.assertIsNone(dp.generate_default_plan(agent))
		write.assert_not_called()
		last = fr.publish_realtime.call_args_list[-1].args[1]
		self.assertEqual(last["state"], "failed")
		self.assertIn("provider down", last["error"])

	def test_empty_model_response_is_a_failure(self):
		agent = _agent()
		mods, _run = _stub_modules(response="nothing useful")
		with (
			mods,
			patch.object(dp, "frappe") as fr,
			patch.object(dp, "plan_is_empty", return_value=True),
			patch.object(dp, "write_rows") as write,
		):
			dp.generate_default_plan(agent)
		write.assert_not_called()
		self.assertEqual(fr.publish_realtime.call_args_list[-1].args[1]["state"], "failed")

	def test_write_rows_skips_when_plan_appeared(self):
		with patch.object(dp, "frappe") as fr, patch.object(dp, "plan_is_empty", return_value=False):
			self.assertFalse(dp.write_rows("AG-1", ["a"]))
		fr.get_doc.assert_not_called()

	def test_write_rows_inserts_children_only(self):
		with (
			patch.object(dp, "frappe") as fr,
			patch.object(dp, "plan_is_empty", return_value=True),
			patch.object(dp, "now_datetime", return_value="now"),
		):
			rows = [MagicMock(), MagicMock()]
			fr.get_doc.side_effect = rows
			self.assertTrue(dp.write_rows("AG-1", ["a", "b"]))
		for row in rows:
			row.db_insert.assert_called_once()
		self.assertEqual(fr.get_doc.call_args_list[1].args[0]["step_index"], 2)
		fr.clear_document_cache.assert_called_once_with("Agent", "AG-1")

	def test_enqueue_only_when_empty(self):
		with patch.object(dp, "frappe") as fr, patch.object(dp, "plan_is_empty", return_value=False):
			dp.enqueue_default_plan("AG-1")
		fr.enqueue.assert_not_called()
		with patch.object(dp, "frappe") as fr, patch.object(dp, "plan_is_empty", return_value=True):
			dp.enqueue_default_plan("AG-1")
		self.assertEqual(fr.enqueue.call_args.args[0], dp.JOB_PATH)
		self.assertEqual(fr.enqueue.call_args.kwargs["agent"], "AG-1")


if __name__ == "__main__":
	unittest.main()
