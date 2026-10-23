# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from litellm import BadRequestError

from huf.ai.providers import litellm as prov
from huf.ai.reasoning import (
	ReasoningCapabilities,
	ReasoningPolicy,
	build_reasoning_kwargs,
	requires_adaptive_thinking,
	resolve_reasoning,
)

CAPS = ReasoningCapabilities(supports_reasoning=True, supports_thinking_blocks=True)


def _kwargs(model, mode, effort="auto", budget=None):
	pol = ReasoningPolicy(mode=mode, effort=effort, budget_tokens=budget)
	return build_reasoning_kwargs(resolve_reasoning(pol, CAPS, provider="Anthropic", model_name=model))


class TestAdaptiveThinking(unittest.TestCase):
	def test_family_rule(self):
		for m in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "anthropic/claude-sonnet-5"):
			self.assertTrue(requires_adaptive_thinking(m), m)
		for m in ("claude-haiku-4-5", "claude-sonnet-4-5-20250929", "claude-3-7-sonnet", "gpt-5"):
			self.assertFalse(requires_adaptive_thinking(m), m)

	def test_matrix(self):
		for mode in ("auto", "on"):
			k5 = _kwargs("claude-sonnet-5-5", mode)
			self.assertEqual(k5["thinking"], {"type": "adaptive"})
			self.assertEqual(k5["output_config"], {"effort": "medium"})
			k4 = _kwargs("claude-haiku-4-5", mode, budget=2048)
			self.assertEqual(k4["thinking"], {"type": "enabled", "budget_tokens": 2048})
			self.assertNotIn("output_config", k4)
		self.assertEqual(_kwargs("claude-opus-5-5", "on", "high")["output_config"], {"effort": "high"})
		self.assertEqual(_kwargs("claude-opus-5-5", "auto", "low")["output_config"], {"effort": "low"})
		for m in ("claude-sonnet-5-5", "claude-haiku-4-5"):
			self.assertEqual(_kwargs(m, "off"), {})

	def _bad(self):
		return BadRequestError(
			message='"thinking.type.enabled" is not supported for this model. Use "thinking.type.adaptive"',
			model="claude-x",
			llm_provider="anthropic",
			response=MagicMock(),
		)

	def test_retry_on_400(self):
		calls = []

		def fake(**kw):
			calls.append(kw)
			if len(calls) == 1:
				raise self._bad()
			return "ok"

		with patch.object(prov.litellm, "completion", side_effect=fake):
			out = asyncio.run(
				prov._litellm_completion_with_retry(
					model="anthropic/claude-x",
					thinking={"type": "enabled", "budget_tokens": 4096},
					stream=True,
				)
			)
		self.assertEqual(out, "ok")
		self.assertEqual(len(calls), 2)
		self.assertEqual(calls[1]["thinking"], {"type": "adaptive"})
		self.assertEqual(calls[1]["output_config"], {"effort": "medium"})
		self.assertTrue(calls[1]["stream"])

	def test_no_retry_without_thinking(self):
		with patch.object(prov.litellm, "completion", side_effect=self._bad()) as m:
			with self.assertRaises(BadRequestError):
				asyncio.run(prov._litellm_completion_with_retry(model="x"))
		self.assertEqual(m.call_count, 1)

	def test_streaming_and_nonstreaming_kwargs_pass_through(self):
		for stream in (True, False):
			with patch.object(prov.litellm, "completion", return_value="r") as m:
				kw = dict(
					model="anthropic/claude-sonnet-5-5", stream=stream, **_kwargs("claude-sonnet-5-5", "auto")
				)
				asyncio.run(prov._litellm_completion_with_retry(**kw))
			sent = m.call_args.kwargs
			self.assertEqual(sent["thinking"], {"type": "adaptive"})
			self.assertEqual(sent["output_config"], {"effort": "medium"})
			self.assertEqual(sent["stream"], stream)


if __name__ == "__main__":
	unittest.main()
