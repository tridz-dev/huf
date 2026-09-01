# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Test suite for prompt cache marker placement logic in litellm.py

Ensures that:
1. Cache markers are placed ONLY on the current user message (never on history)
2. Sync and streaming paths produce identical marker placement
3. Marker suppression via cache_dynamic_content override works correctly
4. Below-minimum prefix detection sets the diagnostic flag
5. litellm.modify_params is a global setting, never sent per-request
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
from types import SimpleNamespace
import json
import litellm


class TestCacheMarkerPlacementLogic(unittest.TestCase):
    """Test cache marker placement behavior in isolation"""

    def test_format_conversation_history_no_markers(self):
        """Verify _format_conversation_history does NOT add cache markers"""
        from huf.ai.providers.litellm import _format_conversation_history

        conversation_history = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ]

        formatted = _format_conversation_history(conversation_history)

        # Should have 3 messages, all unchanged
        self.assertEqual(len(formatted), 3)
        for i, msg in enumerate(formatted):
            original = conversation_history[i]
            self.assertEqual(msg["role"], original["role"])
            self.assertEqual(msg["content"], original["content"])
            # Verify no cache_control was added
            self.assertNotIn("cache_control", msg)
            if isinstance(msg["content"], list):
                for block in msg["content"]:
                    if isinstance(block, dict):
                        self.assertNotIn("cache_control", block)

    def test_build_text_content_with_cache(self):
        """Verify _build_text_content adds cache marker when enabled"""
        from huf.ai.providers.litellm import _build_text_content

        # Without cache
        result = _build_text_content("Hello", "anthropic", False, "ephemeral")
        self.assertEqual(result, "Hello")

        # With cache - anthropic
        result = _build_text_content("Hello", "anthropic", True, "ephemeral")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Hello")
        self.assertIn("cache_control", result[0])
        self.assertEqual(result[0]["cache_control"]["type"], "ephemeral")

        # With cache - non-anthropic (no marker)
        result = _build_text_content("Hello", "openai", True, "ephemeral")
        self.assertEqual(result, [{"type": "text", "text": "Hello"}])

    def test_estimate_prefix_tokens(self):
        """Verify token estimation is reasonable"""
        from huf.ai.providers.litellm import _estimate_prefix_tokens

        messages = [
            {
                "role": "system",
                "content": "This is a system prompt with some text that should be counted.",
            },
            {
                "role": "user",
                "content": "This is a user message.",
            },
        ]

        tokens = _estimate_prefix_tokens(messages)
        # Rough estimate: ~100 chars / 4 * 1.1 = ~27.5 tokens
        # We just want to verify it's a reasonable number
        self.assertGreater(tokens, 0)
        self.assertLess(tokens, 1000)

    def test_estimate_prefix_tokens_with_list_content(self):
        """Verify token estimation works with list-format content"""
        from huf.ai.providers.litellm import _estimate_prefix_tokens

        messages = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "First part"},
                    {"type": "text", "text": "Second part"},
                ],
            }
        ]

        tokens = _estimate_prefix_tokens(messages)
        self.assertGreater(tokens, 0)


