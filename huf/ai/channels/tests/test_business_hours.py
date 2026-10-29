from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import hours
from huf.ai.channels.pipeline import Decision

# 2026-11-02 is a Monday (UTC). Times below are UTC unless a test sets another site timezone.
MON_1000 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
MON_0859 = datetime(2026, 11, 2, 8, 59, tzinfo=timezone.utc)
MON_1700 = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
MON_1800 = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
TUE_1000 = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
NEXT_MON_1800 = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


def _hours(*rows):
	return [{"weekday": w, "start_time": s, "end_time": e} for w, s, e in rows]


class _Base(IntegrationTestCase):
	def setUp(self):
		self.suffix = frappe.generate_hash(length=6)
		p = patch.object(hours, "_site_timezone", return_value="UTC")
		p.start()
		self.addCleanup(p.stop)

	def tearDown(self):
		frappe.db.rollback()

	def unsaved(self, **kw):
		values = {
			"doctype": "Gateway",
			"gateway_name": f"bh-{self.suffix}",
			"provider": "Telegram",
			"business_hours_enabled": 1,
			"business_hours": _hours(("Monday", "09:00:00", "17:00:00")),
		}
		values.update(kw)
		return frappe.get_doc(values)

	def saved(self, **kw):
		gw = self.unsaved(is_enabled=0, **kw)
		gw.insert(ignore_permissions=True)
		return gw

	def at(self, when):
		return patch.object(hours, "_utcnow", return_value=when)


class TestIsOpen(_Base):
	def test_open_inside_weekday_window(self):
		gw = self.unsaved()
		self.assertTrue(hours.is_open(gw, MON_1000))

	def test_closed_before_start_and_at_end(self):
		gw = self.unsaved()
		self.assertFalse(hours.is_open(gw, MON_0859))
		self.assertFalse(hours.is_open(gw, MON_1700))

	def test_closed_on_weekday_without_row(self):
		gw = self.unsaved()
		self.assertFalse(hours.is_open(gw, TUE_1000))

	def test_overnight_range_open_before_midnight_and_in_tail(self):
		gw = self.unsaved(business_hours=_hours(("Friday", "22:00:00", "02:00:00")))
		fri_2300 = datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc)
		sat_0100 = datetime(2026, 11, 7, 1, 0, tzinfo=timezone.utc)
		sat_0300 = datetime(2026, 11, 7, 3, 0, tzinfo=timezone.utc)
		fri_0100 = datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)
		self.assertTrue(hours.is_open(gw, fri_2300))
		self.assertTrue(hours.is_open(gw, sat_0100))
		self.assertFalse(hours.is_open(gw, sat_0300))
		self.assertFalse(hours.is_open(gw, fri_0100))

	def test_site_timezone_is_applied(self):
		gw = self.unsaved()
		with patch.object(hours, "_site_timezone", return_value="Asia/Dubai"):
			# 06:00 UTC is 10:00 in Dubai (UTC+4): open. 04:00 UTC is 08:00 Dubai: closed.
			self.assertTrue(hours.is_open(gw, datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)))
			self.assertFalse(hours.is_open(gw, datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)))

	def test_holiday_closes_open_window_when_holidays_patched(self):
		gw = self.unsaved(holiday_list="Test Holidays")
		with patch.object(hours, "_holidays", return_value={date(2026, 11, 2)}):
			self.assertFalse(hours.is_open(gw, MON_1000))

	def test_holiday_child_row_closes_open_window(self):
		# Real Gateway Holiday child rows, no patching of _holidays.
		gw = self.unsaved(holidays=[{"holiday_date": "2026-11-02", "description": "Election day"}])
		self.assertFalse(hours.is_open(gw, MON_1000))

	def test_holiday_child_row_on_other_date_does_not_close(self):
		gw = self.unsaved(holidays=[{"holiday_date": "2026-11-03", "description": "Not Monday"}])
		self.assertTrue(hours.is_open(gw, MON_1000))

	def test_holidays_union_child_rows_and_holiday_list(self):
		gw = self.unsaved(holidays=[{"holiday_date": "2026-11-02"}], holiday_list="Public Holidays")
		erp_list = {"holidays": [SimpleNamespace(holiday_date=date(2026, 11, 3))]}
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_cached_doc", return_value=erp_list) as cached,
		):
			self.assertEqual(hours._holidays(gw), {date(2026, 11, 2), date(2026, 11, 3)})
		cached.assert_called_once_with("Holiday List", "Public Holidays")
		self.assertFalse(hours.is_open(gw, datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)))

	def test_holiday_list_name_ignored_without_holiday_list_doctype(self):
		gw = self.unsaved(holiday_list="Public Holidays")
		with patch.object(frappe.db, "exists", side_effect=lambda dt, *a, **k: False):
			self.assertEqual(hours._holidays(gw), set())
			self.assertTrue(hours.is_open(gw, MON_1000))

	def test_holiday_list_name_missing_document_is_ignored(self):
		gw = self.unsaved(holiday_list="Deleted List", holidays=[{"holiday_date": "2026-11-09"}])
		with patch.object(frappe.db, "exists", side_effect=lambda dt, *a, **k: dt == "DocType"):
			self.assertEqual(hours._holidays(gw), {date(2026, 11, 9)})

	def test_disabled_means_no_restriction(self):
		gw = self.unsaved(business_hours_enabled=0)
		self.assertTrue(hours.is_open(gw, TUE_1000))


