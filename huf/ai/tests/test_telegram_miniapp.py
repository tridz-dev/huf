# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import base64
import json
import unittest
from urllib.parse import parse_qsl, urlencode

from huf.ai.gateway_adapters import telegram_miniapp as m

TOKEN = "123456:TEST-not-a-real-token"
NOW = 1_800_000_000


def _make(**kw):
	kw.setdefault("auth_date", NOW - 10)
	return m.build_init_data_for_test(TOKEN, **kw)


def _mutate(init_data, **changes):
	fields = dict(parse_qsl(init_data, keep_blank_values=True))
	for k, v in changes.items():
		if v is None:
			fields.pop(k, None)
		else:
			fields[k] = v
	return urlencode(fields)


class TestMiniApp(unittest.TestCase):
	def test_valid(self):
		extra = {
			"start_param": "abc",
			"chat_type": "private",
			"chat_instance": "99",
			"query_id": "Q1",
			"can_send_after": "10",
		}
		u = m.validate_init_data(
			_make(user={"id": 7, "username": "bob", "first_name": "Bob", "language_code": "en"}, extra=extra),
			TOKEN,
			now=NOW,
		)
		self.assertEqual((u.user_id, u.username, u.first_name, u.language_code), (7, "bob", "Bob", "en"))
		self.assertEqual(
			(u.start_param, u.chat_type, u.chat_instance, u.query_id, u.can_send_after),
			("abc", "private", "99", "Q1", 10),
		)

	def test_tampered_hash(self):
		bad = _mutate(_make(), hash="0" * 64)
		with self.assertRaises(m.MiniAppAuthError):
			m.validate_init_data(bad, TOKEN, now=NOW)

	def test_tampered_payload(self):
		bad = _mutate(_make(), user=json.dumps({"id": 999}))
		with self.assertRaises(m.MiniAppAuthError):
			m.validate_init_data(bad, TOKEN, now=NOW)

	def test_expired(self):
		with self.assertRaisesRegex(m.MiniAppAuthError, "expired"):
			m.validate_init_data(_make(auth_date=NOW - 7200), TOKEN, now=NOW)
		m.validate_init_data(_make(auth_date=NOW - 7200), TOKEN, now=NOW, max_age_seconds=8000)

	def test_future(self):
		with self.assertRaisesRegex(m.MiniAppAuthError, "future"):
			m.validate_init_data(_make(auth_date=NOW + 600), TOKEN, now=NOW)

	def test_missing_hash_and_empty(self):
		with self.assertRaisesRegex(m.MiniAppAuthError, "no hash"):
			m.validate_init_data(_mutate(_make(), hash=None), TOKEN, now=NOW)
		with self.assertRaises(m.MiniAppAuthError):
			m.validate_init_data("", TOKEN, now=NOW)

	def test_field_order_and_unknown_fields(self):
		data = _make(extra={"zzz_new": "1", "aaa_new": "2"})
		reordered = urlencode(list(reversed(parse_qsl(data, keep_blank_values=True))))
		self.assertEqual(m.validate_init_data(reordered, TOKEN, now=NOW).user_id, 12345)

	def test_unicode_user(self):
		u = m.validate_init_data(_make(user={"id": 5, "first_name": "Zoë 😀 مرحبا"}), TOKEN, now=NOW)
		self.assertEqual(u.first_name, "Zoë 😀 مرحبا")

	def test_wrong_token(self):
		with self.assertRaises(m.MiniAppAuthError):
			m.validate_init_data(_make(), "999:other", now=NOW)
		with self.assertRaises(m.MiniAppAuthError):
			m.validate_init_data(_make(), "", now=NOW)

	def test_duplicate_field_rejected(self):
		with self.assertRaisesRegex(m.MiniAppAuthError, "duplicate"):
			m.validate_init_data(_make() + "&auth_date=1", TOKEN, now=NOW)

	def test_builders(self):
		self.assertEqual(
			m.web_app_button("https://x.y/app", "Open"),
			{"text": "Open", "web_app": {"url": "https://x.y/app"}},
		)
		p = m.menu_button_payload("https://x.y/app", "Open", chat_id=5)
		self.assertEqual(p["menu_button"]["type"], "web_app")
		self.assertEqual(p["chat_id"], 5)

	def test_third_party_signature(self):
		try:
			from cryptography.hazmat.primitives import serialization
			from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
		except ImportError:
			self.skipTest("cryptography not installed")
		key = Ed25519PrivateKey.generate()
		pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
		fields = {"user": json.dumps({"id": 3}), "auth_date": str(NOW - 5)}
		msg = ("42:WebAppData\n" + "\n".join(f"{k}={fields[k]}" for k in sorted(fields))).encode()
		sig = base64.urlsafe_b64encode(key.sign(msg)).rstrip(b"=").decode()
		data = urlencode({**fields, "hash": "x", "signature": sig})
		self.assertEqual(m.validate_init_data_third_party(data, 42, public_key_hex=pub, now=NOW).user_id, 3)
		with self.assertRaises(m.MiniAppAuthError):
			m.validate_init_data_third_party(data, 43, public_key_hex=pub, now=NOW)
