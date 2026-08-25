"""Tests for timezone handling in huf.ai.agent_run_analytics_api.get_execution_analytics.

The frontend sends from_date/to_date as ISO strings (often with a Z/offset
suffix), which frappe.utils.get_datetime parses as timezone-aware, while
now_datetime()/add_to_date() return naive local datetimes. Mixing aware and
naive datetimes in a comparison raises
"TypeError: can't compare offset-naive and offset-aware datetimes". This
test exercises the real function (unwrapped via .__wrapped__, since
frappe.whitelist() decorates it) with frappe itself mocked out, so no live
site/DB is required, and asserts both aware and naive inputs are handled
without raising.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from huf.ai import agent_run_analytics_api as api_module


def _unwrapped(func):
	"""Unwrap a frappe.whitelist()-decorated function down to the plain callable."""
	while hasattr(func, "__wrapped__"):
		func = func.__wrapped__
	return func


get_execution_analytics = _unwrapped(api_module.get_execution_analytics)


class TestGetExecutionAnalyticsTimezoneHandling(unittest.TestCase):
	def _mock_frappe(self, mock_frappe):
		# Grant access via System Manager so _require_analytics_access short-circuits.
		mock_frappe.session.user = "admin@example.com"
		mock_frappe.get_roles.return_value = ["System Manager"]
		# No rollup doctype yet -> function returns the empty-result shape
		# immediately after the date-window validation, which is exactly the
		# code path we need to exercise the tz-normalization logic.
		mock_frappe.db.exists.return_value = False
		mock_frappe.throw.side_effect = RuntimeError

	@patch("huf.ai.agent_run_analytics_api.frappe")
	def test_handles_timezone_aware_from_and_to_date(self, mock_frappe):
		self._mock_frappe(mock_frappe)
		aware_now = datetime.now(timezone.utc)
		from_date = (aware_now - timedelta(days=1)).isoformat()
		to_date = aware_now.isoformat()

		# get_datetime/now_datetime/add_to_date are imported by name into the
		# module, so they must be patched there directly rather than as
		# attributes of the mocked `frappe` module.
		with patch.object(api_module, "get_datetime", side_effect=lambda v: datetime.fromisoformat(v)):
			result = get_execution_analytics(from_date=from_date, to_date=to_date, granularity="hour")

		self.assertEqual(result["series"], [])

	@patch("huf.ai.agent_run_analytics_api.frappe")
	def test_handles_naive_datetimes_without_raising(self, mock_frappe):
		self._mock_frappe(mock_frappe)
		naive_now = datetime.now()

		with patch.object(api_module, "now_datetime", return_value=naive_now), patch.object(
			api_module, "add_to_date", return_value=naive_now - timedelta(days=7)
		):
			result = get_execution_analytics(granularity="hour")

		self.assertEqual(result["series"], [])

	@patch("huf.ai.agent_run_analytics_api.frappe")
	def test_mixed_aware_from_date_and_naive_end_does_not_raise(self, mock_frappe):
		# Regression check for the exact bug fix #6 addresses: from_date is
		# tz-aware (parsed via get_datetime from an ISO string with an
		# offset), while `end` defaults to the naive now_datetime(). Without
		# the fix, `start > end` below would raise TypeError.
		self._mock_frappe(mock_frappe)
		aware_from = datetime.now(timezone.utc) - timedelta(days=1)
		naive_end = datetime.now()

		with patch.object(api_module, "get_datetime", return_value=aware_from), patch.object(
			api_module, "now_datetime", return_value=naive_end
		):
			result = get_execution_analytics(from_date="irrelevant-because-mocked", granularity="hour")

		self.assertEqual(result["series"], [])


if __name__ == "__main__":
	unittest.main()
