# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Broadcast messaging limit and preview checks (no bench needed; DB helpers and Graph are patched)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.whatsapp.broadcast import limits as bl
from huf.ai.whatsapp import token_check as tc

_REAL_REQUIREMENTS = bl.template_requirements

TOKEN = "EAAB-test-token-not-real"
PREVIEW_OK = {"gateway": "GW-1", "template": "tpl-1", "consent_attested": 1}
TPL_OK = {"status": "APPROVED", "category": "UTILITY"}
LIMIT_OK = {"tier": "TIER_250", "max_unique_24h": 250, "quality": "GREEN", "mps": None, "raw": {}}


class _FakeCache:
	def __init__(self):
		self.store = {}

	def get_value(self, key):
		return self.store.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.store[key] = value


def _resp(status, body):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = body
	return r


class TestMapping(unittest.TestCase):
	def test_tier_caps(self):
		self.assertEqual(bl._max_for("TIER_250"), 250)
		self.assertEqual(bl._max_for("TIER_1K"), 1000)
		self.assertEqual(bl._max_for("TIER_2K"), 2000)
		self.assertEqual(bl._max_for("TIER_10K"), 10000)
		self.assertEqual(bl._max_for("TIER_100K"), 100000)
		self.assertIsNone(bl._max_for(bl.UNLIMITED))
		self.assertIsNone(bl._max_for("TIER_NOPE"))
		self.assertIsNone(bl._max_for(None))

	def test_parse_fields(self):
		out = bl._parse(
			{
				"whatsapp_business_manager_messaging_limit": "TIER_250",
				"quality_rating": "red",
				"throughput": {"mps": 80},
			}
		)
		self.assertEqual(out["tier"], "TIER_250")
		self.assertEqual(out["max_unique_24h"], 250)
		self.assertEqual(out["quality"], "RED")
		self.assertEqual(out["mps"], 80)

	def test_unknown_quality_and_throughput_shape_are_none(self):
		out = bl._parse({"quality_rating": "UNKNOWN", "throughput": {"level": "STANDARD"}})
		self.assertIsNone(out["quality"])
		self.assertIsNone(out["mps"])
		self.assertIsNone(out["tier"])

	def test_us_plus_one(self):
		self.assertTrue(bl._is_us_plus_one("14155550100"))
		self.assertFalse(bl._is_us_plus_one("447700900123"))
		self.assertFalse(bl._is_us_plus_one("IN.4608123"))


class TestGetMessagingLimit(unittest.TestCase):
	def _run(self, http, cache=None, resolve=None):
		cache = cache or _FakeCache()
		creds = {"token": TOKEN, "base": "https://graph.example/v1", "phone_id": "106"}
		with (
			patch.object(bl.frappe.db, "exists", return_value=True),
			patch.object(bl.frappe, "cache", return_value=cache),
			patch.object(tc, "resolve_credentials", side_effect=resolve, return_value=creds),
			patch.object(tc, "default_http_get", side_effect=http),
		):
			return bl.get_messaging_limit("GW-1"), cache

	def test_success_parses_and_caches_without_token(self):
		body = {"whatsapp_business_manager_messaging_limit": "TIER_2K", "quality_rating": "GREEN"}
		http = MagicMock(return_value=_resp(200, body))
		out, cache = self._run(http)
		self.assertEqual(out["tier"], "TIER_2K")
		self.assertEqual(out["max_unique_24h"], 2000)
		self.assertEqual(out["quality"], "GREEN")
		_, kwargs = http.call_args
		self.assertEqual(kwargs["params"]["fields"], bl.FIELDS)
		self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")
		self.assertNotIn(TOKEN, repr(out))
		self.assertNotIn(TOKEN, repr(cache.store))

	def test_cache_hit_skips_graph(self):
		cache = _FakeCache()
		cache.store[bl._cache_key("GW-1")] = dict(LIMIT_OK)
		http = MagicMock()
		out, _ = self._run(http, cache=cache)
		self.assertEqual(out["tier"], "TIER_250")
		http.assert_not_called()

	def test_graph_error_returns_empty(self):
		out, _ = self._run(MagicMock(return_value=_resp(400, {"error": {"code": 100}})))
		self.assertEqual(out, bl._empty())

	def test_transport_error_returns_empty_and_never_raises(self):
		def boom(*a, **k):
			raise ConnectionError(f"https://graph.example/?access_token={TOKEN}")

		out, _ = self._run(boom)
		self.assertEqual(out, bl._empty())
		self.assertNotIn(TOKEN, repr(out))

	def test_missing_credentials_returns_empty(self):
		def no_token(_gateway):
			raise tc.frappe.ValidationError("No access token is configured for this gateway.")

		out, _ = self._run(MagicMock(), resolve=no_token)
		self.assertEqual(out, bl._empty())


class _PreviewBase(unittest.TestCase):
	def setUp(self):
		self.counts = {"queued": 10, "skipped": 2}
		self.queued_numbers = ["447700900123"] * 10
		self.requirements = None
		self.queued_params = [(None, 10)]
		self.patches = [
			patch.object(bl, "_broadcast_row", return_value=dict(PREVIEW_OK)),
			patch.object(bl, "_template_row", return_value=dict(TPL_OK)),
			patch.object(bl, "_recipient_counts", side_effect=lambda _b: dict(self.counts)),
			patch.object(bl, "_queued_numbers", side_effect=lambda _b: list(self.queued_numbers)),
			patch.object(bl, "_running_others", return_value=[]),
			patch.object(bl, "_used_24h", return_value=0),
			patch.object(bl, "get_messaging_limit", return_value=dict(LIMIT_OK)),
			patch.object(bl, "template_requirements", side_effect=lambda _t: self.requirements),
			patch.object(bl, "_queued_params", side_effect=lambda _b: list(self.queued_params)),
		]
		for p in self.patches:
			p.start()
			self.addCleanup(p.stop)

	def _preview(self):
		return bl.preview("BCAST-00001")


