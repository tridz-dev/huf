# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import unittest
from types import SimpleNamespace
from huf.ai.reasoning import (
    ReasoningPolicy,
    ReasoningCapabilities,
    ReasoningResolution,
    detect_model_capabilities,
    resolve_reasoning,
    build_reasoning_kwargs,
)


class TestReasoningLayer(unittest.TestCase):

    def test_policy_parsing(self):
        p = ReasoningPolicy.from_dict({"reasoning_mode": "On", "reasoning_effort": "High", "reasoning_budget_tokens": 8192})
        self.assertEqual(p.mode, "on")
        self.assertEqual(p.effort, "high")
        self.assertEqual(p.budget_tokens, 8192)

        p_default = ReasoningPolicy.from_dict({})
        self.assertEqual(p_default.mode, "auto")
        self.assertEqual(p_default.effort, "auto")
        self.assertIsNone(p_default.budget_tokens)

    def test_detect_capabilities_heuristics(self):
        caps_r1 = detect_model_capabilities("deepseek-r1", provider="DeepSeek")
        self.assertTrue(caps_r1.supports_reasoning)

        caps_claude = detect_model_capabilities("claude-3-7-sonnet-20250219", provider="Anthropic")
        self.assertTrue(caps_claude.supports_thinking_blocks)

        doc_override = SimpleNamespace(supports_reasoning=True, reasoning_config_override='{"supports_thinking_blocks": true}')
        caps_doc = detect_model_capabilities("custom-model", provider="Custom", ai_model_doc=doc_override)
        self.assertTrue(caps_doc.supports_reasoning)
        self.assertTrue(caps_doc.supports_thinking_blocks)

    def test_resolve_openai_reasoning(self):
        policy = ReasoningPolicy(mode="on", effort="high")
        caps = ReasoningCapabilities(supports_reasoning=True)
        res = resolve_reasoning(policy, caps, provider="OpenAI", model_name="o3-mini")

        self.assertEqual(res.resolved.get("reasoning_effort"), "high")
        self.assertIsNone(res.fallback)

        kwargs = build_reasoning_kwargs(res)
        self.assertEqual(kwargs.get("reasoning_effort"), "high")

    def test_resolve_anthropic_thinking(self):
        policy = ReasoningPolicy(mode="on", effort="high", budget_tokens=4096)
        caps = ReasoningCapabilities(supports_reasoning=True, supports_thinking_blocks=True)
        res = resolve_reasoning(policy, caps, provider="Anthropic", model_name="claude-3-7-sonnet")

        self.assertIn("thinking", res.resolved)
        self.assertEqual(res.resolved["thinking"]["type"], "enabled")
        self.assertEqual(res.resolved["thinking"]["budget_tokens"], 4096)
        self.assertTrue(res.resolved.get("modify_params"))

        kwargs = build_reasoning_kwargs(res)
        self.assertEqual(kwargs.get("thinking"), {"type": "enabled", "budget_tokens": 4096})
        self.assertTrue(kwargs.get("modify_params"))

    def test_fallback_when_unsupported(self):
        policy = ReasoningPolicy(mode="on", effort="high")
        caps = ReasoningCapabilities(supports_reasoning=False)
        res = resolve_reasoning(policy, caps, provider="OpenAI", model_name="gpt-4o")

        self.assertEqual(res.resolved, {})
        self.assertIsNotNone(res.fallback)
        self.assertEqual(res.fallback.get("reason"), "model_does_not_support_reasoning")

    def test_mode_off_returns_empty(self):
        policy = ReasoningPolicy(mode="off", effort="high")
        caps = ReasoningCapabilities(supports_reasoning=True)
        res = resolve_reasoning(policy, caps, provider="OpenAI", model_name="o1")

        self.assertEqual(res.resolved, {})
        self.assertIsNone(res.fallback)


if __name__ == "__main__":
    unittest.main()
