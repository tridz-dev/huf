"""Streamed tool calls (incl. desktop tools) always publish a terminal event keyed by the LLM id."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from huf.ai.providers import litellm as lp

TIMEOUT = {
	"ok": False,
	"op": "workspace.info",
	"workspace": "w",
	"error": {"code": "timeout", "message": "Timed out waiting for the desktop to finish the call."},
	"truncated": False,
	"duration_ms": 0,
}
OK = {"ok": True, "op": "workspace.info", "workspace": "w", "result": {"root": "/x"}}


class TestStreamToolOutcome(TestCase):
	def _publish(self, result, message_name=None):
		ctx = {"conversation_id": "CONV-1", "agent_run_id": "RUN-1"}
		call = {"id": "call_abc123"}
		with (
			patch.object(lp.frappe, "publish_realtime") as pub,
			patch.object(lp, "transaction_checkpoint"),
		):
			lp._publish_stream_tool_outcome(ctx, call, "desktop_workspace_info", result, message_name)
		return pub.call_args.kwargs["message"]

	def test_user_and_checkpoint_params(self):
		ctx = {"conversation_id": "C", "agent_run_id": "R"}
		with patch.object(lp.frappe, "publish_realtime") as pub, patch.object(
			lp, "transaction_checkpoint"
		) as cp:
			lp._publish_stream_tool_outcome(ctx, {"id": "x"}, "t", OK, None, user="owner@x.com", checkpoint=False)
		self.assertEqual(pub.call_args.kwargs["user"], "owner@x.com")
		cp.assert_not_called()
		with patch.object(lp.frappe, "publish_realtime") as pub, patch.object(
			lp.frappe, "session", MagicMock(user="sess@x.com"), create=True
		), patch.object(lp, "transaction_checkpoint") as cp:
			lp._publish_stream_tool_outcome(ctx, {"id": "x"}, "t", OK, None)
		self.assertEqual(pub.call_args.kwargs["user"], "sess@x.com")
		cp.assert_called_once()

	def test_failed_detection(self):
		self.assertTrue(lp._tool_result_failed(TIMEOUT))
		self.assertTrue(lp._tool_result_failed({"error": "boom"}))
		self.assertTrue(lp._tool_result_failed("Error executing tool x: boom"))
		self.assertTrue(lp._tool_result_failed('{"ok": false, "error": {"message": "m"}}'))
		self.assertFalse(lp._tool_result_failed(OK))
		self.assertFalse(lp._tool_result_failed({"ask_user": {"questions": []}, "block": "x"}))
		self.assertFalse(lp._tool_result_failed("plain text output"))

	def test_timeout_publishes_failed_with_message_and_llm_id(self):
		msg = self._publish(TIMEOUT)
		self.assertEqual(msg["type"], "tool_call_failed")
		self.assertEqual(msg["tool_call_id"], "call_abc123")
		self.assertEqual(msg["call_id"], "call_abc123")
		self.assertIn("Timed out", msg["error"])

	def test_success_publishes_completed_even_without_message_row(self):
		msg = self._publish(OK, message_name=None)
		self.assertEqual(msg["type"], "tool_call_completed")
		self.assertEqual(msg["call_id"], "call_abc123")
		self.assertEqual(msg["tool_result"], OK)


class TestToolResultFailedWarningError(TestCase):
	def test_string_error_with_success_markers_not_failed(self):
		from huf.ai.providers import litellm as lp
		self.assertFalse(lp._tool_result_failed({"ok": True, "error": "deprecated flag"}))
		self.assertFalse(lp._tool_result_failed({"success": True, "error": "warn"}))
		self.assertFalse(lp._tool_result_failed({"status": "completed", "error": "warn"}))
		self.assertTrue(lp._tool_result_failed({"success": False}))
		self.assertTrue(lp._tool_result_failed({"status": "error"}))
		self.assertTrue(lp._tool_result_failed({"error": {"code": "x"}}))

	def test_checkpoint_failure_after_publish_no_raise(self):
		from unittest.mock import patch
		from huf.ai.providers import litellm as lp
		with patch.object(lp.frappe, "publish_realtime") as pub, \
			patch.object(lp, "transaction_checkpoint", side_effect=RuntimeError("x")):
			lp._publish_stream_tool_outcome({"conversation_id": "C"}, {"id": "1"}, "t", {"ok": True}, None)
		self.assertEqual(pub.call_count, 1)


class TestUnavailableTool(TestCase):
	def test_result_shape_for_desktop_tool(self):
		r = lp._tool_not_available_result("desktop_write_file")
		self.assertEqual(r["ok"], False)
		self.assertEqual(r["error"]["code"], "tool_not_available")
		self.assertIn("desktop not connected", r["error"]["message"])
		self.assertTrue(lp._tool_result_failed(r))

	def test_finalize_fails_row_and_publishes_with_llm_id(self):
		ctx = {"conversation_id": "C", "agent_run_id": "R"}
		with (
			patch.object(lp.frappe, "db", new=MagicMock()) as db,
			patch.object(lp, "_publish_stream_tool_outcome") as pub,
		):
			db.get_value.side_effect = ["ROW-1", "MSG-1"]
			r = lp._finalize_unavailable_tool_call(ctx, {"id": "call_x"}, "desktop_write_file")
		self.assertEqual(r["error"]["code"], "tool_not_available")
		args = db.set_value.call_args.args
		self.assertEqual(args[1], "ROW-1")
		self.assertEqual(args[2]["status"], "Failed")
		self.assertEqual(pub.call_args.args[1], {"id": "call_x"})
		self.assertEqual(pub.call_args.args[4], "MSG-1")