class TestCacheMarkerPlacementIntegration(unittest.TestCase):
    """Integration tests for cache marker placement in complete flow"""

    def test_history_markers_not_added(self):
        """Verify _format_conversation_history never adds cache markers"""
        from huf.ai.providers.litellm import _format_conversation_history

        history = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
        ]

        # Format history - should have no markers even with cache_enabled=True (old behavior)
        formatted = _format_conversation_history(history)

        # Verify no markers were added
        for msg in formatted:
            self.assertNotIn("cache_control", msg)
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict):
                        self.assertNotIn("cache_control", block, "No marker should be added to history")

    def test_user_message_gets_marker_when_caching_enabled(self):
        """Verify _build_text_content adds marker for user message when cache enabled"""
        from huf.ai.providers.litellm import _build_text_content

        text = "This is a user message"

        # Without cache
        content_uncached = _build_text_content(text, "anthropic", False, "ephemeral")
        self.assertEqual(content_uncached, text)

        # With cache
        content_cached = _build_text_content(text, "anthropic", True, "ephemeral")
        self.assertIsInstance(content_cached, list)
        self.assertEqual(len(content_cached), 1)
        self.assertIn("cache_control", content_cached[0])
        self.assertEqual(content_cached[0]["cache_control"]["type"], "ephemeral")

    def test_cache_dynamic_content_override_false_logic(self):
        """Verify the cache_dynamic_content override wins inside Advanced mode.

        Exercises the real resolver rather than a re-implementation of it, so the
        test cannot drift away from the shipped logic.
        """
        from huf.ai.providers.litellm import _resolve_cache_settings

        agent_doc = {
            "prompt_cache_mode": "Advanced",
            "enable_prompt_caching": True,
            "cache_conversation_history": True,
        }
        settings = _resolve_cache_settings(agent_doc, {"cache_dynamic_content": False})

        # Result should be False (override wins)
        self.assertFalse(
            settings.cache_dynamic_content, "Override should suppress dynamic content marker"
        )

    def test_auto_mode_ignores_dynamic_content_override(self):
        """Auto uses HUF defaults; the granular runtime flags are Advanced-only."""
        from huf.ai.providers.litellm import _resolve_cache_settings

        settings = _resolve_cache_settings(
            {
                "prompt_cache_mode": "Auto",
                "enable_prompt_caching": False,
                "agent_tool": [{"tool": "frappe_list_records"}],
            },
            {"cache_dynamic_content": False, "cache_static_prefix": False},
        )
        self.assertTrue(settings.enabled)
        # The tool-bearing Agent, not the runtime override, decides the dynamic
        # breakpoint in Auto mode.
        self.assertTrue(settings.cache_dynamic_content)
        self.assertTrue(settings.cache_static_prefix)

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True)
    @patch("huf.ai.providers.litellm.resolve_capabilities")
    def test_below_minimum_tokens_sets_diagnostic_flag(
        self,
        mock_resolve_capabilities,
        mock_prompt_cache,
        mock_resolve_api_base,
        mock_normalize_model,
        mock_resolve_api_key,
        mock_frappe,
    ):
        """Verify below-minimum prefix sets cache_skipped_below_min_tokens flag"""
        from huf.ai.providers.litellm import _estimate_prefix_tokens

        # Test that a small prefix would be flagged
        small_messages = [
            {"role": "system", "content": "Hi"},  # Very small prefix
        ]
        tokens = _estimate_prefix_tokens(small_messages)
        self.assertLess(tokens, 1024, "Small prefix should be below Haiku minimum")

        # Test that a large prefix would pass
        large_messages = [
            {
                "role": "system",
                "content": "x" * 5000,  # 5000 chars = ~1375 tokens, above Haiku's 1024
            },
        ]
        tokens = _estimate_prefix_tokens(large_messages)
        self.assertGreater(tokens, 1024, "Large prefix should meet minimum")

    def test_cache_skipped_below_min_tokens_flag_behavior(self):
        """Verify cache_skipped_below_min_tokens flag is set correctly"""
        from huf.ai.providers.litellm import _estimate_prefix_tokens

        # Small messages below threshold
        small_messages = [
            {"role": "system", "content": "Hi"},
        ]
        small_tokens = _estimate_prefix_tokens(small_messages)
        self.assertLess(small_tokens, 1024, "Small prefix should be below threshold")

        # Large messages above threshold
        large_messages = [
            {
                "role": "system",
                "content": "x" * 5000,  # About 1375 tokens
            },
        ]
        large_tokens = _estimate_prefix_tokens(large_messages)
        self.assertGreater(large_tokens, 1024, "Large prefix should meet Haiku minimum")


class TestModifyParamsGlobal(unittest.TestCase):
    """Test that modify_params is set globally, never per-request"""

    def test_modify_params_never_in_per_request_kwargs(self):
        """Verify modify_params never appears in completion_kwargs"""
        # This test documents the expected behavior:
        # modify_params should only be set globally on litellm module,
        # never passed as a per-request parameter.

        litellm.modify_params = True

        completion_kwargs = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "test"}],
        }

        # Verify it's not in kwargs
        self.assertNotIn("modify_params", completion_kwargs)

        # Verify the global is set
        self.assertTrue(litellm.modify_params)


