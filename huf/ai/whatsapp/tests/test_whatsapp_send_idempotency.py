# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-9: agent/tool WhatsApp sends are idempotent (durable key, one message per tool call)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp import send_keys as keys
from huf.ai.tools import whatsapp

GW = "GW-IDEM"


def _ok(mid="wamid.1"):
	return json.dumps({"success": True, "data": {"message_id": mid, "recipient": "1555", "status": "sent"}})


class _Base(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)
		self.sent = MagicMock(side_effect=[_ok("wamid.1"), _ok("wamid.2"), _ok("wamid.3")])
		self.addCleanup(patch.stopall)
		patch.object(whatsapp, "_run_gateway", return_value=GW).start()
		patch.object(whatsapp, "_authorize", return_value=None).start()
		patch.object(whatsapp, "_scope_refusal", return_value=None).start()
		patch.object(whatsapp, "_send_message", self.sent).start()
		patch.object(whatsapp, "_send_media", self.sent).start()
		patch.object(whatsapp, "_send_template", self.sent).start()

	def _clean(self):
		frappe.db.delete("WhatsApp Send Key", {"gateway": GW})
		frappe.db.commit()

	def call(self, action="send_message", run="RUN-1", **kw):
		kw.setdefault("to", "15551234567")
		if action == "send_message":
			kw.setdefault("message", "hello")
		with patch.dict(frappe.flags, {"huf_current_agent_run_id": run}):
			return json.loads(whatsapp.handle_action(action, **kw))


class TestSameCallIsOneMessage(_Base):
	def test_retry_of_same_tool_call_sends_once_and_returns_original(self):
		first = self.call(call_id="call_a")
		second = self.call(call_id="call_a")
		self.assertEqual(self.sent.call_count, 1)
		self.assertTrue(first["success"])
		self.assertNotIn("deduplicated", first)
		self.assertTrue(second["deduplicated"])
		self.assertEqual(second["data"]["message_id"], "wamid.1")

	def test_different_tool_calls_with_identical_payload_both_send(self):
		self.call(call_id="call_a")
		second = self.call(call_id="call_b")
		self.assertEqual(self.sent.call_count, 2)
		self.assertNotIn("deduplicated", second)

	def test_different_payload_or_run_is_not_suppressed(self):
		self.call(call_id="call_a")
		self.call(call_id="call_a", message="other")
		self.call(call_id="call_a", run="RUN-2")
		self.assertEqual(self.sent.call_count, 3)

	def test_without_call_id_same_run_and_payload_dedupes(self):
		self.call()
		again = self.call()
		self.assertEqual(self.sent.call_count, 1)
		self.assertTrue(again["deduplicated"])

	def test_recipient_formatting_does_not_defeat_the_key(self):
		self.call(call_id="c", to="+1 (555) 123-4567")
		self.call(call_id="c", to="15551234567")
		self.assertEqual(self.sent.call_count, 1)


class TestNoRunNoAutoKey(_Base):
	def test_without_a_run_or_explicit_key_nothing_is_deduplicated_but_each_send_is_claimed(self):
		self.call(run=None)
		self.call(run=None)
		self.assertEqual(self.sent.call_count, 2)
		self.assertEqual(frappe.db.count("WhatsApp Send Key", {"gateway": GW}), 2)

	def test_explicit_key_works_without_a_run(self):
		self.call(run=None, idempotency_key="flow-1")
		self.call(run=None, idempotency_key="flow-1")
		self.assertEqual(self.sent.call_count, 1)


class TestExplicitKey(_Base):
	def test_explicit_key_dedupes_across_calls_and_payload_within_a_run_and_recipient(self):
		self.call(idempotency_key="order-42", call_id="x")
		again = self.call(idempotency_key="order-42", call_id="y", message="reworded")
		self.assertEqual(self.sent.call_count, 1)
		self.assertTrue(again["deduplicated"])

	def test_explicit_key_is_scoped_to_the_gateway(self):
		self.call(idempotency_key="k")
		with patch.object(whatsapp, "_run_gateway", return_value="GW-OTHER"):
			self.call(idempotency_key="k")
		frappe.db.delete("WhatsApp Send Key", {"gateway": "GW-OTHER"})
		self.assertEqual(self.sent.call_count, 2)

	def test_overlong_or_blank_key_is_ignored_or_refused(self):
		blank = self.call(idempotency_key="   ", call_id="a")
		self.assertTrue(blank["success"])
		long = self.call(idempotency_key="k" * 300)
		self.assertEqual(long["error"], "invalid_idempotency_key")


