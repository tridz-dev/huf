import inspect
import unittest

from huf.ai import agent_integration as ai


class TestFinalizedRunSideEffects(unittest.TestCase):
	"""A late Success that loses to a sweep/cancel must not emit `done` or queue post-run side effects."""

	def test_stream_success_yields_error_not_done_when_guard_false(self):
		src = inspect.getsource(ai)
		i = src.index("_finalized_here = _guarded_finish_started_run(", src.index("stream_run_update"))
		j = src.index('chunk["success"] = True', i)
		block = src[i:j]
		self.assertIn("if not _finalized_here:", block)
		guard = block[block.index("if not _finalized_here:"):]
		self.assertIn('"type": "error"', guard)
		self.assertIn('"success": False', guard)
		self.assertIn("return", guard)
		# the early return precedes the sub-agent hook, auto-naming and summarization enqueues
		self.assertIn("sub_agent_completed", block)
		self.assertLess(block.index("if not _finalized_here:"), block.index("sub_agent_completed"))

	def test_sync_memory_extraction_gated_on_guard_result(self):
		src = inspect.getsource(ai._execute_agent_run)
		self.assertIn("_finalized_here = _guarded_finish_started_run(", src)
		self.assertIn("if _finalized_here and should_extract_memory(", src)


class TestArrayItemsSchemaBuiltinOnly(unittest.TestCase):
	def test_user_tool_params_stay_strings(self):
		from huf.ai.tools._registry import array_items_schema

		self.assertEqual(array_items_schema("data", "my_app.tools.custom"), {"type": "string"})
		self.assertEqual(array_items_schema("edges", ""), {"type": "string"})

	def test_registry_tool_keeps_object_items(self):
		from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, array_items_schema

		path = ALL_INTEGRATION_TOOLS[0]["function_path"]
		self.assertEqual(array_items_schema("data", path), {"type": "object"})
		self.assertEqual(array_items_schema("fields", path), {"type": "string"})
		self.assertEqual(array_items_schema("data"), {"type": "object"})