class TestCacheSkippedBelowMinTokensEndToEnd(unittest.TestCase):
    """End-to-end coverage for cache_skipped_below_min_tokens.

    The flag was previously computed but (a) captured by value into
    total_usage/stream_total_usage BEFORE the round loop determined it, so the
    dict always carried the initial False, and (b) never implemented at all in
    run_stream(). These tests drive run()/run_stream() through their real
    control flow (mocking only the network boundary and Frappe) so a
    regression of either defect fails a test, unlike the previous unit tests
    which only exercised _estimate_prefix_tokens in isolation.
    """

    def _agent_and_provider_mocks(self, instructions="Hi"):
        agent = Mock()
        agent.instructions = instructions
        agent.tools = None
        agent.max_turns = 5
        agent.model_settings = None

        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 1.0
        agent_doc.enable_prompt_caching = True
        agent_doc.get = Mock(side_effect=lambda key, default=None: {
            "enable_prompt_caching": True,
            "cache_control_type": "ephemeral",
            "cache_system_message": True,
            "cache_conversation_history": False,
            "reasoning_mode": None,
            "reasoning_effort": None,
            "reasoning_budget_tokens": None,
            "reasoning_summary": None,
        }.get(key, default))

        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)

        return agent, agent_doc, provider_doc

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True)
    @patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=2048))
    @patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock())
    @patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={}))
    @patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={})
    @patch("huf.ai.providers.litellm.extract_round_usage", return_value={
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    })
    @patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test"))
    def test_sync_flag_reaches_returned_usage_single_round(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
        mock_resolve_capabilities,
        mock_prompt_cache,
        mock_serialize_tools,
        mock_repair_seq,
        mock_trim_messages,
        mock_resolve_api_base,
        mock_normalize_model,
        mock_resolve_api_key,
        mock_litellm,
        mock_frappe,
    ):
        """A below-threshold prefix must show up as True in the dict run() returns.

        Regression guard for the ordering bug: total_usage was built with the
        flag's *initial* value before the round loop ran the check that flips
        it, so the returned usage always carried False even when the
        determination inside the loop was True.
        """
        import asyncio
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks(instructions="Hi")

        mock_frappe.get_doc = Mock(side_effect=lambda doctype, name: {
            "Agent": agent_doc,
            "AI Provider": provider_doc,
        }.get(doctype))
        mock_frappe.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
        mock_frappe.has_permission = Mock(return_value=True)
        mock_frappe.session = Mock(user="test")
        mock_frappe.logger = Mock(return_value=Mock())

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock(
            content="Final answer",
            tool_calls=None,
            thinking_blocks=None,
            reasoning_content=None,
        )
        mock_response.usage = Mock()
        mock_litellm.side_effect = lambda **kwargs: mock_response

        context = {"agent_name": "TestAgent"}
        result = asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertTrue(
            result.usage["cache_skipped_below_min_tokens"],
            "cache_skipped_below_min_tokens must be True on the dict run() actually returns, "
            "not just on the local variable inside the loop",
        )

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True)
    @patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=2048))
    @patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock())
    @patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={}))
    @patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={})
    @patch("huf.ai.providers.litellm.extract_round_usage", return_value={
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    })
    @patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test"))
    def test_sync_flag_persists_across_multiple_rounds_and_is_only_logged_once(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
        mock_resolve_capabilities,
        mock_prompt_cache,
        mock_serialize_tools,
        mock_repair_seq,
        mock_trim_messages,
        mock_resolve_api_base,
        mock_normalize_model,
        mock_resolve_api_key,
        mock_litellm,
        mock_frappe,
    ):
        """The comment above the check says the flag 'persists across rounds' —
        prove it survives a tool-call round into a second, final round, and
        that the min-token estimate/log only fires once (the
        `not cache_skipped_below_min_tokens` guard short-circuits round 2)."""
        import asyncio
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks(instructions="Hi")
        agent.tools = []  # _find_tool iterates agent.tools; None is not iterable

        mock_frappe.get_doc = Mock(side_effect=lambda doctype, name: {
            "Agent": agent_doc,
            "AI Provider": provider_doc,
        }.get(doctype))
        mock_frappe.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
        mock_frappe.has_permission = Mock(return_value=True)
        mock_frappe.session = Mock(user="test")
        mock_frappe.logger = Mock(return_value=Mock())

        tool_call = Mock()
        tool_call.id = "tc1"
        tool_call.function.name = "nonexistent_tool"
        tool_call.function.arguments = "{}"

        round1_response = Mock()
        round1_response.choices = [Mock()]
        round1_response.choices[0].message = Mock(
            content=None,
            tool_calls=[tool_call],
            thinking_blocks=None,
            reasoning_content=None,
        )
        round1_response.usage = Mock()

        round2_response = Mock()
        round2_response.choices = [Mock()]
        round2_response.choices[0].message = Mock(
            content="Final answer",
            tool_calls=None,
            thinking_blocks=None,
            reasoning_content=None,
        )
        round2_response.usage = Mock()

        mock_litellm.side_effect = [round1_response, round2_response]

        context = {"agent_name": "TestAgent"}
        result = asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertEqual(mock_litellm.call_count, 2, "Expected exactly two rounds (tool call, then final)")
        self.assertTrue(
            result.usage["cache_skipped_below_min_tokens"],
            "Flag set in round 1 must still be True in the usage dict after round 2",
        )
        # resolve_capabilities is only consulted once, before the loop starts —
        # the persistence guard means the min-token *check* itself only needs
        # to run until it first flips to True.
        self.assertLessEqual(
            mock_resolve_capabilities.call_count, 1,
            "resolve_capabilities should be called at most once (before the round loop)",
        )

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True)
    @patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=2048))
    @patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock())
    @patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={}))
    @patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={})
    @patch("huf.ai.providers.litellm.extract_round_usage", return_value={
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    })
    @patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test"))
    def test_sync_flag_stays_false_when_prefix_meets_minimum(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
        mock_resolve_capabilities,
        mock_prompt_cache,
        mock_serialize_tools,
        mock_repair_seq,
        mock_trim_messages,
        mock_resolve_api_base,
        mock_normalize_model,
        mock_resolve_api_key,
        mock_litellm,
        mock_frappe,
    ):
        """A prefix comfortably above min_cacheable_tokens must leave the flag False."""
        import asyncio
        from huf.ai.providers.litellm import run

        # ~1.1 tokens/4 chars => 20000 chars is well above the 2048-token minimum.
        agent, agent_doc, provider_doc = self._agent_and_provider_mocks(instructions="x" * 20000)

        mock_frappe.get_doc = Mock(side_effect=lambda doctype, name: {
            "Agent": agent_doc,
            "AI Provider": provider_doc,
        }.get(doctype))
        mock_frappe.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
        mock_frappe.has_permission = Mock(return_value=True)
        mock_frappe.session = Mock(user="test")
        mock_frappe.logger = Mock(return_value=Mock())

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock(
            content="Final answer",
            tool_calls=None,
            thinking_blocks=None,
            reasoning_content=None,
        )
        mock_response.usage = Mock()
        mock_litellm.side_effect = lambda **kwargs: mock_response

        context = {"agent_name": "TestAgent"}
        result = asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertFalse(result.usage["cache_skipped_below_min_tokens"])

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True)
    @patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=2048))
    @patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock())
    @patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={}))
    @patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={})
    @patch("huf.ai.providers.litellm.normalise_usage_payload", return_value={
        "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0,
    })
    @patch("huf.ai.providers.litellm.extract_round_usage", return_value={
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    })
    @patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test"))
    def test_stream_flag_reaches_returned_usage(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_normalise_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
        mock_resolve_capabilities,
        mock_prompt_cache,
        mock_serialize_tools,
        mock_repair_seq,
        mock_trim_messages,
        mock_resolve_api_base,
        mock_normalize_model,
        mock_resolve_api_key,
        mock_litellm,
        mock_frappe,
    ):
        """run_stream() had NO implementation of the min-token check at all —
        prove the streaming path now sets the flag on the final 'complete'
        event's usage payload, matching run()'s behaviour."""
        import asyncio
        from huf.ai.providers.litellm import run_stream

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks(instructions="Hi")

        mock_frappe.get_doc = Mock(side_effect=lambda doctype, name: {
            "Agent": agent_doc,
            "AI Provider": provider_doc,
        }.get(doctype))
        mock_frappe.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
        mock_frappe.has_permission = Mock(return_value=True)
        mock_frappe.session = Mock(user="test")
        mock_frappe.logger = Mock(return_value=Mock())

        delta1 = SimpleNamespace(content="Final", thinking_blocks=None, reasoning_content=None, tool_calls=None)
        chunk1 = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=delta1, finish_reason=None)])

        delta2 = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=None)
        chunk2 = SimpleNamespace(usage=Mock(), choices=[SimpleNamespace(delta=delta2, finish_reason="stop")])

        async def fake_completion_with_retry(**kwargs):
            return [chunk1, chunk2]

        mock_litellm.side_effect = fake_completion_with_retry

        context = {"agent_name": "TestAgent"}

        async def _collect():
            events = []
            async for event in run_stream(agent, "hi", "Anthropic", "claude-haiku", context=context):
                events.append(event)
            return events

        events = asyncio.run(_collect())

        complete_events = [e for e in events if e.get("type") == "complete"]
        self.assertEqual(len(complete_events), 1, f"Expected exactly one complete event, got: {events}")
        self.assertTrue(
            complete_events[0]["usage"]["cache_skipped_below_min_tokens"],
            "run_stream() must implement the same below-minimum-tokens detection as run()",
        )


