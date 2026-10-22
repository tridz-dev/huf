"""Terminal event state survives a deadlocked Gateway stamp; a repaired event keeps its reply id."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai import gateway_service as gs
from huf.ai import gateway_webhook as gw
from huf.ai.gateway_adapters import telegram_pipeline as tp


def _db():
	"""Swap the (unbound without a site) ``frappe.db`` proxy for a mock in the frappe module dict."""
	return mock.patch.dict(frappe.__dict__, {"db": mock.MagicMock()})


_NOW = mock.patch("frappe.utils.now_datetime", return_value=__import__("datetime").datetime(2026, 1, 1))


class TestTouchLastEvent(unittest.TestCase):
	def test_deadlock_is_retried_and_never_raises(self):
		calls = []

		def set_value(*a, **k):
			calls.append(1)
			if len(calls) < 3:
				raise frappe.QueryDeadlockError("Deadlock found")

		with _db(), _NOW, mock.patch("time.sleep"):
			db = frappe.db
			db.get_value.return_value = None
			db.set_value.side_effect = set_value
			gw.touch_last_event("GW-1")
			db.rollback.assert_not_called()
		self.assertEqual(len(calls), 3)

	def test_persistent_deadlock_logs_warning_type_only(self):
		logger = mock.Mock()
		with _db(), _NOW, mock.patch("time.sleep"), mock.patch.object(
			gw.frappe, "logger", return_value=logger
		):
			db = frappe.db
			db.get_value.return_value = None
			db.set_value.side_effect = frappe.QueryDeadlockError("secret detail")
			gw.touch_last_event("GW-1")
			db.rollback.assert_not_called()
		logger.warning.assert_called_once_with("touch_last_event failed: %s", "QueryDeadlockError")


class TestCommitOrder(unittest.TestCase):
	def test_event_committed_before_touch(self):
		order = []
		event = mock.Mock(reply_message_id="m1", agent_run="R", name="E1")
		event.db_set.side_effect = lambda *a, **k: order.append("event")
		svc = SimpleNamespace(
			_throttle_outbound_send=mock.Mock(),
			_outbound_rate_cap=mock.Mock(),
			_record_reply_sent=mock.Mock(),
			_commit_unless_testing=lambda: order.append("commit"),
		)
		gateway = SimpleNamespace(name="GW", provider="Telegram")
		with mock.patch.object(tp, "_svc", return_value=svc), mock.patch.object(
			tp, "before_send", side_effect=lambda e, g, p: p
		), mock.patch.object(
			tp, "send_parts", return_value=SimpleNamespace(provider_message_id="m2")
		), _db(), mock.patch(
			"huf.ai.gateway_webhook.touch_last_event", side_effect=lambda g: order.append("touch")
		):
			frappe.db.get_value.return_value = "sent"
			res = tp.attempt_parts(event, gateway, ["hi"], 1)
		self.assertEqual(res["status"], "Succeeded")
		self.assertEqual(order[-3:], ["event", "commit", "touch"])


class TestRepair(unittest.TestCase):
	def test_repair_restores_reply_message_id_and_status(self):
		result = {"status": "Succeeded", "agent_run_id": "RUN", "provider_message_id": "tg-9"}
		lost = {"status": "Running", "agent_run": None, "reply_message_id": None, "reply_status": None}
		with _db(), mock.patch.object(gs.frappe, "log_error"), mock.patch.object(gs, "_commit_unless_testing"):
			db = frappe.db
			db.get_value.return_value = lost
			gs._persist_terminal_state("E1", result)
			db.set_value.assert_called_once_with(
				"Gateway Event",
				"E1",
				{"status": "Succeeded", "agent_run": "RUN", "reply_message_id": "tg-9", "reply_status": "sent"},
			)

	def test_no_repair_when_intact(self):
		result = {"status": "Succeeded", "agent_run_id": "RUN", "provider_message_id": "tg-9"}
		ok = {"status": "Succeeded", "agent_run": "RUN", "reply_message_id": "tg-9", "reply_status": "sent"}
		with _db(), mock.patch.object(gs.frappe, "log_error") as le, mock.patch.object(gs, "_commit_unless_testing"):
			db = frappe.db
			db.get_value.return_value = ok
			gs._persist_terminal_state("E1", result)
			db.set_value.assert_not_called()
			le.assert_not_called()
