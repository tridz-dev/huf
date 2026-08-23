# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for huf.ai.context_segments.count_tool_exchange_tokens:

  - counts assistant messages carrying `tool_calls` (the serialized
    name+arguments payload, not `content`)
  - counts messages with role == "tool" (the tool result content)
  - does NOT count system/user/plain-assistant (no tool_calls) messages
  - returns None if any message's count fails
  - handles both string and list-of-content-block `content` shapes

`_count()` (the module's shared token counter) calls `litellm.token_counter`,
which is stubbed in this environment (see huf/ai/tests/_stub_env.py) to
return a deterministic value via a side_effect keyed on text length, so
these tests can assert on exact counted totals rather than "it ran".
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import litellm  # noqa: E402
from huf.ai.context_segments import count_tool_exchange_tokens  # noqa: E402


class TestCountToolExchangeTokens(unittest.TestCase):
    def setUp(self):
        # Deterministic per-call token count: 1 "token" per character. Lets
        # tests assert exact totals without depending on a real tokenizer.
        litellm.token_counter.side_effect = lambda model, text: len(text)
        litellm.token_counter.return_value = None

    def tearDown(self):
        litellm.token_counter.side_effect = None
        litellm.token_counter.return_value = 0

    def test_empty_or_none_messages_returns_zero(self):
        self.assertEqual(count_tool_exchange_tokens("gpt-4", []), 0)
        self.assertEqual(count_tool_exchange_tokens("gpt-4", None), 0)

    def test_counts_assistant_message_with_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search", "arguments": '{"q": "some longer search query"}'}},
                ],
            }
        ]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_counts_tool_role_message(self):
        messages = [{"role": "tool", "content": "the tool result"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, len("the tool result"))

    def test_does_not_count_system_message(self):
        messages = [{"role": "system", "content": "you are a helpful assistant with lots of instructions"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, 0)

    def test_does_not_count_user_message(self):
        messages = [{"role": "user", "content": "please do something for me"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, 0)

    def test_does_not_count_plain_assistant_message_without_tool_calls(self):
        messages = [{"role": "assistant", "content": "here is my final answer to your question"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, 0)

    def test_assistant_tool_calls_counts_arguments_not_content(self):
        # An assistant tool-calling turn's `content` is frequently empty and
        # is deliberately not the thing measured -- only the serialized
        # tool_calls payload is counted.
        messages = [
            {
                "role": "assistant",
                "content": "this large content block should not be counted at all",
                "tool_calls": [{"function": {"name": "f", "arguments": "{}"}}],
            }
        ]
        result = count_tool_exchange_tokens("gpt-4", messages)
        # Serialized {"name": "f", "arguments": "{}"} is much shorter than
        # the (ignored) content string above.
        self.assertLess(result, len(messages[0]["content"]))

    def test_tool_message_with_list_of_content_blocks_shape(self):
        messages = [
            {
                "role": "tool",
                "content": [
                    {"type": "text", "text": "part one "},
                    {"type": "text", "text": "part two"},
                ],
            }
        ]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, len("part one \npart two"))

    def test_tool_message_with_string_content_shape(self):
        messages = [{"role": "tool", "content": "plain string result"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, len("plain string result"))

    def test_sums_across_multiple_qualifying_messages(self):
        messages = [
            {"role": "system", "content": "ignored"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "tool", "content": "result one"},
            {"role": "user", "content": "ignored too"},
            {"role": "tool", "content": "result two"},
        ]
        result = count_tool_exchange_tokens("gpt-4", messages)
        tool_call_only_result = count_tool_exchange_tokens(
            "gpt-4",
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "f", "arguments": "{}"}}],
                }
            ],
        )
        expected = tool_call_only_result + len("result one") + len("result two")
        self.assertEqual(result, expected)

    def test_returns_none_when_a_message_count_fails(self):
        def flaky_counter(model, text):
            if text == "will fail":
                raise RuntimeError("tokenizer exploded")
            return len(text)

        litellm.token_counter.side_effect = flaky_counter
        messages = [{"role": "tool", "content": "will fail"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertIsNone(result)

    def test_non_dict_messages_are_skipped_not_raised(self):
        messages = ["not a dict", {"role": "tool", "content": "ok"}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, len("ok"))

    def test_empty_tool_message_content_contributes_nothing(self):
        messages = [{"role": "tool", "content": ""}]
        result = count_tool_exchange_tokens("gpt-4", messages)
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
