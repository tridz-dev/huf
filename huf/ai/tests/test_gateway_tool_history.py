"""Regression: persisted combined 'Tool Result' rows must replay as a paired
assistant tool_calls + tool message and survive repair_message_sequence."""

import json
import unittest
from unittest.mock import patch

from huf.ai.conversation_manager import ConversationManager, repair_message_sequence


def _row(**kw):
    base = {"role": "agent", "kind": "Message", "content": "", "context_policy": "include_full",
            "context_summary": None, "reference_doctype": None, "reference_name": None,
            "record_kind": None, "tool_call": None, "tool_call_id": None, "tool_calls": None}
    base.update(kw)
    return base


def _combined(cid, name="telegram", args='{"action":"send_poll"}', result="ok-result"):
    return _row(
        kind="Tool Result", tool_call="link-" + cid, tool_call_id=cid, record_kind="tool_result",
        content=f"Requesting Tool: {name}\nArguments: {args}\n\n**Tool Result:**\n{result}",
        tool_calls=json.dumps([{"id": cid, "type": "function", "function": {"name": name, "arguments": args}}]),
    )


class TestGatewayToolHistory(unittest.TestCase):
    def _cm(self):
        return ConversationManager("a", channel="telegram", external_id="1")

    def test_combined_row_yields_assistant_and_tool(self):
        out = self._cm()._message_to_context(_combined("toolu_1"))
        self.assertIsInstance(out, list)
        self.assertEqual([m["role"] for m in out], ["assistant", "tool"])
        self.assertEqual(out[0]["tool_calls"][0]["id"], "toolu_1")
        self.assertEqual(out[1]["tool_call_id"], "toolu_1")
        self.assertEqual(out[1]["content"], "ok-result")

    def test_history_survives_repair(self):
        cm = self._cm()
        rows = [_row(role="user", content="hi"), _combined("toolu_1"), _combined("toolu_2"),
                _row(content="done")]
        history = []
        for r in rows:
            ctx = cm._message_to_context(r)
            history.extend(ctx if isinstance(ctx, list) else [ctx])
        with patch("huf.ai.conversation_manager.frappe.log_error") as log:
            fixed = repair_message_sequence(history, "conv")
        log.assert_not_called()
        self.assertEqual(fixed, history)
        self.assertEqual([m["role"] for m in fixed],
                         ["user", "assistant", "tool", "assistant", "tool", "assistant"])

    def test_unfulfilled_tool_call_row_still_dropped(self):
        row = _row(kind="Tool Call", tool_call_id="x", tool_calls=json.dumps(
            [{"id": "x", "type": "function", "function": {"name": "t", "arguments": "{}"}}]))
        out = self._cm()._message_to_context(row)
        self.assertEqual(out["role"], "assistant")
        with patch("huf.ai.conversation_manager.frappe.log_error"):
            self.assertEqual(repair_message_sequence([out], "c"), [])
