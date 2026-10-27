# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-12: WhatsApp Broadcast cost estimate and typed-count confirm token."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from huf.ai.whatsapp import broadcast_cost as cost

MOD = "huf.ai.whatsapp.broadcast_cost"


def _rows(*numbers, status="queued"):
	return [{"recipient": n, "status": status} for n in numbers]


class _Base(unittest.TestCase):
	def _estimate(self, rows, category="marketing"):
		with (
			patch(f"{MOD}._pending_rows", return_value=rows),
			patch(f"{MOD}._category", return_value=category),
		):
			return cost.estimate("BCAST-00001")


class TestMarketForRecipient(_Base):
	def test_known_markets_by_dialling_code(self):
		cases = {
			"919876543210": "IN",
			"15555550100": "US",
			"447700900123": "GB",
			"5511999990000": "BR",
			"6281234567890": "ID",
			"5215512345678": "MX",
			"971501234567": "AE",
			"4915112345678": "DE",
			"33612345678": "FR",
			"34612345678": "ES",
			"966501234567": "SA",
			"2348012345678": "NG",
			"27821234567": "ZA",
		}
		for number, market in cases.items():
			with self.subTest(number=number):
				self.assertEqual(cost.market_for_recipient(number), market)

	def test_plus_and_spaces_are_ignored(self):
		self.assertEqual(cost.market_for_recipient("+44 7700 900123"), "GB")

	def test_unknown_dialling_code(self):
		self.assertEqual(cost.market_for_recipient("9999999999"), cost.UNKNOWN_MARKET)

	def test_bsuid_and_empty_are_unknown(self):
		self.assertEqual(cost.market_for_recipient("US.abc123"), cost.UNKNOWN_MARKET)
		self.assertEqual(cost.market_for_recipient(""), cost.UNKNOWN_MARKET)
		self.assertEqual(cost.market_for_recipient(None), cost.UNKNOWN_MARKET)

	def test_longest_prefix_wins(self):
		codes = {"2": "XX", "27": "ZA"}
		self.assertEqual(cost.market_for_recipient("27821234567", codes), "ZA")
		self.assertEqual(cost.market_for_recipient("2123", codes), "XX")


class TestConfirmToken(_Base):
	def test_token_is_pending_count_as_string(self):
		rows = _rows("919876543210", "919876543211", "15555550100")
		with patch(f"{MOD}._pending_rows", return_value=rows):
			self.assertEqual(cost.confirm_token("BCAST-00001"), "3")

	def test_zero_pending(self):
		with patch(f"{MOD}._pending_rows", return_value=[]):
			self.assertEqual(cost.confirm_token("BCAST-00001"), "0")


class TestEstimate(_Base):
	def test_null_rates_give_null_total_and_warnings(self):
		# Rate card ships unverified: every known market has rate None.
		result = self._estimate(_rows("919876543210", "919876543211"))
		self.assertEqual(result["currency"], "USD")
		self.assertIsNone(result["total"])
		self.assertEqual(result["by_country"]["IN"], {"count": 2, "rate": None, "subtotal": None})
		self.assertIn("rate_unavailable:marketing:IN", result["warnings"])
		self.assertEqual(result["category"], "marketing")
		self.assertTrue(result["basis"].startswith("rate_card_"))
		self.assertFalse(result["rates_verified"])

	def test_disclaimer_always_present(self):
		result = self._estimate([])
		self.assertIn("Billing is by Meta", result["disclaimer"])
		self.assertIn("may differ", result["disclaimer"])

	def test_empty_broadcast_totals_zero(self):
		result = self._estimate([])
		self.assertEqual(result["total"], 0.0)
		self.assertEqual(result["by_country"], {})
		self.assertEqual(result["warnings"], [])

	def test_unknown_market_warns_and_nulls_total(self):
		result = self._estimate(_rows("9999999999"))
		self.assertIsNone(result["total"])
		self.assertIn("market_unknown:1_recipients", result["warnings"])
		self.assertEqual(result["by_country"][cost.UNKNOWN_MARKET]["count"], 1)

	def test_unsupported_category_warns(self):
		result = self._estimate(_rows("919876543210"), category="authentication")
		self.assertIsNone(result["total"])
		self.assertIn("rate_unavailable:authentication:IN", result["warnings"])

	def test_missing_category_warns(self):
		result = self._estimate(_rows("919876543210"), category=None)
		self.assertIn("category_missing", result["warnings"])
		self.assertIsNone(result["total"])

	def test_total_sums_when_rates_present(self):
		rates = {
			"currency": "USD",
			"retrieved": "2026-10-27",
			"rates_verified": True,
			"disclaimer": "d",
			"dialling_codes": {"91": "IN", "1": "US"},
			"rates": {"marketing": {"IN": 0.5, "US": 1.25}, "utility": {}},
		}
		with patch(f"{MOD}._load_rates", return_value=rates):
			result = self._estimate(_rows("919876543210", "919876543211", "15555550100"))
		self.assertEqual(result["by_country"]["IN"], {"count": 2, "rate": 0.5, "subtotal": 1.0})
		self.assertEqual(result["by_country"]["US"], {"count": 1, "rate": 1.25, "subtotal": 1.25})
		self.assertEqual(result["total"], 2.25)
		self.assertEqual(result["warnings"], [])
		self.assertTrue(result["rates_verified"])

	def test_pending_rows_query_uses_queued_and_deferred(self):
		with patch(f"{MOD}.frappe.get_all", return_value=[]) as get_all:
			cost._pending_rows("BCAST-00001")
		filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["broadcast"], "BCAST-00001")
		self.assertEqual(filters["status"], ["in", ["queued", "deferred"]])


class TestRatesFile(unittest.TestCase):
	def test_rates_file_has_source_and_date(self):
		rates = cost._load_rates()
		self.assertTrue(rates["source_url"].startswith("https://developers.facebook.com/"))
		self.assertRegex(rates["retrieved"], r"^\d{4}-\d{2}-\d{2}$")
		self.assertEqual(rates["currency"], "USD")

	def test_required_markets_covered(self):
		rates = cost._load_rates()
		for market in ("IN", "US", "GB", "BR", "ID", "MX", "AE", "DE", "FR", "ES", "SA", "NG", "ZA"):
			self.assertIn(market, set(rates["dialling_codes"].values()))
			self.assertIn(market, rates["rates"]["marketing"])
			self.assertIn(market, rates["rates"]["utility"])
