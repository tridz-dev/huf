# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-2: broadcast recipient intake (normalize, prepare, parse_csv). Store and policy helpers are patched."""

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.whatsapp.broadcast import recipients as br

BC = "BCAST-00001"
GW = "GW-BCAST"


def _broadcast(category="UTILITY", max_recipients=1000):
	doc = MagicMock(name="broadcast")
	doc.gateway = GW
	doc.category = category
	doc.max_recipients = max_recipients
	return doc


class TestNormalizeRecipient(unittest.TestCase):
	def test_plus_spaces_dashes_parens_become_digits(self):
		self.assertEqual(br.normalize_recipient("+1 (555) 000-1111"), "15550001111")

	def test_double_zero_prefix_is_stripped(self):
		self.assertEqual(br.normalize_recipient("0044 7700 900123"), "447700900123")

	def test_numeric_input_accepted(self):
		self.assertEqual(br.normalize_recipient(447700900123), "447700900123")

	def test_too_short_is_invalid(self):
		self.assertIsNone(br.normalize_recipient("1234567"))

	def test_too_long_is_invalid(self):
		self.assertIsNone(br.normalize_recipient("1" * 16))

	def test_letters_only_is_invalid(self):
		self.assertIsNone(br.normalize_recipient("call me"))

	def test_empty_and_none_are_invalid(self):
		self.assertIsNone(br.normalize_recipient(""))
		self.assertIsNone(br.normalize_recipient("   "))
		self.assertIsNone(br.normalize_recipient(None))

	def test_bsuid_passes_through(self):
		self.assertEqual(br.normalize_recipient("IN.4608123"), "IN.4608123")


class TestParseCsv(unittest.TestCase):
	def test_bom_and_phone_header(self):
		rows = br.parse_csv("﻿phone\n+15550001111\n15550002222\n")
		self.assertEqual([r["recipient"] for r in rows], ["+15550001111", "15550002222"])
		self.assertEqual(rows[0]["params"], {"body": []})

	def test_recipient_header_variant_and_case(self):
		rows = br.parse_csv(" Recipient \n15550001111\n")
		self.assertEqual(rows[0]["recipient"], "15550001111")

	def test_phone_number_and_dashed_header_variants(self):
		self.assertEqual(br.parse_csv("Phone_Number\n15550001111\n")[0]["recipient"], "15550001111")
		self.assertEqual(br.parse_csv("phone-number\n15550001111\n")[0]["recipient"], "15550001111")

	def test_quoted_fields_with_commas_and_newlines(self):
		text = 'name,phone,city\n"Doe, Jane",15550001111,"Austin, TX"\n'
		rows = br.parse_csv(text)
		self.assertEqual(rows[0]["recipient"], "15550001111")
		self.assertEqual(rows[0]["params"], {"body": ["Doe, Jane", "Austin, TX"]})

	def test_extra_columns_become_body_in_column_order(self):
		text = "first,phone,last\nAna,15550001111,Lee\n"
		rows = br.parse_csv(text)
		self.assertEqual(rows[0]["params"], {"body": ["Ana", "Lee"]})

	def test_blank_lines_skipped_and_short_rows_padded(self):
		text = "phone,a,b\n\n15550001111,x\n   \n15550002222,y,z\n"
		rows = br.parse_csv(text)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["params"], {"body": ["x", ""]})
		self.assertEqual(rows[1]["params"], {"body": ["y", "z"]})

	def test_missing_phone_column_raises(self):
		with self.assertRaises(ValueError):
			br.parse_csv("name,city\nAna,Austin\n")

	def test_empty_text_returns_no_rows(self):
		self.assertEqual(br.parse_csv(""), [])


