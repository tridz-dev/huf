"""``stop`` node: fails the run with the message."""

import unittest

from huf.ai.flow import engine as flow_engine
from huf.ai.graph.executor import GraphContext


class _Run:
	flow_id = "f"
	name = "FR"
	context_json = "{}"


def _settings(data):
	return flow_engine.FlowRunContext(context=GraphContext(data))


class TestStopNode(unittest.TestCase):
	def _stop(self, config, data=None):
		return flow_engine._exec_stop(_Run(), {"id": "stop"}, config, _settings(data or {}))

	def test_stop_error_fails_run_with_message(self):
		out = self._stop({"message": "Stock is short"})
		self.assertEqual(out["status"], "failed")
		self.assertEqual(out["error"], "Stock is short")

	def test_stop_error_is_the_default(self):
		out = self._stop({"message": "Stopped"})
		self.assertEqual(out["status"], "failed")
		self.assertEqual(out["error"], "Stopped")

	def test_stop_error_without_message_asks_for_one(self):
		out = self._stop({})
		self.assertEqual(out["status"], "failed")
		self.assertIn("Write the message", out["error"])

	def test_stop_has_no_next(self):
		for config in ({"message": "x"},):
			out = self._stop(config)
			self.assertNotIn("next_node_id", out)
			self.assertNotIn("next", out)


if __name__ == "__main__":
	unittest.main()
