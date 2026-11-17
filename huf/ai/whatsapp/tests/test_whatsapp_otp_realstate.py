"""OTP against the REAL Redis cache and DB (the unit suite uses a dict-backed fake cache).

Covers idempotency_conflict, rate-limit refund, and a scan of every text column for the code after the
WhatsApp and SMS-fallback paths ran (twilio mode mocked).

Run: bench --site test_site run-tests --app huf --module huf.ai.whatsapp.tests.test_whatsapp_otp_realstate
"""

import logging
import random
import secrets
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import otp
from huf.ai.whatsapp.tests import test_whatsapp_otp as base

CODE = "SNTL" + secrets.token_hex(3).upper()


def _phone() -> str:
	return "9199" + "".join(str(random.randint(0, 9)) for _ in range(8))


class TestOtpRealState(base.TestOtp):
	"""Re-run the whole OTP suite on real Redis, plus the extra checks below."""

	def setUp(self):
		real = frappe.cache()
		super().setUp()
		patcher = patch("frappe.cache", return_value=real)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.real = real

	def _purge(self, *phones):
		for ph in phones:
			real = self.real
			real.delete(otp._key("phone", otp._digest("GW", ph)))

	def test_idempotency_conflict_real_redis(self):
		ph = _phone()
		key = secrets.token_hex(4)
		first = otp.send_otp("GW", ph, CODE, idempotency_key=key)
		self.assertTrue(first["success"])
		same = otp.send_otp("GW", ph, CODE, idempotency_key=key)
		self.assertTrue(same.get("replayed"))
		self.assertEqual(len(self.sent), 1)
		other = otp.send_otp("GW", ph, CODE + "X", idempotency_key=key)
		self.assertEqual(other["error"], "idempotency_conflict")
		self.assertEqual(len(self.sent), 1)
		self.assertNotIn(CODE, repr(other))

	def test_rate_limit_refund_real_redis(self):
		ph = _phone()
		optout = patch.object(bridge.policy, "enforce_template", side_effect=bridge.policy.OutboundRefused("x", "opted_out"))
		with optout:
			for _ in range(otp.PHONE_LIMIT + 3):
				self.assertEqual(otp.send_otp("GW", ph, CODE)["error"], "not_opted_in")  # refunded, never rate_limited
		# Meta saw these: they keep their count
		self.post.side_effect = base._graph_error
		for _ in range(otp.PHONE_LIMIT):
			self.assertEqual(otp.send_otp("GW", ph, CODE)["error"], "send_failed")
		self.assertEqual(otp.send_otp("GW", ph, CODE)["error"], "rate_limited")

	def test_sms_fallback_idempotency_and_refund(self):
		ph = _phone()
		sms = MagicMock(return_value={"ok": True, "id": "SM1", "status": "queued"})
		with self._optout(), patch("huf.ai.channels.channel_consent.has_consent", return_value=(True, "ok")), \
				patch("huf.ai.gateway_adapters.sms.send_sms_message", sms):
			key = secrets.token_hex(4)
			res = otp.send_otp("GW", ph, CODE, idempotency_key=key, **self.FB)
			again = otp.send_otp("GW", ph, CODE, idempotency_key=key, **self.FB)
			clash = otp.send_otp("GW", ph, CODE + "Z", idempotency_key=key, **self.FB)
		self.assertEqual((res["channel"], res["message_id"]), ("sms", "SM1"))
		self.assertTrue(again.get("replayed"))
		self.assertEqual(clash["error"], "idempotency_conflict")
		self.assertEqual(sms.call_count, 1)

	def test_code_absent_from_every_text_column(self):
		ph = _phone()
		sms = MagicMock(return_value={"ok": True, "id": "SM2", "status": "queued", "error": f"echo {CODE}"})
		logger = logging.getLogger()
		with self.assertLogs(logger, level="DEBUG"):
			logger.debug("probe")
			otp.send_otp("GW", ph, CODE, idempotency_key=secrets.token_hex(4))
			self.post.side_effect = base._graph_error
			otp.send_otp("GW", _phone(), CODE)
			with self._optout(), patch("huf.ai.channels.channel_consent.has_consent", return_value=(True, "ok")), \
					patch("huf.ai.gateway_adapters.sms.send_sms_message", sms):
				otp.send_otp("GW", _phone(), CODE, **self.FB)
			bad = MagicMock(side_effect=RuntimeError(f"boom {CODE}"))
			with self._optout(), patch("huf.ai.channels.channel_consent.has_consent", return_value=(True, "ok")), \
					patch("huf.ai.gateway_adapters.sms.send_sms_message", bad):
				otp.send_otp("GW", _phone(), CODE, **self.FB)
		hits = []
		cols = frappe.db.sql(
			"""select table_name, column_name from information_schema.columns
			where table_schema = database() and data_type in ('char','varchar','tinytext','text','mediumtext','longtext','json')""",
		)
		for table, col in cols:
			n = frappe.db.sql(f"select count(*) from `{table}` where `{col}` like %s", (f"%{CODE}%",))[0][0]
			if n:
				hits.append((table, col, n))
		self.assertEqual(hits, [], f"OTP code found in DB columns: {hits}")