class TestPrepare(unittest.TestCase):
	def setUp(self):
		self.inserted = []
		self.existing = set()
		self.active = 0
		self.opted_out = set()
		self.marketing_stopped = set()
		self.broadcast = _broadcast()

		patches = [
			patch.object(br, "_load_broadcast", side_effect=lambda name: self.broadcast),
			patch.object(br, "_existing_names", side_effect=lambda name: set(self.existing)),
			patch.object(br, "_active_count", side_effect=lambda name: self.active),
			patch.object(br, "_insert_row", side_effect=self._insert),
			patch("huf.ai.gateway_service.is_opted_out", side_effect=lambda gw, s: s in self.opted_out),
			patch(
				"huf.ai.whatsapp.account_events.is_marketing_allowed",
				side_effect=lambda gw, s: s not in self.marketing_stopped,
			),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def _insert(self, broadcast, recipient, status, skip_reason, params, consent_source, consent_at):
		self.inserted.append(
			{
				"recipient": recipient,
				"status": status,
				"skip_reason": skip_reason,
				"params": params,
				"consent_source": consent_source,
				"consent_at": consent_at,
			}
		)

	def _prepare(self, rows):
		return br.prepare(BC, rows)

	def test_queues_valid_recipients_and_recounts(self):
		result = self._prepare([{"recipient": "+15550001111"}, {"recipient": "447700900123"}])
		self.assertEqual(result["added"], 2)
		self.assertEqual(result["skipped"], [])
		self.assertEqual(result["invalid"], [])
		self.assertEqual([r["status"] for r in self.inserted], ["queued", "queued"])
		self.broadcast.recount.assert_called_once()

	def test_dedupes_within_input(self):
		result = self._prepare([{"recipient": "+15550001111"}, {"recipient": "1-555-000-1111"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(result["skipped"], [{"recipient": "15550001111", "reason": "duplicate"}])

	def test_dedupes_against_existing_rows(self):
		self.existing = {f"{BC}-15550001111"}
		result = self._prepare([{"recipient": "15550001111"}])
		self.assertEqual(result["added"], 0)
		self.assertEqual(result["skipped"], [{"recipient": "15550001111", "reason": "duplicate"}])
		self.assertEqual(self.inserted, [])

	def test_invalid_numbers_reported_and_not_stored(self):
		result = self._prepare([{"recipient": "abc"}, {"recipient": "123"}, {"recipient": "15550001111"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(len(result["invalid"]), 2)
		self.assertEqual(result["invalid"][0]["reason"], "invalid_number")
		self.assertEqual(len(self.inserted), 1)

	def test_stop_contact_stored_as_skipped_with_reason(self):
		self.opted_out.add("15550001111")
		result = self._prepare([{"recipient": "15550001111"}])
		self.assertEqual(result["added"], 0)
		self.assertEqual(result["skipped"], [{"recipient": "15550001111", "reason": "opted_out"}])
		self.assertEqual(self.inserted[0]["status"], "skipped")
		self.assertEqual(self.inserted[0]["skip_reason"], "opted_out")

	def test_marketing_stopped_contact_skipped_for_marketing_only(self):
		self.marketing_stopped.add("447700900123")
		self.broadcast.category = "MARKETING"
		result = self._prepare([{"recipient": "447700900123"}])
		self.assertEqual(result["skipped"], [{"recipient": "447700900123", "reason": "marketing_opted_out"}])

		self.inserted.clear()
		self.broadcast.category = "UTILITY"
		result = self._prepare([{"recipient": "447700900123"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(result["skipped"], [])

	def test_us_plus_one_skipped_for_marketing_only(self):
		self.broadcast.category = "MARKETING"
		result = self._prepare([{"recipient": "+1 555 000 1111"}, {"recipient": "447700900123"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(result["skipped"], [{"recipient": "15550001111", "reason": "us_plus_one_marketing"}])

		self.inserted.clear()
		self.broadcast.category = "UTILITY"
		result = self._prepare([{"recipient": "+1 555 000 1111"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(result["skipped"], [])

	def test_bsuid_recipient_skipped_by_outbound_policy(self):
		result = self._prepare([{"recipient": "IN.4608123"}])
		self.assertEqual(result["added"], 0)
		self.assertEqual(result["skipped"], [{"recipient": "IN.4608123", "reason": "bsuid_recipient"}])

	def test_max_recipients_enforced_against_active_rows(self):
		self.broadcast.max_recipients = 2
		self.active = 1  # one queued row already exists
		result = self._prepare([{"recipient": "15550001111"}, {"recipient": "15550002222"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(result["skipped"], [{"recipient": "15550002222", "reason": "max_recipients"}])
		self.assertEqual([r["recipient"] for r in self.inserted], ["15550001111"])

	def test_max_recipients_does_not_count_skipped_policy_rows(self):
		self.broadcast.max_recipients = 1
		self.opted_out.add("15550001111")
		result = self._prepare([{"recipient": "15550001111"}, {"recipient": "15550002222"}])
		self.assertEqual(result["added"], 1)
		self.assertEqual(result["skipped"], [{"recipient": "15550001111", "reason": "opted_out"}])

	def test_max_skipped_contact_is_not_stored_so_a_later_run_can_add_it(self):
		self.broadcast.max_recipients = 1
		result = self._prepare([{"recipient": "15550001111"}, {"recipient": "15550002222"}])
		self.assertEqual(result["skipped"], [{"recipient": "15550002222", "reason": "max_recipients"}])
		self.assertEqual([r["recipient"] for r in self.inserted], ["15550001111"])

	def test_params_and_consent_are_stored(self):
		self._prepare(
			[
				{
					"recipient": "15550001111",
					"params": {"body": ["Ana"]},
					"consent_source": "CSV import",
					"consent_at": "2026-10-27 09:00:00",
				}
			]
		)
		row = self.inserted[0]
		self.assertEqual(row["params"], {"body": ["Ana"]})
		self.assertEqual(row["consent_source"], "CSV import")
		self.assertEqual(row["consent_at"], "2026-10-27 09:00:00")

	def test_non_dict_params_are_dropped(self):
		self._prepare([{"recipient": "15550001111", "params": "oops"}])
		self.assertIsNone(self.inserted[0]["params"])


if __name__ == "__main__":
	unittest.main()
