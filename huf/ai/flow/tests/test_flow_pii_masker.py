# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""H-W2-12 acceptance: personal data is masked before a trace, step error or error log is written (G4).

bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_pii_masker
"""

import random
import re
import unittest
from unittest import mock

from huf.ai.flow.support import pii
from huf.ai.flow.support.pii_mask import mask_pii

PHONE = "919876543210"
EMAIL = "asha.rao@example.com"
NAME = "Asha Raoul"
HASH_ID = "a3f9" + "1234567890" * 3 + "beef"


def _record(i: int) -> dict:
	rng = random.Random(i)
	phone = "9" + "".join(str(rng.randint(0, 9)) for _ in range(11))
	return {
		"customer_name": f"Member{i} Surname{i}",
		"phone": phone,
		"note": f"call {phone[:5]}_{phone[5:]} or {phone[:6]}/{phone[6:]} or mail m{i}@example.org",
		"amount": float(phone),
		"segment_membership": HASH_ID,
		"when": "2026-11-27T10:00:00",
	}


class TestFlowPiiMasker(unittest.TestCase):
	def test_corpus_has_no_raw_pii(self):
		for i in range(1000):
			record = _record(i)
			text = str(mask_pii(record))
			self.assertNotIn(record["phone"], text)
			self.assertNotIn(record["phone"][:6], text.replace(HASH_ID, ""))
			self.assertNotIn("@example.org", text)
			self.assertNotIn(f"Surname{i}", text)
			self.assertIn(HASH_ID, text)
			self.assertIn("2026-11-27T10:00:00", text)

	def test_float_phone_is_masked(self):
		self.assertEqual(mask_pii({"x": 919876543210.0}), {"x": "****3210"})
		self.assertEqual(mask_pii({"phone": 919876543210.0}), {"phone": "[phone]"})
		self.assertEqual(mask_pii({"price": 12.5}), {"price": 12.5})

	def test_digit_runs_split_by_underscore_or_slash(self):
		for raw in ("98765_43210", "98765/43210", "ref 987/654/3210"):
			self.assertIsNone(re.search(r"\d{5}", mask_pii(raw).replace("****", "")), raw)

	def test_docname_in_name_field_is_kept(self):
		masked = mask_pii(
			{"name": "FLOW-RUN-00042", "doctype": "Agent Flow Run", "note": "see FLOW-RUN-00042"}
		)
		self.assertEqual(masked["name"], "FLOW-RUN-00042")
		self.assertEqual(masked["note"], "see FLOW-RUN-00042")
		self.assertEqual(mask_pii({"name": NAME})["name"], "[name]")
		self.assertEqual(mask_pii({"name": HASH_ID})["name"], HASH_ID)

	def test_app_fields_from_hook(self):
		with mock.patch.object(pii, "app_pii_fields", return_value=("loyalty_card",)):
			self.assertEqual(
				pii.mask_value({"loyalty_card": "LC-1", "tier": "gold"}),
				{"loyalty_card": "[redacted]", "tier": "gold"},
			)

	def test_unmaskable_value_is_dropped_not_written_raw(self):
		with mock.patch.object(pii, "mask_pii", return_value=None):
			self.assertEqual(pii.mask_text(f"failed for {PHONE}"), pii.DROPPED)
		self.assertEqual(pii.mask_text(""), "")
		self.assertIsNone(pii.mask_text(None))

	def test_error_log_is_masked(self):
		fake = mock.MagicMock()
		fake.get_hooks.return_value = []
		with mock.patch.dict("sys.modules", {"frappe": fake}):
			pii.log_flow_error(f"Traceback: bad {PHONE} {EMAIL}", "Flow node n1 raised")
		message = fake.log_error.call_args.args[0]
		self.assertNotIn(PHONE, message)
		self.assertNotIn(EMAIL, message)
		self.assertEqual(fake.log_error.call_args.args[1], "Flow node n1 raised")

	def test_step_error_record_is_masked(self):
		try:
			from huf.ai.flow.engine import failed_node_record
			from huf.ai.graph.executor import Outcome
		except ImportError:
			self.skipTest("needs a bench")
		outcome = Outcome.from_mapping({"status": "failed", "error": f"no reply from {PHONE} ({EMAIL})"})
		record = failed_node_record(outcome)
		self.assertNotIn(PHONE, record["error"])
		self.assertNotIn(EMAIL, record["error"])
		self.assertEqual(record["status"], "failed")
