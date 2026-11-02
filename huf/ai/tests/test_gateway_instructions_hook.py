# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Gateway ``agent_instructions`` hook dispatch: signature-based, failures yield no channel note."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai import gateway_service

GW = SimpleNamespace(name="gw-1", provider="Telegram")


class TestCallInstructionsHook(unittest.TestCase):
	def _call(self, hook):
		with patch.object(gateway_service.frappe, "logger") as logger:
			res = gateway_service._call_instructions_hook(hook, GW)
		return res, logger

	def test_hook_with_gateway_arg_receives_gateway(self):
		seen = []

		def hook(gateway=None):
			seen.append(gateway)
			return "note"

		res, _ = self._call(hook)
		self.assertEqual(res, "note")
		self.assertEqual(seen, [GW])

	def test_no_arg_hook_called_without_gateway(self):
		def hook():
			return "legacy note"

		res, _ = self._call(hook)
		self.assertEqual(res, "legacy note")

	def test_hook_raising_type_error_internally_gives_no_note(self):
		calls = []

		def hook(gateway=None):
			calls.append(1)
			raise TypeError("internal bug")

		res, logger = self._call(hook)
		self.assertIsNone(res)
		# Must not retry with a no-arg call (the old except-TypeError path did, re-raising a different error).
		self.assertEqual(len(calls), 1)
		logger.return_value.warning.assert_called_once()

	def test_hook_raising_other_error_gives_no_note_and_redacts_message(self):
		def hook(gateway=None):
			raise RuntimeError("bot secret 123456:SECRET-TOKEN-XYZ")

		res, logger = self._call(hook)
		self.assertIsNone(res)
		logged = logger.return_value.warning.call_args[0][0]
		self.assertIn("Telegram", logged)
		self.assertIn("RuntimeError", logged)
		self.assertNotIn("SECRET-TOKEN", logged)

	def test_empty_note_passes_through(self):
		res, _ = self._call(lambda gateway=None: "")
		self.assertEqual(res, "")
