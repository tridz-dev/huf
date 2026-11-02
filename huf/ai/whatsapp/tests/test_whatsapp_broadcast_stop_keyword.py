# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-14: a STOP keyword opt-out skips the contact's pending broadcast rows (WhatsApp gateways only)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service as gs
from huf.ai.whatsapp.broadcast import status as bs


def _gw(provider, name="GW-1"):
	return SimpleNamespace(name=name, provider=provider)


class TestStopKeywordBroadcastSkip(unittest.TestCase):
	def _run(self, provider, side_effect=None):
		with patch.object(gs, "_live_sender_entry", return_value={"name": "E1", "state": "Approved"}), \
			patch.object(gs, "_save_entry") as save, \
			patch.object(gs, "_normalize_sender_for_provider", side_effect=lambda p, k, s: s), \
			patch.object(bs, "apply_user_stop", side_effect=side_effect) as stop, \
			patch.object(gs.frappe, "log_error") as log:
			gs._record_opt_out(_gw(provider), "15551234567")
		return save, stop, log

	def test_whatsapp_triggers_apply_user_stop(self):
		save, stop, _ = self._run("WhatsApp")
		save.assert_called_once()
		stop.assert_called_once_with("GW-1", "15551234567")

	def test_telegram_does_not(self):
		save, stop, _ = self._run("Telegram")
		save.assert_called_once()
		stop.assert_not_called()

	def test_exception_swallowed_and_logged(self):
		save, stop, log = self._run("WhatsApp", side_effect=RuntimeError("boom"))
		save.assert_called_once()
		stop.assert_called_once()
		log.assert_called_once()

	def test_new_entry_path_also_triggers(self):
		doc = MagicMock()
		with patch.object(gs, "_live_sender_entry", return_value=None), \
			patch.object(gs.frappe, "get_doc", return_value=doc), \
			patch.object(gs, "_normalize_sender_for_provider", side_effect=lambda p, k, s: s), \
			patch.object(bs, "apply_user_stop") as stop:
			gs._record_opt_out(_gw("WhatsApp"), "15551234567")
		doc.insert.assert_called_once()
		stop.assert_called_once()
