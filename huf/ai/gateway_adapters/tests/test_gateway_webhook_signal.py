"""Webhook health signals: throttled, timestamp-only writes for signature failures and verify success."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_webhook

NOW = datetime(2026, 10, 14, 12, 0, 0)


class _Gateway(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def set(self, key, value):
		setattr(self, key, value)


def _frappe(now=NOW):
	f = MagicMock()
	f.utils.now_datetime.return_value = now
	f.utils.get_datetime.side_effect = lambda v: v
	return f


class TestRecordWebhookSignal(unittest.TestCase):
	def test_writes_only_a_timestamp(self):
		f = _frappe()
		gw = _Gateway(name="GW", provider="WhatsApp", last_signature_failure_at=None)
		with patch.object(gateway_webhook, "frappe", f):
			gateway_webhook._record_webhook_signal(gw, "last_signature_failure_at")
		f.db.set_value.assert_called_once_with(
			"Gateway", "GW", "last_signature_failure_at", NOW, update_modified=False
		)

	def test_throttled_within_a_minute_then_writes_again(self):
		f = _frappe()
		gw = _Gateway(name="GW", provider="WhatsApp", last_signature_failure_at=None)
		with patch.object(gateway_webhook, "frappe", f):
			for _ in range(50):  # unauthenticated flood
				gateway_webhook._record_webhook_signal(gw, "last_signature_failure_at")
			self.assertEqual(f.db.set_value.call_count, 1)
			f.utils.now_datetime.return_value = NOW + timedelta(seconds=61)
			gateway_webhook._record_webhook_signal(gw, "last_signature_failure_at")
			self.assertEqual(f.db.set_value.call_count, 2)

	def test_db_failure_never_raises(self):
		f = _frappe()
		f.db.set_value.side_effect = RuntimeError("db down")
		gw = _Gateway(name="GW", provider="WhatsApp", last_verify_ok_at=None)
		with patch.object(gateway_webhook, "frappe", f):
			gateway_webhook._record_webhook_signal(gw, "last_verify_ok_at")


class FakeResponse:
	http_status_code = 200


class TestHandlerRecords(unittest.TestCase):
	def _run(self, method, adapter, provider="WhatsApp"):
		f = _frappe()
		f.request = SimpleNamespace(args={"gateway_name": "GW"})
		f.local = SimpleNamespace(response=FakeResponse())
		f.PermissionError = PermissionError
		gw = _Gateway(name="GW", provider=provider, is_enabled=1, last_signature_failure_at=None, last_verify_ok_at=None)
		f.get_doc.return_value = gw
		req = SimpleNamespace(method=method, headers={"X-Hub-Signature-256": "sha256=bad"}, body=b"{}", query={})
		with patch.object(gateway_webhook, "frappe", f), patch.object(
			gateway_webhook, "get_gateway_adapter", return_value=adapter
		), patch.object(gateway_webhook, "_inbound_request", return_value=req), patch.object(
			gateway_webhook, "_ingest_rate_gate"
		), patch.object(gateway_webhook, "_text_response"):
			result = gateway_webhook.handle_gateway_webhook()
		return f, result

	def test_bad_signature_is_401_and_recorded(self):
		adapter = SimpleNamespace(verify_inbound=lambda r: False)
		f, result = self._run("POST", adapter)
		self.assertEqual(f.local.response.http_status_code, 401)
		self.assertFalse(result["success"])
		args = f.db.set_value.call_args[0]
		self.assertEqual(args[:3], ("Gateway", "GW", "last_signature_failure_at"))

	def test_bad_verify_token_recorded_and_good_verify_stamped(self):
		def bad(_r):
			raise PermissionError("mismatch")

		f, _ = self._run("GET", SimpleNamespace(verify_url=bad, verify_inbound=lambda r: False))
		self.assertEqual(f.db.set_value.call_args[0][2], "last_signature_failure_at")
		f, result = self._run("GET", SimpleNamespace(verify_url=lambda r: "42", verify_inbound=lambda r: True))
		self.assertIsNone(result)
		self.assertEqual(f.db.set_value.call_args[0][2], "last_verify_ok_at")

	def test_other_providers_are_untouched(self):
		adapter = SimpleNamespace(verify_inbound=lambda r: False)
		f, _ = self._run("POST", adapter, provider="Slack")
		f.db.set_value.assert_not_called()