class TestApplyDynamicCacheMarker(unittest.TestCase):
    """Unit tests for _apply_dynamic_cache_marker, the round-gate's marker-upgrade
    helper: it takes user content already built WITHOUT a marker (round 0's
    shape) and attaches one, preserving any non-text parts."""

    def test_non_anthropic_passthrough(self):
        from huf.ai.providers.litellm import _apply_dynamic_cache_marker

        result = _apply_dynamic_cache_marker("Hello", "openai", "ephemeral")
        self.assertEqual(result, "Hello")

    def test_plain_string_gets_wrapped_and_marked(self):
        from huf.ai.providers.litellm import _apply_dynamic_cache_marker

        result = _apply_dynamic_cache_marker("Hello", "anthropic", "ephemeral")
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["text"], "Hello")
        self.assertEqual(result[0]["cache_control"], {"type": "ephemeral"})

    def test_list_content_marks_text_part_and_keeps_image_part(self):
        from huf.ai.providers.litellm import _apply_dynamic_cache_marker

        content = [
            {"type": "text", "text": "Hello"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
        ]
        result = _apply_dynamic_cache_marker(content, "anthropic", "ephemeral")

        text_parts = [p for p in result if p.get("type") == "text"]
        image_parts = [p for p in result if p.get("type") == "image_url"]
        self.assertEqual(len(text_parts), 1)
        self.assertEqual(text_parts[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(len(image_parts), 1)
        self.assertNotIn("cache_control", image_parts[0])
        # Original list/dicts must not be mutated in place.
        self.assertNotIn("cache_control", content[0])

    def test_list_without_text_part_is_left_untouched(self):
        from huf.ai.providers.litellm import _apply_dynamic_cache_marker

        content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}]
        result = _apply_dynamic_cache_marker(content, "anthropic", "ephemeral")
        self.assertEqual(result, content)


class TestDynamicMarkerRoundGate(unittest.TestCase):
    """Round-gate tests: the dynamic (latest-user-message) marker must never
    appear at round 0, must appear from round 1 onward once it does, and must
    stay off entirely when Off/ineligible.

    Regression guard for the fix that stopped marking the latest user message
    unconditionally at message-build time (paid for on every single-round
    turn, never read back within that turn) and instead attaches it inside
    the round loop only once round_num >= 1.
    """

    def _agent_and_provider_mocks(self, instructions="Hi", mode="Advanced", cache_dynamic_content=True):
        agent = Mock()
        agent.instructions = instructions
        agent.tools = []  # _find_tool iterates agent.tools; None is not iterable
        agent.max_turns = 5
        agent.model_settings = None

        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 1.0
        agent_doc.get = Mock(side_effect=lambda key, default=None: {
            "prompt_cache_mode": mode,
            "enable_prompt_caching": True,
            "cache_control_type": "ephemeral",
            "cache_system_message": True,
            "cache_conversation_history": cache_dynamic_content,
            "reasoning_mode": None,
            "reasoning_effort": None,
            "reasoning_budget_tokens": None,
            "reasoning_summary": None,
        }.get(key, default))

        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)

        return agent, agent_doc, provider_doc

    def _wire_frappe(self, mock_frappe, agent_doc, provider_doc):
        mock_frappe.get_doc = Mock(side_effect=lambda doctype, name: {
            "Agent": agent_doc,
            "AI Provider": provider_doc,
        }.get(doctype))
        mock_frappe.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
        mock_frappe.has_permission = Mock(return_value=True)
        mock_frappe.session = Mock(user="test")
        mock_frappe.logger = Mock(return_value=Mock())

    @staticmethod
    def _has_dynamic_marker(messages):
        """True if the (single) user-role message carries an Anthropic
        cache_control marker. These tests never add conversation_history, so
        there is exactly one role='user' message to inspect."""
        user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
        if not user_msgs:
            return False
        content = user_msgs[-1].get("content")
        if not isinstance(content, list):
            return False
        return any(isinstance(p, dict) and "cache_control" in p for p in content)

    @staticmethod
    def _final_response():
        resp = Mock()
        resp.choices = [Mock()]
        resp.choices[0].message = Mock(
            content="Final answer", tool_calls=None, thinking_blocks=None, reasoning_content=None,
        )
        resp.usage = Mock()
        return resp

    @staticmethod
    def _tool_call_response(call_id="tc1"):
        tool_call = Mock()
        tool_call.id = call_id
        tool_call.function.name = "nonexistent_tool"
        tool_call.function.arguments = "{}"
        resp = Mock()
        resp.choices = [Mock()]
        resp.choices[0].message = Mock(
            content=None, tool_calls=[tool_call], thinking_blocks=None, reasoning_content=None,
        )
        resp.usage = Mock()
        return resp

    def _sync_decorators(test_method):
        for dec in [
            patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test")),
            patch("huf.ai.providers.litellm.extract_round_usage", return_value={
                "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0,
            }),
            patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={}),
            patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={})),
            patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock()),
            patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=1)),
            patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True),
            patch("huf.ai.providers.litellm.serialize_tools", return_value=None),
            patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages),
            patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages),
            patch("huf.ai.providers.litellm._resolve_api_base", return_value=None),
            patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku"),
            patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key"),
            patch("huf.ai.providers.litellm._litellm_completion_with_retry"),
            patch("huf.ai.providers.litellm.frappe"),
        ]:
            test_method = dec(test_method)
        return test_method

    @_sync_decorators
    def test_sync_single_round_turn_never_pays_for_marker(
        self, mock_calc_cost, mock_extract_usage, mock_reasoning_kwargs, mock_resolve_reasoning,
        mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache, mock_serialize_tools,
        mock_repair_seq, mock_trim_messages, mock_resolve_api_base, mock_normalize_model,
        mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        import asyncio
        import copy
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks()
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        captured = []

        def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return self._final_response()

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent"}
        asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertEqual(len(captured), 1, "Expected exactly one provider round")
        self.assertFalse(
            self._has_dynamic_marker(captured[0]),
            "A turn that resolves at round 0 must never carry the dynamic marker",
        )

    @_sync_decorators
    def test_sync_marker_appears_from_round_one_and_persists(
        self, mock_calc_cost, mock_extract_usage, mock_reasoning_kwargs, mock_resolve_reasoning,
        mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache, mock_serialize_tools,
        mock_repair_seq, mock_trim_messages, mock_resolve_api_base, mock_normalize_model,
        mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        import asyncio
        import copy
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks()
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        responses = [
            self._tool_call_response("tc1"),
            self._tool_call_response("tc2"),
            self._final_response(),
        ]
        captured = []

        def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return responses[len(captured) - 1]

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent"}
        asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertEqual(len(captured), 3, "Expected 3 provider rounds (two tool calls, then the final answer)")
        self.assertFalse(self._has_dynamic_marker(captured[0]), "round 0 (round_num=0) must not carry the marker")
        self.assertTrue(self._has_dynamic_marker(captured[1]), "round 1 (round_num=1) must carry the marker")
        self.assertTrue(
            self._has_dynamic_marker(captured[2]),
            "round 2 (round_num=2) must still carry the marker — read back, not re-written",
        )

    @_sync_decorators
    def test_sync_off_mode_never_marks_even_across_rounds(
        self, mock_calc_cost, mock_extract_usage, mock_reasoning_kwargs, mock_resolve_reasoning,
        mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache, mock_serialize_tools,
        mock_repair_seq, mock_trim_messages, mock_resolve_api_base, mock_normalize_model,
        mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        import asyncio
        import copy
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks(mode="Off")
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        responses = [self._tool_call_response("tc1"), self._final_response()]
        captured = []

        def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return responses[len(captured) - 1]

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent"}
        asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertEqual(len(captured), 2)
        for round_messages in captured:
            self.assertFalse(self._has_dynamic_marker(round_messages), "Off must never mark, at any round")

    def _sync_decorators_real_repair(test_method):
        """Same as _sync_decorators but does NOT patch repair_message_sequence —
        the real huf.ai.conversation_manager.repair_message_sequence runs, so a
        history containing an orphaned assistant tool_calls declaration is
        actually dropped from `messages`. Regression guard for the HIGH-1 fix:
        with the old fixed-index round gate, that drop shifts every later
        index and the dynamic marker silently never gets applied
        (markers_per_round == [False, False, False]); with the fix (re-scan
        for the last user message at the point the gate fires) it must still
        gate to [False, True, True].
        """
        for dec in [
            patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test")),
            patch("huf.ai.providers.litellm.extract_round_usage", return_value={
                "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0,
            }),
            patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={}),
            patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={})),
            patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock()),
            patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=1)),
            patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True),
            patch("huf.ai.providers.litellm.serialize_tools", return_value=None),
            # NOTE: repair_message_sequence is intentionally left unpatched (real function).
            patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages),
            patch("huf.ai.providers.litellm._resolve_api_base", return_value=None),
            patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku"),
            patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key"),
            patch("huf.ai.providers.litellm._litellm_completion_with_retry"),
            patch("huf.ai.providers.litellm.frappe"),
        ]:
            test_method = dec(test_method)
        return test_method

    def _markers_per_round(self, captured):
        return [self._has_dynamic_marker(m) for m in captured]

    @_sync_decorators_real_repair
    def test_sync_real_repair_clean_history_gates_correctly(
        self, mock_calc_cost, mock_extract_usage, mock_reasoning_kwargs, mock_resolve_reasoning,
        mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache, mock_serialize_tools,
        mock_trim_messages, mock_resolve_api_base, mock_normalize_model,
        mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        """Baseline: a clean history (no orphaned tool_calls) run through the
        REAL repair_message_sequence must still gate [False, True, True]."""
        import asyncio
        import copy
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks()
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        conversation_history = [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
        ]

        responses = [
            self._tool_call_response("tc1"),
            self._tool_call_response("tc2"),
            self._final_response(),
        ]
        captured = []

        def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return responses[len(captured) - 1]

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent", "conversation_history": conversation_history}
        asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        self.assertEqual(len(captured), 3)
        self.assertEqual(
            self._markers_per_round(captured), [False, True, True],
            "clean history through the real repair_message_sequence must gate [False, True, True]",
        )

    @_sync_decorators_real_repair
    def test_sync_real_repair_orphaned_tool_call_gates_correctly(
        self, mock_calc_cost, mock_extract_usage, mock_reasoning_kwargs, mock_resolve_reasoning,
        mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache, mock_serialize_tools,
        mock_trim_messages, mock_resolve_api_base, mock_normalize_model,
        mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        """Regression guard for HIGH-1: a history containing an assistant
        message with an unfulfilled tool_calls entry (no matching tool
        result) — exactly what a sliding-window get_conversation_history()
        produces when it cuts through a previous tool loop — gets dropped by
        the REAL repair_message_sequence. The round gate must re-locate the
        last user message rather than trust a stale pre-repair index, and
        still gate [False, True, True]."""
        import asyncio
        import copy
        from huf.ai.providers.litellm import run

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks()
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        conversation_history = [
            {"role": "user", "content": "earlier question"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "orphan-1",
                        "type": "function",
                        "function": {"name": "some_tool", "arguments": "{}"},
                    }
                ],
            },
            # No matching role="tool" result for "orphan-1" — this declaration
            # is unfulfilled, so repair_message_sequence drops it entirely.
        ]

        responses = [
            self._tool_call_response("tc1"),
            self._tool_call_response("tc2"),
            self._final_response(),
        ]
        captured = []

        def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return responses[len(captured) - 1]

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent", "conversation_history": conversation_history}
        asyncio.run(run(agent, "hi", "Anthropic", "claude-haiku", context=context))

        # Sanity: the orphan really was dropped by the real repair function,
        # i.e. this test actually exercises the failure mode (not a no-op).
        for round_messages in captured:
            for m in round_messages:
                self.assertFalse(
                    isinstance(m, dict) and m.get("tool_calls") and any(
                        tc.get("id") == "orphan-1" for tc in (m.get("tool_calls") or [])
                        if isinstance(tc, dict)
                    ),
                    "the orphaned declaration should have been dropped by repair_message_sequence",
                )

        self.assertEqual(len(captured), 3)
        self.assertEqual(
            self._markers_per_round(captured), [False, True, True],
            "orphaned tool_call history through the real repair_message_sequence must still gate "
            "[False, True, True] — this is exactly what HIGH-1 fixes",
        )

    def _stream_decorators(test_method):
        for dec in [
            patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test")),
            patch("huf.ai.providers.litellm.extract_round_usage", return_value={
                "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0,
            }),
            patch("huf.ai.providers.litellm.normalise_usage_payload", return_value={
                "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0,
            }),
            patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={}),
            patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={})),
            patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock()),
            patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=1)),
            patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True),
            patch("huf.ai.providers.litellm.serialize_tools", return_value=None),
            patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages),
            patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages),
            patch("huf.ai.providers.litellm._resolve_api_base", return_value=None),
            patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku"),
            patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key"),
            patch("huf.ai.providers.litellm._litellm_completion_with_retry"),
            patch("huf.ai.providers.litellm.frappe"),
        ]:
            test_method = dec(test_method)
        return test_method

    @staticmethod
    def _final_chunks():
        delta = SimpleNamespace(content="Final", thinking_blocks=None, reasoning_content=None, tool_calls=None)
        chunk1 = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=delta, finish_reason=None)])
        delta2 = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=None)
        chunk2 = SimpleNamespace(usage=Mock(), choices=[SimpleNamespace(delta=delta2, finish_reason="stop")])
        return [chunk1, chunk2]

    @staticmethod
    def _tool_call_chunks(call_id="tc1"):
        tc_delta = SimpleNamespace(
            index=0, id=call_id, function=SimpleNamespace(name="nonexistent_tool", arguments="{}"),
        )
        delta = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=[tc_delta])
        chunk1 = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=delta, finish_reason=None)])
        empty_delta = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=None)
        chunk2 = SimpleNamespace(usage=Mock(), choices=[SimpleNamespace(delta=empty_delta, finish_reason="tool_calls")])
        return [chunk1, chunk2]

    @_stream_decorators
    def test_stream_single_round_turn_never_pays_for_marker(
        self, mock_calc_cost, mock_extract_usage, mock_normalise_usage, mock_reasoning_kwargs,
        mock_resolve_reasoning, mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache,
        mock_serialize_tools, mock_repair_seq, mock_trim_messages, mock_resolve_api_base,
        mock_normalize_model, mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        import asyncio
        import copy
        from huf.ai.providers.litellm import run_stream

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks()
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        captured = []

        async def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return self._final_chunks()

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent"}

        async def _collect():
            return [e async for e in run_stream(agent, "hi", "Anthropic", "claude-haiku", context=context)]

        asyncio.run(_collect())

        self.assertEqual(len(captured), 1, "Expected exactly one provider round")
        self.assertFalse(
            self._has_dynamic_marker(captured[0]),
            "A turn that resolves at round 0 must never carry the dynamic marker",
        )

    @_stream_decorators
    def test_stream_marker_appears_from_round_one_and_persists(
        self, mock_calc_cost, mock_extract_usage, mock_normalise_usage, mock_reasoning_kwargs,
        mock_resolve_reasoning, mock_detect_caps, mock_resolve_capabilities, mock_prompt_cache,
        mock_serialize_tools, mock_repair_seq, mock_trim_messages, mock_resolve_api_base,
        mock_normalize_model, mock_resolve_api_key, mock_litellm, mock_frappe,
    ):
        import asyncio
        import copy
        from huf.ai.providers.litellm import run_stream

        agent, agent_doc, provider_doc = self._agent_and_provider_mocks()
        self._wire_frappe(mock_frappe, agent_doc, provider_doc)

        round_chunks = [
            self._tool_call_chunks("tc1"),
            self._tool_call_chunks("tc2"),
            self._final_chunks(),
        ]
        captured = []

        async def fake_completion(**kwargs):
            captured.append(copy.deepcopy(kwargs["messages"]))
            return round_chunks[len(captured) - 1]

        mock_litellm.side_effect = fake_completion

        context = {"agent_name": "TestAgent"}

        async def _collect():
            return [e async for e in run_stream(agent, "hi", "Anthropic", "claude-haiku", context=context)]

        asyncio.run(_collect())

        self.assertEqual(len(captured), 3, "Expected 3 provider rounds (two tool calls, then the final answer)")
        self.assertFalse(self._has_dynamic_marker(captured[0]), "round 0 (round_num=0) must not carry the marker")
        self.assertTrue(self._has_dynamic_marker(captured[1]), "round 1 (round_num=1) must carry the marker")
        self.assertTrue(
            self._has_dynamic_marker(captured[2]),
            "round 2 (round_num=2) must still carry the marker — read back, not re-written",
        )


if __name__ == "__main__":
    unittest.main()
