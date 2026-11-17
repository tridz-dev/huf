"""send_otp / get_otp_status: restricted caller, abuse limits, idempotency, and the code never leaking.

Run: bench --site test_site run-tests --app huf --module huf.ai.whatsapp.tests.test_whatsapp_otp
"""

import logging
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import otp

SENTINEL = "987654"
PHONE = "919876543210"
ACCT = {"name": "ACC", "phone_id": "111", "token": "tok", "url": "https://graph.facebook.com", "version": "v25.0"}
TPL = {"name": "otp_auth-en_US", "status": "APPROVED", "actual_name": "otp_auth", "template_name": "otp_auth", "language_code": "en_US"}


def _ok(*_a, **_k):
	r = MagicMock(status_code=200)
	r.json.return_value = {"messages": [{"id": "wamid.OTP1"}]}
	return r


def _graph_error(*_a, **_k):
	r = MagicMock(status_code=400, text="")
	r.json.return_value = {"error": {"code": 131000, "message": f"bad param {SENTINEL} rejected"}}
	return r


class TestOtp(unittest.TestCase):
	def setUp(self):
		self.cache = {}
		fake = MagicMock()
		fake.incr.side_effect = lambda k: self.cache.__setitem__(k, self.cache.get(k, 0) + 1) or self.cache[k]
		fake.decr.side_effect = lambda k: self.cache.__setitem__(k, self.cache.get(k, 0) - 1)
		fake.expire.return_value = True

		def _set(k, v, ex=None, nx=False):
			if nx and k in self.cache:
				return None
			self.cache[k] = v
			return True

		fake.set.side_effect = _set
		fake.get.side_effect = lambda k: self.cache.get(k)
		fake.delete.side_effect = lambda k: self.cache.pop(k, None)
		self.sent = []
		self.post = MagicMock(side_effect=lambda *a, **k: (self.sent.append(k.get("json")), _ok())[1])
		self.mirror = MagicMock(return_value={"success": True, "name": "WM1", "message_id": "wamid.OTP1", "status": "Success"})
		self.user = "otp.caller@example.com"
		self.roles = [otp.OTP_SENDER_ROLE]
		patches = [
			patch("huf.ai.whatsapp.otp.frappe.cache", return_value=fake),
			patch("huf.ai.whatsapp.otp.frappe.get_roles", side_effect=lambda *_: self.roles),
			patch("huf.ai.whatsapp.otp.frappe.db.exists", return_value=True),
			patch("huf.ai.whatsapp.otp.frappe.get_all", return_value=[dict(TPL)]),
			patch("huf.ai.whatsapp.otp.management._gateway_whatsapp_account", return_value="ACC"),
			patch("huf.ai.whatsapp.otp.management._resolve_account_name", return_value="ACC"),
			patch("huf.ai.whatsapp.otp.bridge.is_available", return_value=True),
			patch("huf.ai.whatsapp.otp.bridge._template_docname", return_value="otp_auth-en_US"),
			patch.object(bridge, "_account_or_error", return_value=dict(ACCT)),
			patch.object(bridge, "_refuse_if_disconnected"),
			patch.object(bridge, "_template_docname", return_value="otp_auth-en_US"),
			patch.object(bridge, "_template_row", return_value={**TPL, "template": "Your code is {{1}}", "category": "AUTHENTICATION", "whatsapp_account": "ACC", "buttons": [], "header_type": ""}),
			patch.object(bridge.policy, "enforce_template"),
			patch.object(bridge.policy, "note_template_sent"),
			patch.object(bridge, "_default_post", self.post),
			patch.object(bridge, "_mirror_template_send", self.mirror),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		self._user = patch.object(frappe.session, "user", self.user)
		self._user.start()
		self.addCleanup(self._user.stop)

	def test_sentinel_never_leaks(self):
		logger = logging.getLogger()
		with self.assertLogs(logger, level="DEBUG") as cm, patch("frappe.log_error") as log_error:
			logger.debug("probe")
			res = otp.send_otp("GW", PHONE, SENTINEL, idempotency_key="k1")
			self.post.side_effect = _graph_error
			err = otp.send_otp("GW", "919876543211", SENTINEL)
		self.assertTrue(res["success"])
		self.assertEqual(res["message_id"], "wamid.OTP1")
		# Meta did get the code (it must) ...
		self.assertIn(SENTINEL, str(self.sent[0]))
		# ... but nothing else did
		self.assertNotIn(SENTINEL, repr(res))
		self.assertNotIn(SENTINEL, repr(err))
		self.assertFalse(err["success"])
		self.assertNotIn(SENTINEL, "\n".join(cm.output))
		log_error.assert_not_called()
		mirror_values = self.mirror.call_args_list[0].args[4]
		self.assertNotIn(SENTINEL, repr(mirror_values))
		self.assertNotIn(SENTINEL, repr(self.cache))

	def test_permission_denied(self):
		for roles in (["Huf Manager"], ["Guest"]):
			self.roles = roles
			with self.assertRaises(frappe.PermissionError):
				otp.send_otp("GW", PHONE, SENTINEL)
			with self.assertRaises(frappe.PermissionError):
				otp.get_otp_status("wamid.OTP1")
		self.assertEqual(self.sent, [])
		self.roles = ["System Manager"]
		self.assertTrue(otp.send_otp("GW", PHONE, SENTINEL)["success"])

	def test_per_phone_rate_limit(self):
		for _ in range(otp.PHONE_LIMIT):
			self.assertTrue(otp.send_otp("GW", PHONE, SENTINEL)["success"])
		res = otp.send_otp("GW", PHONE, SENTINEL)
		self.assertEqual((res["error"], res["scope"]), ("rate_limited", "phone"))
		self.assertEqual(len(self.sent), otp.PHONE_LIMIT)

	def test_per_caller_rate_limit(self):
		with patch.object(otp, "CALLER_LIMIT", 2):
			self.assertTrue(otp.send_otp("GW", "919000000001", SENTINEL)["success"])
			self.assertTrue(otp.send_otp("GW", "919000000002", SENTINEL)["success"])
			res = otp.send_otp("GW", "919000000003", SENTINEL)
		self.assertEqual((res["error"], res["scope"]), ("rate_limited", "caller"))

	def test_idempotent_replay(self):
		first = otp.send_otp("GW", PHONE, SENTINEL, idempotency_key="abc")
		again = otp.send_otp("GW", PHONE, SENTINEL, idempotency_key="abc")
		self.assertEqual(again["message_id"], first["message_id"])
		self.assertTrue(again["replayed"])
		self.assertEqual(len(self.sent), 1)
		# same key, other phone: not a replay
		other = otp.send_otp("GW", "919876543299", SENTINEL, idempotency_key="abc")
		self.assertNotIn("replayed", other)
		self.assertEqual(len(self.sent), 2)
		self.assertFalse(any("abc" in k for k in self.cache))  # key stored hashed only

	def test_error_codes(self):
		with patch.object(bridge.policy, "enforce_template", side_effect=bridge.policy.OutboundRefused("x", "opted_out")):
			self.assertEqual(otp.send_otp("GW", PHONE, SENTINEL)["error"], "not_opted_in")
		with patch("huf.ai.whatsapp.otp.frappe.get_all", return_value=[{**TPL, "status": "PENDING"}]):
			self.assertEqual(otp.send_otp("GW", PHONE, SENTINEL)["error"], "template_not_approved")
		self.assertEqual(otp.send_otp("GW", PHONE, "12")["error"], "invalid_code")

	def test_status_owner_check(self):
		res = otp.send_otp("GW", PHONE, SENTINEL)
		with patch("huf.ai.whatsapp.otp.frappe.db.get_value", return_value={"status": "delivered", "type": "Outgoing"}):
			self.assertEqual(otp.get_otp_status(res["message_id"])["status"], "delivered")
			with patch.object(frappe.session, "user", "someone.else@example.com"):
				self.assertEqual(otp.get_otp_status(res["message_id"])["error"], "not_found")
