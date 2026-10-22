"""Unit tests for whatsapp_errors (pure Python; loadable without frappe)."""

import importlib.util
import os
import random
import unittest


def _load(name):
	try:
		import importlib

		return importlib.import_module(f"huf.ai.gateway_adapters.{name}")
	except Exception:
		path = os.path.join(os.path.dirname(__file__), "..", "..", "gateway_adapters", f"{name}.py")
		spec = importlib.util.spec_from_file_location(name, path)
		mod = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(mod)
		return mod


we = _load("whatsapp_errors")


def body(code, msg="m", **kw):
	return {"error": {"message": msg, "code": code, **kw}}


class FakeResp:
	def __init__(self, status, payload=None, headers=None, text=""):
		self.status_code = status
		self._p = payload
		self.headers = headers or {}
		self.text = text

	def json(self):
		if self._p is None:
			raise ValueError("no json")
		return self._p


class FakeHTTPError(Exception):
	def __init__(self, resp):
		super().__init__("http error")
		self.response = resp


class Timeout(Exception):
	pass


class TestClassify(unittest.TestCase):
	# code -> (kind, retryable)
	CODES = {
		190: ("auth", False),
		10: ("permission", False),
		200: ("permission", False),
		250: ("permission", False),
		299: ("permission", False),
		4: ("rate_limited", True),
		17: ("rate_limited", True),
		32: ("rate_limited", True),
		613: ("rate_limited", True),
		80007: ("rate_limited", True),
		130429: ("rate_limited", True),
		131056: ("pair_rate_limited", True),
		131047: ("window_closed", False),
		131026: ("recipient", False),
		131048: ("permission", False),
		131049: ("rate_limited", False),
		131051: ("media", False),
		131052: ("media", False),
		131053: ("media", False),
		131000: ("param", False),
		131008: ("param", False),
		131009: ("param", False),
		132000: ("template", False),
		132001: ("template", False),
		132005: ("template", False),
		132007: ("template", False),
		132012: ("template", False),
		132015: ("template", False),
		132016: ("template", False),
		133010: ("permission", False),
		368: ("permission", False),
		100: ("param", False),
	}

	def test_code_table(self):
		for code, (kind, retry) in self.CODES.items():
			with self.subTest(code):
				c = we.classify(body(code))
				self.assertEqual((c["code"], c["kind"], c["retryable"]), (code, kind, retry))
				self.assertTrue(c["operator_text"])
				self.assertEqual(we.is_permanent(c), not retry)

	def test_inner_dict_shape(self):
		c = we.classify({"code": 131047, "message": "x"})
		self.assertEqual(c["kind"], "window_closed")

	def test_webhook_status_errors_shape(self):
		c = we.classify({"errors": [{"code": 131026, "title": "Message Undeliverable", "message": "m"}]})
		self.assertEqual((c["kind"], c["user_msg"]), ("recipient", "Message Undeliverable"))

	def test_pair_rate_limit_hint(self):
		self.assertEqual(we.classify(body(131056))["retry_after_hint"], 6.0)

	def test_marketing_cap_hint_but_not_retryable(self):
		c = we.classify(body(131049))
		self.assertFalse(c["retryable"])
		self.assertEqual(c["retry_after_hint"], 86400.0)

	def test_window_closed_suggests_template(self):
		self.assertIn("template", we.classify(body(131047))["operator_text"].lower())

	def test_subcode_and_user_msg(self):
		c = we.classify(body(100, error_subcode=2388023, error_user_msg="Bad phone", error_user_title="Oops"))
		self.assertEqual((c["subcode"], c["user_msg"]), (2388023, "Bad phone"))
		self.assertIn("Bad phone", c["operator_text"])

	def test_user_title_fallback(self):
		self.assertEqual(we.classify(body(100, error_user_title="T"))["user_msg"], "T")

	def test_user_msg_none_when_absent(self):
		self.assertIsNone(we.classify(body(190))["user_msg"])

	def test_status_body_tuple(self):
		c = we.classify((400, body(131047)))
		self.assertEqual((c["http_status"], c["kind"]), (400, "window_closed"))

	def test_status_tuple_string_body(self):
		c = we.classify((503, "upstream down"))
		self.assertEqual((c["kind"], c["retryable"]), ("server", True))

	def test_http_429_without_code(self):
		c = we.classify((429, {}))
		self.assertEqual((c["kind"], c["retryable"]), ("rate_limited", True))

	def test_http_5xx(self):
		for st in (500, 502, 503):
			with self.subTest(st):
				c = we.classify((st, None))
				self.assertEqual((c["kind"], c["retryable"]), ("server", True))

	def test_http_504_and_408_timeout(self):
		for st in (504, 408):
			self.assertEqual(we.classify((st, None))["kind"], "timeout")

	def test_http_401_403(self):
		self.assertEqual(we.classify((401, None))["kind"], "auth")
		self.assertEqual(we.classify((403, None))["kind"], "permission")

	def test_requests_exception_with_response(self):
		c = we.classify(FakeHTTPError(FakeResp(400, body(131056))))
		self.assertEqual((c["kind"], c["http_status"]), ("pair_rate_limited", 400))

	def test_exception_retry_after_header(self):
		c = we.classify(FakeHTTPError(FakeResp(429, {}, headers={"Retry-After": "30"})))
		self.assertEqual((c["kind"], c["retry_after_hint"]), ("rate_limited", 30.0))

	def test_response_object_directly(self):
		c = we.classify(FakeResp(500, None, text="oops"))
		self.assertEqual(c["kind"], "server")

	def test_response_non_json_body(self):
		c = we.classify(FakeHTTPError(FakeResp(502, None, text="<html>bad gateway</html>")))
		self.assertEqual(c["kind"], "server")

	def test_timeout_exceptions(self):
		for e in (Timeout("read timed out"), TimeoutError("x")):
			with self.subTest(type(e).__name__):
				c = we.classify(e)
				self.assertEqual((c["kind"], c["retryable"]), ("timeout", True))

	def test_connection_error_retryable(self):
		self.assertTrue(we.classify(ConnectionError("Connection reset"))["retryable"])

	def test_string_json(self):
		c = we.classify('{"error": {"code": 190, "message": "expired"}}')
		self.assertEqual(c["kind"], "auth")

	def test_string_graph_error_message_style(self):
		c = we.classify("(131047) Re-engagement message")
		self.assertEqual((c["code"], c["kind"]), (131047, "window_closed"))

	def test_string_timeout(self):
		self.assertEqual(we.classify("request timed out")["kind"], "timeout")

	def test_unknown_code(self):
		c = we.classify(body(999999))
		self.assertEqual((c["kind"], c["retryable"]), ("unknown", False))

	def test_malformed_inputs_never_raise(self):
		for v in (None, "", 0, 3.5, [], {}, {"error": "str"}, {"error": None}, (1,), object(), b"\xff\xfe", {"error": {"code": "abc"}}, [1, 2, 3]):
			with self.subTest(repr(v)[:30]):
				c = we.classify(v)
				self.assertIn(c["kind"], we.KINDS)
				for key in ("code", "subcode", "kind", "retryable", "retry_after_hint", "operator_text", "user_msg", "message"):
					self.assertIn(key, c)

	def test_string_code_coerced(self):
		self.assertEqual(we.classify(body("131047"))["code"], 131047)

	def test_kind_always_valid(self):
		for code in list(self.CODES) + [None, 12345]:
			self.assertIn(we.classify(body(code))["kind"], we.KINDS)


