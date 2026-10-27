# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from litellm import BadRequestError

from huf.ai.providers import litellm as prov
from huf.ai.reasoning import rejects_sampling_params


def _bad(message):
	return BadRequestError(
		message=message, model="claude-haiku-5-5", llm_provider="anthropic", response=MagicMock()
	)


class TestRejectsSamplingParams(unittest.TestCase):
	def test_family_rule(self):
		for m in ("claude-haiku-5-5", "claude-sonnet-5-5", "anthropic/claude-opus-5"):
			self.assertTrue(rejects_sampling_params(m), m)
		for m in ("claude-haiku-4-5", "claude-3-7-sonnet", "gpt-5", "gpt-4o"):
			self.assertFalse(rejects_sampling_params(m), m)


class TestDropSamplingParams(unittest.TestCase):
	def _kwargs(self):
		return {"model": "m", "messages": [], "temperature": 0.3, "top_p": 0.9, "top_k": 40}

	def test_drops_for_claude_5(self):
		kw = self._kwargs()
		prov._drop_sampling_params_if_rejected(kw, "anthropic/claude-haiku-5-5")
		for key in ("temperature", "top_p", "top_k"):
			self.assertNotIn(key, kw)

	def test_keeps_for_claude_4_and_gpt(self):
		for m in ("anthropic/claude-haiku-4-5", "gpt-5", "gpt-4o"):
			kw = self._kwargs()
			prov._drop_sampling_params_if_rejected(kw, m)
			self.assertEqual(kw["temperature"], 0.3, m)
			self.assertEqual(kw["top_p"], 0.9, m)


class TestSamplingRejectionMessage(unittest.TestCase):
	def test_temperature_deprecated(self):
		kw = {"temperature": 0.3, "top_p": 0.9}
		self.assertEqual(
			prov._sampling_keys_rejected("`temperature` is deprecated for this model", kw), ["temperature"]
		)

	def test_top_p_not_supported(self):
		kw = {"temperature": 0.3, "top_p": 0.9}
		self.assertEqual(prov._sampling_keys_rejected("top_p is not supported for this model", kw), ["top_p"])

	def test_unrelated_message_no_match(self):
		kw = {"temperature": 0.3}
		self.assertEqual(prov._sampling_keys_rejected("max_tokens too large", kw), [])


class TestSamplingRetry(unittest.TestCase):
	def test_retry_without_temperature_on_deprecated(self):
		calls = []

		def fake(**kw):
			calls.append(kw)
			if len(calls) == 1:
				raise _bad("`temperature` is deprecated for this model")
			return "ok"

		with patch.object(prov.litellm, "completion", side_effect=fake):
			out = asyncio.run(
				prov._litellm_completion_with_retry(
					model="anthropic/claude-haiku-5-5", temperature=0.3, top_p=0.9, messages=[]
				)
			)
		self.assertEqual(out, "ok")
		self.assertEqual(len(calls), 2)
		self.assertIn("temperature", calls[0])
		self.assertNotIn("temperature", calls[1])
		self.assertEqual(calls[1]["top_p"], 0.9)

	def test_retry_without_top_p_when_not_supported(self):
		calls = []

		def fake(**kw):
			calls.append(kw)
			if len(calls) == 1:
				raise _bad("top_p is not supported for this model")
			return "ok"

		with patch.object(prov.litellm, "completion", side_effect=fake):
			asyncio.run(
				prov._litellm_completion_with_retry(model="x", temperature=0.3, top_p=0.9, messages=[])
			)
		self.assertEqual(len(calls), 2)
		self.assertNotIn("top_p", calls[1])
		self.assertEqual(calls[1]["temperature"], 0.3)

	def test_no_retry_for_unrelated_bad_request(self):
		with patch.object(prov.litellm, "completion", side_effect=_bad("max_tokens too large")) as m:
			with self.assertRaises(BadRequestError):
				asyncio.run(prov._litellm_completion_with_retry(model="x", temperature=0.3, messages=[]))
		self.assertEqual(m.call_count, 1)

	def test_bad_request_retry_gets_transient_handling(self):
		calls = []

		def fake(**kw):
			calls.append(kw)
			if len(calls) == 1:
				raise _bad("top_p is not supported for this model")
			if len(calls) == 2:
				raise ConnectionResetError("connection reset by peer")
			return "ok"

		with patch.object(prov.litellm, "completion", side_effect=fake):
			out = asyncio.run(
				prov._litellm_completion_with_retry(model="x", top_p=0.9, messages=[], _huf_base_delay=0)
			)
		self.assertEqual(out, "ok")
		self.assertEqual(len(calls), 3)
		self.assertNotIn("top_p", calls[1])
		self.assertNotIn("top_p", calls[2])


if __name__ == "__main__":
	unittest.main()
