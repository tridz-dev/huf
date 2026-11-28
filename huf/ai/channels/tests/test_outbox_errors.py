"""Channel outbox error classes and backoff (outbox_errors): pure, bench-less."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from huf.ai.channels.outbound import outbox_errors as errors
from huf.ai.channels.outbound import recipient_binder, token_binder


class TestOutboxErrors(unittest.TestCase):
	def test_classify_dict_retryable(self):
		self.assertEqual(errors.classify({"retryable": True}), errors.TRANSIENT)
		self.assertEqual(errors.classify({"retryable": False}), errors.PERMANENT)

	def test_classify_block_codes(self):
		self.assertEqual(errors.classify("frequency_capped"), errors.BLOCKED)
		self.assertEqual(errors.classify(token_binder.TokenUnbound(["1"])), errors.BLOCKED)
		self.assertEqual(errors.classify(recipient_binder.RecipientUnbound()), errors.BLOCKED)

	def test_delivery_error_block_code_is_guard(self):
		self.assertEqual(
			errors.delivery_error("frequency_capped"),
			{"class": errors.BLOCKED, "code": "frequency_capped", "kind": "guard"},
		)

	def test_delivery_error_keeps_codes_only(self):
		err = errors.delivery_error({"retryable": False, "code": 131026, "kind": "template"})
		self.assertEqual(err, {"class": errors.PERMANENT, "code": "131026", "kind": "template"})
		self.assertEqual(set(err), {"class", "code", "kind"})

	def test_delivery_error_unknown_kind_defaults(self):
		err = errors.delivery_error({"retryable": True})
		self.assertEqual(err, {"class": errors.TRANSIENT, "code": "unknown", "kind": "unknown"})

	def test_delivery_error_not_posting_is_never_ambiguous(self):
		with patch.object(errors, "_classify_exception", return_value={"retryable": True, "code": "x"}):
			with patch.object(errors, "_outcome_unknown", return_value=True):
				err = errors.delivery_error(ValueError("boom"), posting=False)
		self.assertEqual(err["class"], errors.TRANSIENT)

	def test_delivery_error_posted_unknown_outcome_is_ambiguous(self):
		with patch.object(errors, "_classify_exception", return_value={"retryable": True, "code": "timeout"}):
			with patch.object(errors, "_outcome_unknown", return_value=True):
				err = errors.delivery_error(ValueError("boom"))
		self.assertEqual(err["class"], errors.AMBIGUOUS)
		self.assertEqual(err["code"], "timeout")

	def test_backoff_starts_at_base_and_doubles(self):
		self.assertEqual(errors.backoff_seconds(0), errors.BACKOFF_BASE_S)
		self.assertEqual(errors.backoff_seconds(1), errors.BACKOFF_BASE_S)
		self.assertEqual(errors.backoff_seconds(2), 2 * errors.BACKOFF_BASE_S)
		self.assertEqual(errors.backoff_seconds(3), 4 * errors.BACKOFF_BASE_S)

	def test_backoff_monotonic_and_capped(self):
		delays = [errors.backoff_seconds(n) for n in range(1, 40)]
		self.assertEqual(delays, sorted(delays))
		self.assertEqual(max(delays), errors.BACKOFF_MAX_S)
		self.assertEqual(delays[-1], errors.BACKOFF_MAX_S)

	def test_classify_exception_passthrough(self):
		classification = {"kind": "rate_limit", "retryable": True, "code": 80007}
		with patch(
			"huf.ai.gateway_adapters.whatsapp_parts.send_errors.classify_send_exception",
			return_value=classification,
		):
			self.assertEqual(errors._classify_exception(RuntimeError("x")), classification)

	def test_classify_exception_unclassifiable_is_permanent(self):
		with patch(
			"huf.ai.gateway_adapters.whatsapp_parts.send_errors.classify_send_exception",
			side_effect=RuntimeError("bad"),
		):
			self.assertEqual(
				errors._classify_exception(RuntimeError("x")),
				{"kind": "unknown", "retryable": False},
			)
