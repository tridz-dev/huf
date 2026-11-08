import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "external_runner"))
import runner


def tool_result(data):
	return {"result": {"content": [{"type": "text", "text": json.dumps(data)}]}}


class HelperTests(unittest.TestCase):
	def test_parse_tool_result(self):
		self.assertEqual(runner.parse_tool_result(tool_result({"a": 1})), {"a": 1})

	def test_parse_errors(self):
		with self.assertRaises(runner.RpcError):
			runner.parse_tool_result({"error": {"message": "x"}})
		with self.assertRaises(runner.RpcError):
			runner.parse_tool_result({"result": {"content": []}})

	def test_build_argv_keeps_prompt_single_element(self):
		argv = runner.build_argv("tool --p {prompt} -v", "a b; rm -rf /")
		self.assertEqual(argv, ["tool", "--p", "a b; rm -rf /", "-v"])

	def test_build_argv_appends_and_stdin(self):
		self.assertEqual(runner.build_argv("tool", "hi"), ["tool", "hi"])
		self.assertEqual(runner.build_argv("tool {prompt}", "hi", True), ["tool"])
		with self.assertRaises(ValueError):
			runner.build_argv("  ", "hi")

	def test_truncate(self):
		self.assertEqual(runner.truncate("abc"), "abc")
		out = runner.truncate("x" * 5000)
		self.assertEqual(len(out), runner.MAX_REPORT_CHARS)
		self.assertTrue(out.endswith("[truncated]"))

	def test_backoff(self):
		self.assertEqual([runner.backoff_delay(i) for i in range(3)], [1, 2, 4])
		self.assertEqual(runner.backoff_delay(20), runner.BACKOFF_CAP)

	def test_task_events_filters(self):
		result = {"events": [{"event_type": "message"}, {"event_type": "task_assigned", "payload": {}}]}
		self.assertEqual(len(runner.task_events(result)), 1)

	def test_run_command(self):
		self.assertEqual(runner.run_command([sys.executable, "-c", "print('ok')"], None, 10), (True, "ok"))
		ok, text = runner.run_command([sys.executable, "-c", "import sys;sys.exit(3)"], None, 10)
		self.assertFalse(ok)
		self.assertIn("Exit code 3", text)
		ok, text = runner.run_command([sys.executable, "-c", "import time;time.sleep(30)"], None, 0.5)
		self.assertFalse(ok)
		self.assertIn("Timed out", text)


if __name__ == "__main__":
	unittest.main()