class TestCoverage(_Base):
	def test_media_and_template_are_covered(self):
		for action, extra in (("send_image", {"link": "https://x/y.png"}), ("send_template", {"template_name": "t"})):
			self.sent.reset_mock(side_effect=True)
			self.sent.side_effect = [_ok("wamid.a"), _ok("wamid.b")]
			self.call(action, call_id=action, **extra)
			again = self.call(action, call_id=action, **extra)
			self.assertEqual(self.sent.call_count, 1, action)
			self.assertTrue(again["deduplicated"], action)

	def test_reads_are_never_deduplicated(self):
		with patch.object(whatsapp, "_list_messages", return_value=_ok()) as listing:
			self.call("list_messages", call_id="c")
			self.call("list_messages", call_id="c")
		self.assertEqual(listing.call_count, 2)


class TestFailuresAndDurability(_Base):
	def test_definitely_refused_send_releases_the_key_so_a_retry_sends(self):
		self.sent.side_effect = [json.dumps({"success": False, "error": "invalid_thing"}), _ok("wamid.2")]
		self.call(call_id="c")
		retry = self.call(call_id="c")
		self.assertEqual(self.sent.call_count, 2)
		self.assertTrue(retry["success"])
		self.assertNotIn("deduplicated", retry)

	def test_permission_error_releases_the_key(self):
		self.sent.side_effect = [frappe.PermissionError("x"), _ok()]
		with self.assertRaises(frappe.PermissionError):
			self.call(call_id="c")
		self.assertTrue(self.call(call_id="c")["success"])
		self.assertEqual(self.sent.call_count, 2)

	def test_key_is_stored_in_the_database_not_the_cache(self):
		self.call(call_id="c")
		rows = frappe.get_all("WhatsApp Send Key", filters={"gateway": GW}, fields=["status", "message_id", "expires_at"])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].status, "Sent")
		self.assertEqual(rows[0].message_id, "wamid.1")
		self.assertGreater(rows[0].expires_at, add_to_date(now_datetime(), hours=23))

	def test_in_flight_duplicate_is_refused_not_resent(self):
		key = keys.derive_key(GW, "RUN-1", "call_a", "send_message", {"to": "15551234567", "message": "hello"})
		keys._claim(GW, key)
		result = self.call(call_id="call_a")
		self.assertEqual(result["error"], "send_in_progress")
		self.assertEqual(self.sent.call_count, 0)

	def test_expired_key_allows_a_new_send_and_purge_removes_it(self):
		self.call(call_id="c")
		frappe.db.set_value("WhatsApp Send Key", {"gateway": GW}, "expires_at", add_to_date(now_datetime(), hours=-1))
		again = self.call(call_id="c")
		self.assertEqual(self.sent.call_count, 2)
		self.assertNotIn("deduplicated", again)
		frappe.db.set_value("WhatsApp Send Key", {"gateway": GW}, "expires_at", add_to_date(now_datetime(), hours=-1))
		keys.purge_expired()
		self.assertEqual(frappe.db.count("WhatsApp Send Key", {"gateway": GW}), 0)


class TestPolicyNotWeakened(_Base):
	def test_policy_refusal_is_not_cached_as_a_sent_message(self):
		self.sent.side_effect = [json.dumps({"success": False, "error": "opted_out"}), _ok()]
		self.call(call_id="c")
		later = self.call(call_id="c")
		self.assertTrue(later["success"])  # contact opted back in: the retry is evaluated afresh
		self.assertEqual(self.sent.call_count, 2)


if __name__ == "__main__":
	unittest.main()
