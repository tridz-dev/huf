"""send_otp / get_otp_status: restricted caller, abuse limits, idempotency, and the code never leaking.

Run: bench --site test_site run-tests --app huf --module huf.ai.whatsapp.tests.test_whatsapp_otp
"""

import logging
import unittest
from typing import ClassVar
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
		self.fake = fake

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
			patch("huf.ai.whatsapp.otp.frappe.has_permission", return_value=True),
			patch("huf.ai.whatsapp.broadcast.failover._credentials", return_value={"mode": "twilio"}),
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
		self._user = patch.object(frappe, "session", frappe._dict(user=self.user))
		self._user.start()
		self.addCleanup(self._user.stop)

	def test_payload_matches_meta_authentication_shape(self):
		res = otp.send_otp("GW", PHONE, SENTINEL)
		self.assertTrue(res["success"])
		comps = self.sent[0]["template"]["components"]
		self.assertEqual(comps, [
			{"type": "body", "parameters": [{"type": "text", "text": SENTINEL}]},
			{"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": SENTINEL}]},
		])

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
			with patch.object(frappe, "session", frappe._dict(user="someone.else@example.com")):
				self.assertEqual(otp.get_otp_status(res["message_id"])["error"], "not_found")

	# --- SMS fallback (HUFCRM-01b) ---
	FB: ClassVar[dict] = {"fallback": "sms", "sms_gateway": "SMSGW", "fallback_text": "Your code is {code}"}

	def _optout(self):
		return patch.object(bridge.policy, "enforce_template", side_effect=bridge.policy.OutboundRefused("x", "opted_out"))

	def test_sms_fallback_sentinel_never_leaks(self):
		sms = MagicMock(return_value={"ok": True, "id": "SM1", "status": "queued", "error": f"echo Your code is {SENTINEL}"})
		logger = logging.getLogger()
		with self.assertLogs(logger, level="DEBUG") as cm, patch("frappe.log_error") as log_error, self._optout(), \
				patch("huf.ai.channels.channel_consent.has_consent", return_value=(True, "ok")) as consent, \
				patch("huf.ai.gateway_adapters.sms.send_sms_message", sms), \
				patch("huf.ai.whatsapp.broadcast.failover._credentials", return_value={"mode": "twilio"}):
			logger.debug("probe")
			res = otp.send_otp("GW", PHONE, SENTINEL, idempotency_key="k9", **self.FB)
		self.assertTrue(res["success"])
		self.assertEqual((res["channel"], res["message_id"]), ("sms", "SM1"))
		self.assertEqual(consent.call_args.args, ("sms", f"+{PHONE}", "utility"))
		self.assertIn(SENTINEL, sms.call_args.args[2])  # the SMS itself carries the code
		self.assertNotIn(SENTINEL, repr(res))
		self.assertNotIn(SENTINEL, "\n".join(cm.output))
		log_error.assert_not_called()
		self.assertNotIn(SENTINEL, repr(self.cache))
		self.assertNotIn(SENTINEL, repr(self.mirror.call_args_list))

	def test_email_fallback_refused(self):
		for fb in ("email", "whatsapp", "sms,email"):
			res = otp.send_otp("GW", PHONE, SENTINEL, **{**self.FB, "fallback": fb})
			self.assertEqual(res["error"], "invalid_fallback")
		self.assertEqual(self.sent, [])

	def test_sms_fallback_no_consent_no_sms(self):
		sms = MagicMock()
		with self._optout(), patch("huf.ai.channels.channel_consent.has_consent", return_value=(False, "no_consent")), \
				patch("huf.ai.gateway_adapters.sms.send_sms_message", sms):
			res = otp.send_otp("GW", PHONE, SENTINEL, **self.FB)
		sms.assert_not_called()
		self.assertEqual(res["error"], "not_opted_in")

	def test_sms_fallback_requires_gateway_and_text(self):
		for kw in ({"sms_gateway": None},):
			res = otp.send_otp("GW", PHONE, SENTINEL, **{**self.FB, **kw})
			self.assertEqual(res["error"], "invalid_fallback")
		for text in (None, "no placeholder", "{code} {code}", "go http://x.io {code}", "see www.x.io {code}", "a" * 500 + "{code}"):
			res = otp.send_otp("GW", PHONE, SENTINEL, **{**self.FB, "fallback_text": text})
			self.assertEqual(res["error"], "invalid_fallback_text", text)
		self.assertEqual(self.sent, [])

	def test_sms_fallback_only_on_terminal_failure(self):
		sms = MagicMock()
		with patch("huf.ai.gateway_adapters.sms.send_sms_message", sms):
			ok = otp.send_otp("GW", PHONE, SENTINEL, **self.FB)
			self.assertEqual(ok["channel"], "whatsapp")
			with patch.object(bridge.policy, "enforce_template", side_effect=bridge.policy.OutboundRefused("x", "template_not_approved")):
				self.assertEqual(otp.send_otp("GW", "919876543211", SENTINEL, **self.FB)["error"], "template_not_approved")
		sms.assert_not_called()

	def test_sms_mode_frappe_sms_refused(self):
		sms = MagicMock()
		with self._optout(), patch("huf.ai.whatsapp.broadcast.failover._credentials", return_value={"mode": "frappe_sms"}), \
				patch("huf.ai.gateway_adapters.sms.send_sms_message", sms):
			res = otp.send_otp("GW", PHONE, SENTINEL, **self.FB)
		self.assertEqual(res["error"], "sms_mode_not_allowed_for_otp")
		sms.assert_not_called()
		self.assertEqual(self.sent, [])

	def test_gateway_forbidden(self):
		with patch("huf.ai.whatsapp.otp.frappe.has_permission", side_effect=lambda dt, pt, name, user=None: name != "SMSGW"):
			self.assertEqual(otp.send_otp("GW", PHONE, SENTINEL, **self.FB)["error"], "gateway_forbidden")
		with patch("huf.ai.whatsapp.otp.frappe.has_permission", return_value=False):
			self.assertEqual(otp.send_otp("GW", PHONE, SENTINEL)["error"], "gateway_forbidden")
		self.assertEqual(self.sent, [])

	def test_idempotency_conflict_on_different_code(self):
		otp.send_otp("GW", PHONE, SENTINEL, idempotency_key="k")
		res = otp.send_otp("GW", PHONE, "111222", idempotency_key="k")
		self.assertEqual(res["error"], "idempotency_conflict")
		self.assertEqual(len(self.sent), 1)

	def test_slot_released_when_sms_fallback_raises(self):
		with self._optout(), patch.object(otp, "_sms_fallback", side_effect=RuntimeError("boom")):
			res = otp.send_otp("GW", PHONE, SENTINEL, idempotency_key="k", **self.FB)
		self.assertEqual(res["error"], "send_failed")
		self.assertFalse([k for k in self.cache if ":idem:" in k])

	def test_counters_refunded_before_meta_but_not_after(self):
		with patch.object(bridge.policy, "enforce_template", side_effect=bridge.policy.OutboundRefused("x", "opted_out")):
			otp.send_otp("GW", PHONE, SENTINEL)
		self.assertTrue(all(v == 0 for k, v in self.cache.items() if ":phone:" in k or ":caller:" in k))
		self.post.side_effect = _graph_error
		otp.send_otp("GW", "919876543211", SENTINEL)
		self.assertTrue(any(v == 1 for k, v in self.cache.items() if ":phone:" in k))

	def test_hit_sets_ttl_atomically(self):
		otp._hit("phone", "d", 3, 600)
		self.fake.set.assert_any_call(otp._key("phone", "d"), 0, ex=600, nx=True)

	def test_sms_leg_status_and_owner(self):
		sms = MagicMock(return_value={"ok": True, "id": "SM1", "status": "queued"})
		with self._optout(), patch("huf.ai.channels.channel_consent.has_consent", return_value=(True, "ok")), \
				patch("huf.ai.gateway_adapters.sms.send_sms_message", sms):
			res = otp.send_otp("GW", PHONE, SENTINEL, **self.FB)
		self.assertEqual(otp.get_otp_status(res["message_id"])["status"], "sent")
		with patch.dict(frappe.session, {"user": "someone.else@example.com"}):
			self.assertEqual(otp.get_otp_status(res["message_id"])["error"], "not_found")