class TestBusinessHoursHook(_Base):
	def test_noop_without_gateway(self):
		self.assertIsNone(hours.business_hours_hook({}))

	def test_disabled_passthrough(self):
		gw = self.saved(business_hours_enabled=0, after_hours_mode="away_message", away_message="closed")
		with self.at(TUE_1000):
			self.assertIsNone(hours.business_hours_hook({"gateway": gw.name, "context": {"sender_id": "1"}}))

	def test_open_passthrough(self):
		gw = self.saved(after_hours_mode="away_message", away_message="closed")
		with self.at(MON_1000):
			self.assertIsNone(hours.business_hours_hook({"gateway": gw.name, "context": {"sender_id": "1"}}))

	def test_24_7_passthrough_when_closed(self):
		gw = self.saved(after_hours_mode="agent_24_7", away_message="closed")
		with self.at(TUE_1000):
			self.assertIsNone(hours.business_hours_hook({"gateway": gw.name, "context": {"sender_id": "1"}}))

	def test_away_message_replies_once_per_closed_window(self):
		conv = f"conv-{self.suffix}"
		gw = self.saved(after_hours_mode="away_message", away_message="We are closed")
		ctx = {"gateway": gw.name, "context": {"sender_id": "1", "conversation_id": conv}}
		with self.at(MON_1800):
			first = hours.business_hours_hook(ctx)
			again = hours.business_hours_hook(ctx)
		self.assertEqual(first.action, "reply")
		self.assertEqual(first.payload, {"text": "We are closed"})
		self.assertIsInstance(first, Decision)
		self.assertEqual(again.action, "drop")

		# Tuesday is closed too, but it is the same closed window (next open is Monday 09:00): no second reply.
		with self.at(TUE_1000):
			self.assertEqual(hours.business_hours_hook(ctx).action, "drop")

		# Next Monday evening is a new closed window: reply again.
		with self.at(NEXT_MON_1800):
			self.assertEqual(hours.business_hours_hook(ctx).action, "reply")

	def test_away_template_sends_template_with_text_fallback(self):
		gw = self.saved(after_hours_mode="away_template", away_template="closed_notice", away_message="Back at 9")
		with self.at(TUE_1000):
			d = hours.business_hours_hook({"gateway": gw.name, "context": {"sender_id": f"t-{self.suffix}"}})
		self.assertEqual(d.action, "reply")
		self.assertEqual(d.payload, {"template": "closed_notice", "text": "Back at 9"})
