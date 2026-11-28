# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""PII masker (H-W2-12, pure part). All data here is synthetic.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_pii_mask_pure
"""

import copy
import hashlib
import json
from unittest import mock

from frappe.tests import UnitTestCase

from huf.ai.flow.support import pii_mask
from huf.ai.flow.support.pii_mask import mask_pii

FIRST = ["Asha", "Ravi", "Meera", "Farhan", "Latha"]
LAST = ["Menon", "Iyer", "Kurian", "Rahman", "Pillai"]


def _hash_id(i: int) -> str:
	# Starts with a long digit run, which a plain phone scan would damage.
	return "9876543210" + hashlib.sha256(str(i).encode()).hexdigest()[:30] + "f"


def _record(i: int) -> tuple[dict, list[str]]:
	first, last = FIRST[i % 5], LAST[(i // 5) % 5]
	full = f"{first} {last}"
	local = f"98{i:08d}"
	phone = [f"+91 {local[:5]} {local[5:]}", f"91{local}", f"({local[:3]}) {local[3:6]}-{local[6:]}", local][
		i % 4
	]
	email = f"{first.lower()}.{i}@example.test"
	record = {
		"customer_name": full,
		"mobile_no": phone,
		"email": email,
		"membership": _hash_id(i),
		"note": f"Hello {first}, call {phone} or mail {email} on 2026-11-27 10:15:00 for {_hash_id(i)}",
		"ref": f"ph.{local}",
		"after_date": f"2026-11-27 {local}",
		"payload": json.dumps({"fullName": full, "contact": int("91" + local)}),
		"items": [{"sender_phone": phone, "text": f"{full} ({email})"}],
		phone: "keyed by phone",
	}
	return record, [first, last, email, phone, local, local[-8:]]


class TestFlowPiiMaskPure(UnitTestCase):
	def test_corpus_of_1000_records_has_no_raw_pii_and_keeps_hash_ids(self):
		for i in range(1000):
			record, raw = _record(i)
			original = copy.deepcopy(record)
			masked = mask_pii(record)
			self.assertEqual(record, original)
			# Hash ids must survive; take them out before looking for raw values, as they contain digit runs.
			self.assertEqual(masked["membership"], _hash_id(i))
			self.assertIn(f"on 2026-11-27 10:15:00 for {_hash_id(i)}", masked["note"])
			text = json.dumps(masked).replace(_hash_id(i), "")
			for value in raw:
				self.assertNotIn(value, text, f"record {i}")

	def test_hash_id_is_exempt_under_sensitive_and_id_fields(self):
		hid = "12345678901234567890123456789012ab"
		value = {"name": hid, "conversation_id": hid, "ids": [hid], "text": f"seg:{hid}"}
		self.assertEqual(mask_pii(value), value)

	def test_short_hex_is_not_exempt(self):
		self.assertNotIn("98765432", mask_pii("id 9876543210ab"))

	def test_non_pii_values_are_unchanged(self):
		value = {"status": "sent", "count": 3, "amount": 12.5, "ok": True, "none": None, "at": "2026-11-27"}
		self.assertEqual(mask_pii(value), value)

	def test_extra_fields_are_hidden(self):
		self.assertEqual(
			mask_pii({"loyaltyCard": "AB-12", "x": "y"}, ["loyalty_card"]),
			{"loyaltyCard": "[redacted]", "x": "y"},
		)

	def test_webhook_secret_in_a_graph_is_dropped(self):
		graph = {"nodes": [{"type": "trigger.webhook", "config": {"secret": "s3cret-value"}}]}
		self.assertNotIn("s3cret-value", json.dumps(mask_pii(graph)))

	def test_unmaskable_field_is_dropped(self):
		value = {"ok": "fine", "blob": b"9876543210", "obj": object(), "list": [object(), "a"]}
		self.assertEqual(mask_pii(value), {"ok": "fine", "list": ["a"]})

	def test_masker_failure_drops_the_field_not_writes_it_raw(self):
		with mock.patch.object(pii_mask._Masker, "_string", side_effect=RuntimeError):
			self.assertEqual(mask_pii({"note": "call 9876543210", "n": 1}), {"n": 1})
			self.assertIsNone(mask_pii("call 9876543210"))
		with mock.patch.object(pii_mask, "_collect_names", side_effect=RuntimeError):
			self.assertIsNone(mask_pii({"note": "Asha"}))
