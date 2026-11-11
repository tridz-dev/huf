"""huf_gateway_opt_out fires once per real consent transition (external apps learn about STOP/START)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service as gs

GW = SimpleNamespace(name="GW", provider="Telegram")


def _opted_out(state):
	return {"name": "E1", "state": state, "previous_state": "Approved"}


class TestOptOutHook(unittest.TestCase):
	def _out(self, row, **kw):
		with (
			patch.object(gs, "_live_sender_entry", return_value=row),
			patch.object(gs, "_save_entry"),
			patch.object(gs.frappe, "get_doc", return_value=MagicMock()),
			patch.object(gs, "fire_hook") as fh,
		):
			gs._record_opt_out(GW, "123", keyword="stop", **kw)
		return fh

	def test_stop_fires_opt_out_once(self):
		fh = self._out(_opted_out("Approved"))
		fh.assert_called_once_with("huf_gateway_opt_out", gateway="GW", sender_id="123", kind="opt_out", keyword="stop")

	def test_stop_without_entry_fires(self):
		self.assertEqual(self._out(None).call_count, 1)

	def test_second_stop_fires_nothing(self):
		self.assertEqual(self._out(_opted_out("Opted out")).call_count, 0)

	def test_start_fires_opt_in(self):
		with (
			patch.object(gs, "_live_sender_entry", return_value=_opted_out("Opted out")),
			patch.object(gs, "_save_entry"),
			patch.object(gs, "fire_hook") as fh,
		):
			gs._record_opt_in(GW, "123", keyword="start")
		fh.assert_called_once_with("huf_gateway_opt_out", gateway="GW", sender_id="123", kind="opt_in", keyword="start")

	def test_start_without_prior_opt_out_fires_nothing(self):
		with (
			patch.object(gs, "_live_sender_entry", return_value=_opted_out("Approved")),
			patch.object(gs, "_save_entry"),
			patch.object(gs, "fire_hook") as fh,
		):
			gs._record_opt_in(GW, "123", keyword="start")
		fh.assert_not_called()

	def test_linked_stop_fires_once_for_primary(self):
		event = SimpleNamespace(raw_payload={})
		with (
			patch.object(gs, "_raw_bsuid", return_value="IN.9"),
			patch.object(gs, "_live_sender_entry", return_value=_opted_out("Approved")),
			patch.object(gs, "_save_entry"),
			patch.object(gs, "fire_hook") as fh,
		):
			gs._record_opt_out_linked(GW, event, "123", keyword="stop")
		fh.assert_called_once_with("huf_gateway_opt_out", gateway="GW", sender_id="123", kind="opt_out", keyword="stop")

	def test_linked_start_fires_once_for_primary(self):
		with (
			patch.object(gs, "_linked_sender_ids", return_value=["123", "IN.9"]),
			patch.object(gs, "_live_sender_entry", return_value=_opted_out("Opted out")),
			patch.object(gs, "_save_entry"),
			patch.object(gs, "fire_hook") as fh,
		):
			gs._record_opt_in_linked(GW, "123", keyword="start")
		fh.assert_called_once_with("huf_gateway_opt_out", gateway="GW", sender_id="123", kind="opt_in", keyword="start")