class TestPreview(_PreviewBase):
	def test_clean_broadcast_has_no_blocking(self):
		out = self._preview()
		self.assertEqual(out["blocking"], [])
		self.assertEqual(out["warnings"], [])
		self.assertEqual(out["recipients"], 12)
		self.assertEqual(out["queued"], 10)
		self.assertEqual(out["skipped"], 2)
		self.assertEqual(out["template_status"], "APPROVED")
		self.assertEqual(out["category"], "UTILITY")
		self.assertTrue(out["within_limit"])
		self.assertEqual(out["remaining_24h"], 250)

	def test_template_not_approved_blocks(self):
		with patch.object(bl, "_template_row", return_value={"status": "PAUSED", "category": "MARKETING"}):
			out = self._preview()
		self.assertIn("template_not_approved:PAUSED", out["blocking"])

	def test_marketing_us_plus_one_warns_with_count(self):
		self.queued_numbers = ["14155550100", "14155550101", "447700900123"]
		self.counts = {"queued": 3}
		with patch.object(bl, "_template_row", return_value={"status": "APPROVED", "category": "MARKETING"}):
			out = self._preview()
		self.assertTrue(any("2 queued recipient(s) are US +1" in w for w in out["warnings"]))

	def test_non_marketing_us_numbers_do_not_warn(self):
		self.queued_numbers = ["14155550100"]
		self.counts = {"queued": 1}
		out = self._preview()
		self.assertFalse(any("US +1" in w for w in out["warnings"]))

	def test_budget_exceeded_blocks_when_limit_known(self):
		with patch.object(bl, "_used_24h", return_value=245):
			out = self._preview()
		self.assertFalse(out["within_limit"])
		self.assertEqual(out["remaining_24h"], 5)
		self.assertTrue(any(b.startswith("recipients_exceed_24h_budget") for b in out["blocking"]))

	def test_unknown_limit_warns_and_within_limit_is_none(self):
		with patch.object(bl, "get_messaging_limit", return_value=bl._empty()):
			out = self._preview()
		self.assertIsNone(out["within_limit"])
		self.assertIsNone(out["remaining_24h"])
		self.assertEqual(out["blocking"], [])
		self.assertTrue(any("Messaging limit is unknown" in w for w in out["warnings"]))

	def test_unlimited_tier_has_no_cap(self):
		unlimited = {"tier": bl.UNLIMITED, "max_unique_24h": None, "quality": "GREEN", "mps": None, "raw": {}}
		with patch.object(bl, "get_messaging_limit", return_value=unlimited):
			out = self._preview()
		self.assertTrue(out["within_limit"])
		self.assertIsNone(out["remaining_24h"])

	def test_quality_red_blocks_yellow_warns(self):
		with patch.object(bl, "get_messaging_limit", return_value=dict(LIMIT_OK, quality="RED")):
			self.assertIn("quality_red", self._preview()["blocking"])
		with patch.object(bl, "get_messaging_limit", return_value=dict(LIMIT_OK, quality="YELLOW")):
			out = self._preview()
		self.assertNotIn("quality_red", out["blocking"])
		self.assertTrue(any("YELLOW" in w for w in out["warnings"]))

	def test_other_running_broadcast_blocks(self):
		with patch.object(bl, "_running_others", return_value=["BCAST-00009"]):
			out = self._preview()
		self.assertIn("another_broadcast_running:BCAST-00009", out["blocking"])

	def test_consent_not_attested_blocks(self):
		with patch.object(bl, "_broadcast_row", return_value=dict(PREVIEW_OK, consent_attested=0)):
			out = self._preview()
		self.assertIn("consent_not_attested", out["blocking"])

	def test_missing_broadcast_blocks(self):
		with patch.object(bl, "_broadcast_row", return_value=None):
			out = self._preview()
		self.assertEqual(out["blocking"], ["broadcast_not_found"])

	def test_unexpected_error_never_raises(self):
		with patch.object(bl, "_recipient_counts", side_effect=RuntimeError("db down")):
			out = self._preview()
		self.assertEqual(out["blocking"], ["preview_failed"])


class TestPreviewTemplateParams(_PreviewBase):
	def _named(self):
		from huf.ai.gateway_adapters import whatsapp_bridge as bridge
		from huf.ai.gateway_adapters import whatsapp_template_guard as guard

		tpl = {"template": "Hi {{first_name}}", "header_type": "", "header": "", "sample": "", "buttons": [],
			"parameter_format": "NAMED", "header_format": "", "whatsapp_account": "A"}
		with patch.object(bridge, "_template_row", return_value=tpl), patch.object(guard, "get_extra", return_value={}):
			return _REAL_REQUIREMENTS("t")

	def test_missing_named_value_blocks(self):
		self.requirements = self._named()
		out = self._preview()
		self.assertIn("10 recipients are missing values for template variables: first_name", out["blocking"])

	def test_default_params_clear_block(self):
		self.requirements = self._named()
		row = dict(PREVIEW_OK, body_params='{"first_name": "Friend"}')
		with patch.object(bl, "_broadcast_row", return_value=row):
			out = self._preview()
		self.assertEqual(out["blocking"], [])
