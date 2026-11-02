"""A chat trigger's sample message matches the trigger's own word filters (so a test shows a message that would start it)."""

import unittest

from huf.ai.flow.gateways.samples_api import _fit_filters


class TestFitFilters(unittest.TestCase):
	def test_command_sets_command_args_and_text(self):
		sample = {"text": "Hi", "command": "", "command_args": ""}
		_fit_filters(sample, [{"key": "commands", "value": ["/start"]}])
		self.assertEqual((sample["command"], sample["command_args"], sample["text"]), ("start", "hello", "/start hello"))

	def test_keyword_is_added_only_when_missing(self):
		sample = {"text": "Hi, is my order ready?"}
		_fit_filters(sample, [{"key": "keywords", "value": ["Order"]}])
		self.assertEqual(sample["text"], "Hi, is my order ready?")
		sample = {"text": "Hello"}
		_fit_filters(sample, [{"key": "keywords", "value": ["refund"]}])
		self.assertTrue(sample["text"].startswith("refund"))

	def test_no_filters_changes_nothing(self):
		sample = {"text": "Hi"}
		_fit_filters(sample, None)
		self.assertEqual(sample, {"text": "Hi"})


if __name__ == "__main__":
	unittest.main()
