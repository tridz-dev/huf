import unittest
from unittest.mock import patch

from huf.ai.solutions import ceiling


class TestParseTier(unittest.TestCase):
	def test_known_tiers(self):
		self.assertEqual(ceiling.parse_tier("TIER_50"), 50)
		self.assertEqual(ceiling.parse_tier("TIER_250"), 250)
		self.assertEqual(ceiling.parse_tier("TIER_1K"), 1000)
		self.assertEqual(ceiling.parse_tier("TIER_10K"), 10000)
		self.assertEqual(ceiling.parse_tier("TIER_100K"), 100000)
		self.assertEqual(ceiling.parse_tier(" tier_1k "), 1000)

	def test_unlimited_is_known_but_has_no_number(self):
		self.assertEqual(ceiling.parse_tier("TIER_UNLIMITED"), ceiling.UNLIMITED)

	def test_unknown_tier_is_not_known(self):
		for bad in (None, "", "TIER_", "TIER_5X", "gold", 12, "TIER_0"):
			self.assertIsNone(ceiling.parse_tier(bad), bad)


class TestCeilingForGateway(unittest.TestCase):
	def _run(self, tier, cap):
		with patch.object(ceiling, "_cached_tier", return_value=tier), patch.object(ceiling, "_gateway_cap", return_value=cap):
			return ceiling.ceiling_for_gateway("GW")

	def test_meta_tier_wins_over_gateway_cap(self):
		self.assertEqual(self._run("TIER_1K", 200), (1000, "meta_tier"))

	def test_unlimited_tier_is_meta_source_without_number(self):
		self.assertEqual(self._run("TIER_UNLIMITED", 200), (None, "meta_tier"))

	def test_unknown_tier_falls_back_to_gateway_cap(self):
		self.assertEqual(self._run("garbage", 200), (200, "gateway_cap"))
		self.assertEqual(self._run(None, 200), (200, "gateway_cap"))

	def test_zero_cap_means_none(self):
		self.assertEqual(self._run(None, 0), (None, "none"))

	def test_missing_or_bad_cap_means_none(self):
		self.assertEqual(self._run(None, None), (None, "none"))
		self.assertEqual(self._run(None, -5), (None, "none"))

	def test_no_gateway_means_none(self):
		self.assertEqual(ceiling.ceiling_for_gateway(""), (None, "none"))
		self.assertEqual(ceiling.ceiling_for_gateway(None), (None, "none"))


class TestCachedTier(unittest.TestCase):
	def test_reads_tier_from_token_check_cache(self):
		class C:
			def get_value(self, key):
				return {"valid": True, "phone": {"tier": "TIER_10K"}}

		with patch("frappe.cache", return_value=C()):
			self.assertEqual(ceiling._cached_tier("GW"), "TIER_10K")

	def test_cache_failure_is_none(self):
		with patch("frappe.cache", side_effect=RuntimeError):
			self.assertIsNone(ceiling._cached_tier("GW"))

	def test_phone_missing_is_none(self):
		class C:
			def get_value(self, key):
				return {"valid": True, "phone": None}

		with patch("frappe.cache", return_value=C()):
			self.assertIsNone(ceiling._cached_tier("GW"))