class TestRedaction(unittest.TestCase):
	def test_bearer_redacted(self):
		c = we.classify(body(190, "Invalid Bearer EAAabcdefghijk1234567890 token"))
		self.assertNotIn("EAAabcdefghijk", c["message"])

	def test_access_token_query_redacted(self):
		c = we.classify(body(100, "failed https://graph.facebook.com/v21.0/1/messages?access_token=SECRETVALUE123&x=1"))
		self.assertNotIn("SECRETVALUE123", c["message"])
		self.assertNotIn("x=1", c["message"])

	def test_media_url_query_stripped(self):
		c = we.classify(body(131052, "see https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1&ext=2&hash=ABC"))
		self.assertNotIn("hash=ABC", c["message"])

	def test_plain_url_without_query_kept(self):
		self.assertIn("https://a.com/x", we.redact("see https://a.com/x ok"))

	def test_json_style_token_redacted(self):
		self.assertNotIn("TOPSECRET", we.redact('{"access_token": "TOPSECRET", "a": 1}'))

	def test_string_error_redacted(self):
		self.assertNotIn("tok123", we.classify("boom Authorization: Bearer tok123").get("message"))

	def test_user_msg_redacted(self):
		c = we.classify(body(100, error_user_msg="bad access_token=ZZZ999"))
		self.assertNotIn("ZZZ999", c["user_msg"])

	def test_exception_text_redacted(self):
		self.assertNotIn("sekret", we.classify(Timeout("GET https://x.com/p?access_token=sekret timed out"))["message"])


class TestBackoff(unittest.TestCase):
	def test_schedule_within_jitter(self):
		for attempt, base in ((1, 2), (2, 4), (3, 8), (4, 16), (5, 16), (10, 16)):
			for _ in range(50):
				d = we.backoff_seconds("rate_limited", attempt)
				self.assertGreaterEqual(d, base * 0.8 - 1e-9)
				self.assertLessEqual(d, base * 1.2 + 1e-9)

	def test_deterministic_rng_midpoint(self):
		class Mid:
			def uniform(self, a, b):
				return 0.0

		self.assertEqual([we.backoff_seconds("server", n, Mid()) for n in (1, 2, 3, 4)], [2, 4, 8, 16])

	def test_pair_fixed_six(self):
		for n in (1, 2, 3):
			self.assertEqual(we.backoff_seconds("pair_rate_limited", n), 6.0)

	def test_permanent_kinds_none(self):
		for k in ("auth", "window_closed", "template", "media", "recipient", "permission", "param", "unknown"):
			self.assertIsNone(we.backoff_seconds(k, 1))

	def test_classification_input(self):
		self.assertIsNone(we.backoff_seconds(we.classify(body(131026)), 1))
		self.assertEqual(we.backoff_seconds(we.classify(body(131056)), 1), 6.0)

	def test_retry_after_hint_wins(self):
		c = we.classify(FakeHTTPError(FakeResp(429, {}, headers={"Retry-After": "60"})))
		self.assertEqual(we.backoff_seconds(c, 1), 60.0)

	def test_attempt_below_one_and_bad(self):
		self.assertLessEqual(we.backoff_seconds("server", 0), 2.4)
		self.assertLessEqual(we.backoff_seconds("server", "x"), 2.4)

	def test_seeded_random(self):
		self.assertEqual(we.backoff_seconds("server", 2, random.Random(1)), we.backoff_seconds("server", 2, random.Random(1)))

	def test_should_retry_caps_attempts(self):
		c = we.classify(body(130429))
		self.assertTrue(we.should_retry(c, 1))
		self.assertTrue(we.should_retry(c, 3))
		self.assertFalse(we.should_retry(c, we.MAX_ATTEMPTS))
		self.assertFalse(we.should_retry(we.classify(body(131026)), 1))

	def test_is_permanent_bad_input(self):
		self.assertTrue(we.is_permanent({}))
		self.assertTrue(we.is_permanent(None))


if __name__ == "__main__":
	unittest.main()
