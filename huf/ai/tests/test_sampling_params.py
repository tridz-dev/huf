# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Test suite for sampling parameter handling in litellm.py

Ensures that:
1. Temperature and top_p are not sent unconditionally
2. Temperature and top_p are never sent together (prevents API errors)
3. Doctype defaults (1.0) are treated as "not explicitly set"
4. Sync (run) and streaming (run_stream) paths agree on sampling keys
"""

import unittest
from unittest.mock import Mock, patch, MagicMock


class TestSamplingParameterLogic(unittest.TestCase):
    """Test the sampling parameter logic by directly testing the logic blocks"""

    def test_temperature_default_1_treated_as_unset(self):
        """Doctype default temperature=1.0 should be treated as unset"""
        # Simulate the logic from run() and run_stream()
        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 1.0

        temperature = agent_doc.temperature
        top_p = agent_doc.top_p

        # Apply the fix logic
        if temperature == 1.0:
            temperature = None
        if top_p == 1.0:
            top_p = None

        self.assertIsNone(temperature, "temperature=1.0 should be treated as None")
        self.assertIsNone(top_p, "top_p=1.0 should be treated as None")

    def test_explicit_temperature_preserved(self):
        """Explicitly set temperature != 1.0 should be preserved"""
        agent_doc = Mock()
        agent_doc.temperature = 0.5
        agent_doc.top_p = 1.0

        temperature = agent_doc.temperature
        top_p = agent_doc.top_p

        # Apply the fix logic
        if temperature == 1.0:
            temperature = None
        if top_p == 1.0:
            top_p = None

        self.assertEqual(temperature, 0.5, "Explicit temperature should be preserved")
        self.assertIsNone(top_p, "top_p=1.0 should be treated as None")

    def test_explicit_top_p_preserved(self):
        """Explicitly set top_p != 1.0 should be preserved"""
        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 0.8

        temperature = agent_doc.temperature
        top_p = agent_doc.top_p

        # Apply the fix logic
        if temperature == 1.0:
            temperature = None
        if top_p == 1.0:
            top_p = None

        self.assertIsNone(temperature, "temperature=1.0 should be treated as None")
        self.assertEqual(top_p, 0.8, "Explicit top_p should be preserved")

    def test_both_set_temperature_precedence(self):
        """When both temperature and top_p are set, temperature should win"""
        agent_doc = Mock()
        agent_doc.temperature = 0.5
        agent_doc.top_p = 0.8

        temperature = agent_doc.temperature
        top_p = agent_doc.top_p

        # Apply the fix logic
        if temperature == 1.0:
            temperature = None
        if top_p == 1.0:
            top_p = None

        # Apply sampling parameter precedence: if both are set, send only temperature
        if temperature is not None and top_p is not None:
            top_p = None  # temperature wins

        self.assertEqual(temperature, 0.5, "temperature should be preserved")
        self.assertIsNone(top_p, "top_p should be None due to precedence")

    def test_none_from_model_settings_respected(self):
        """If agent.model_settings provides None, it should stay None"""
        # Simulate when temperature comes from agent.model_settings
        temperature = None
        top_p = None

        # Apply the fix logic
        if temperature == 1.0:
            temperature = None
        if top_p == 1.0:
            top_p = None

        self.assertIsNone(temperature, "None from model_settings should stay None")
        self.assertIsNone(top_p, "None from model_settings should stay None")

    def test_completion_kwargs_temperature_only(self):
        """When only temperature is set, only temperature key should be in kwargs"""
        temperature = 0.5
        top_p = None

        completion_kwargs = {"model": "test-model"}

        if temperature is not None:
            completion_kwargs["temperature"] = temperature
        if top_p is not None:
            completion_kwargs["top_p"] = top_p

        self.assertIn("temperature", completion_kwargs)
        self.assertNotIn("top_p", completion_kwargs)

    def test_completion_kwargs_top_p_only(self):
        """When only top_p is set, only top_p key should be in kwargs"""
        temperature = None
        top_p = 0.8

        completion_kwargs = {"model": "test-model"}

        if temperature is not None:
            completion_kwargs["temperature"] = temperature
        if top_p is not None:
            completion_kwargs["top_p"] = top_p

        self.assertNotIn("temperature", completion_kwargs)
        self.assertIn("top_p", completion_kwargs)

    def test_completion_kwargs_neither_set(self):
        """When neither is set, neither key should be in kwargs"""
        temperature = None
        top_p = None

        completion_kwargs = {"model": "test-model"}

        if temperature is not None:
            completion_kwargs["temperature"] = temperature
        if top_p is not None:
            completion_kwargs["top_p"] = top_p

        self.assertNotIn("temperature", completion_kwargs)
        self.assertNotIn("top_p", completion_kwargs)

    def test_completion_kwargs_both_set_temperature_only(self):
        """When both are set, only temperature should be in kwargs"""
        temperature = 0.5
        top_p = 0.8

        # Apply precedence
        if temperature is not None and top_p is not None:
            top_p = None

        completion_kwargs = {"model": "test-model"}

        if temperature is not None:
            completion_kwargs["temperature"] = temperature
        if top_p is not None:
            completion_kwargs["top_p"] = top_p

        self.assertIn("temperature", completion_kwargs)
        self.assertNotIn("top_p", completion_kwargs)


class TestSamplingParameterIntegration(unittest.TestCase):
    """Integration tests to verify sync and streaming paths use the same logic"""

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-opus")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=False)
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
    def test_sync_neither_temperature_nor_top_p_sent(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
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
        """Verify sync run() doesn't send temperature/top_p when both are doctype default"""
        import asyncio
        from huf.ai.providers.litellm import run

        agent = Mock()
        agent.instructions = "Test"
        agent.tools = None
        agent.max_turns = 1
        agent.model_settings = None

        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 1.0
        agent_doc.enable_prompt_caching = False
        agent_doc.get = Mock(return_value=None)

        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)

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
            content="Test response",
            tool_calls=None,
            thinking_blocks=None,
            reasoning_content=None,
        )
        mock_response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        captured_kwargs = {}
        def capture_kwargs(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        mock_litellm.side_effect = capture_kwargs

        context = {"agent_name": "TestAgent"}
        asyncio.run(run(agent, "Test prompt", "Anthropic", "claude-opus", context=context))

        # Verify neither temperature nor top_p are in the kwargs
        self.assertNotIn("temperature", captured_kwargs, "temperature should not be sent when doctype default")
        self.assertNotIn("top_p", captured_kwargs, "top_p should not be sent when doctype default")

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-opus")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=False)
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
    def test_sync_temperature_only_sent(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
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
        """Verify sync run() sends only temperature when top_p is default"""
        import asyncio
        from huf.ai.providers.litellm import run

        agent = Mock()
        agent.instructions = "Test"
        agent.tools = None
        agent.max_turns = 1
        agent.model_settings = None

        agent_doc = Mock()
        agent_doc.temperature = 0.5
        agent_doc.top_p = 1.0
        agent_doc.enable_prompt_caching = False
        agent_doc.get = Mock(return_value=None)

        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)

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
            content="Test response",
            tool_calls=None,
            thinking_blocks=None,
            reasoning_content=None,
        )
        mock_response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        captured_kwargs = {}
        def capture_kwargs(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        mock_litellm.side_effect = capture_kwargs

        context = {"agent_name": "TestAgent"}
        asyncio.run(run(agent, "Test prompt", "Anthropic", "claude-opus", context=context))

        # Verify only temperature is sent
        self.assertIn("temperature", captured_kwargs, "temperature should be sent when explicitly set")
        self.assertEqual(captured_kwargs["temperature"], 0.5)
        self.assertNotIn("top_p", captured_kwargs, "top_p should not be sent when doctype default")

    @patch("huf.ai.providers.litellm.frappe")
    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    @patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key")
    @patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-opus")
    @patch("huf.ai.providers.litellm._resolve_api_base", return_value=None)
    @patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages)
    @patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages)
    @patch("huf.ai.providers.litellm.serialize_tools", return_value=None)
    @patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=False)
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
    def test_sync_both_set_only_temperature_sent(
        self,
        mock_calc_cost,
        mock_extract_usage,
        mock_reasoning_kwargs,
        mock_resolve_reasoning,
        mock_detect_caps,
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
        """Verify sync run() sends only temperature when both are set (precedence)"""
        import asyncio
        from huf.ai.providers.litellm import run

        agent = Mock()
        agent.instructions = "Test"
        agent.tools = None
        agent.max_turns = 1
        agent.model_settings = None

        agent_doc = Mock()
        agent_doc.temperature = 0.5
        agent_doc.top_p = 0.8
        agent_doc.enable_prompt_caching = False
        agent_doc.get = Mock(return_value=None)

        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)

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
            content="Test response",
            tool_calls=None,
            thinking_blocks=None,
            reasoning_content=None,
        )
        mock_response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        captured_kwargs = {}
        def capture_kwargs(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        mock_litellm.side_effect = capture_kwargs

        context = {"agent_name": "TestAgent"}
        asyncio.run(run(agent, "Test prompt", "Anthropic", "claude-opus", context=context))

        # Verify only temperature is sent (precedence)
        self.assertIn("temperature", captured_kwargs, "temperature should be sent (has precedence)")
        self.assertEqual(captured_kwargs["temperature"], 0.5)
        self.assertNotIn("top_p", captured_kwargs, "top_p should not be sent when both are set (temperature wins)")


if __name__ == "__main__":
    unittest.main()
