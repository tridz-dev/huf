# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-6: broadcast recipient status application (monotonic, dedupe, errors, pause, user stop).

Uses an in-memory stand-in for the two doctypes' rows so the rank/dedupe logic is exercised
without a database; the webhook fixtures drive the payload shapes.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.whatsapp import broadcast_status as bs

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
GW = "GW-1"


def fixture_status(name):
	return json.loads((FIXTURES / name).read_text())["entry"][0]["changes"][0]["value"]["statuses"][0]


class FakeDB:
	def __init__(self):
		self.recipients = {}
		self.broadcasts = {"BC-1": {"gateway": GW, "status": "Running"}, "BC-2": {"gateway": "GW-2", "status": "Running"}, "BC-3": {"gateway": GW, "status": "Completed"}}

	def add(self, name, broadcast="BC-1", status="sent", wamid=None, recipient="15551234567"):
		self.recipients[name] = {"name": name, "broadcast": broadcast, "status": status, "wamid": wamid, "recipient": recipient, "skip_reason": None, "error_code": None}

	def sql(self, query, args=None):
		q = " ".join(query.split())
		if q.startswith("update") and "skip_reason='opted_out'" in q:
			row = self.recipients[args]
			if row["status"] in ("queued", "deferred"):
				row.update(status="skipped", skip_reason="opted_out")
			return None
		if q.startswith("update"):
			row = self.recipients[args["_name"]]
			if row["status"] == args["_current"]:
				row.update({k: v for k, v in args.items() if not k.startswith("_")})
			return None
		if q.startswith("select 1") and "skip_reason='opted_out'" in q:
			row = self.recipients[args]
			return [(1,)] if row["status"] == "skipped" and row["skip_reason"] == "opted_out" else []
		if q.startswith("select 1"):
			row = self.recipients[args[0]]
			return [(1,)] if row["status"] == args[1] else []
		if "join" in q:
			gateway, live, key = args
			return [
				(r["name"], r["broadcast"])
				for r in self.recipients.values()
				if self.broadcasts[r["broadcast"]]["gateway"] == gateway
				and self.broadcasts[r["broadcast"]]["status"] in live
				and r["recipient"] == key
				and r["status"] in ("queued", "deferred")
			]
		raise AssertionError(q)


class FakeFrappe:
	def __init__(self, db):
		self.db = db
		self.recounted = []
		self.log_error = MagicMock()
		self.get_traceback = lambda: "tb"
		self.utils = SimpleNamespace(now_datetime=lambda: "NOW")

	def get_all(self, doctype, filters=None, fields=None, limit_page_length=None):
		key, value = next(iter(filters.items()))
		return [dict(r) for r in self.db.recipients.values() if r.get(key) == value][:1]

	def get_doc(self, doctype, name):
		return SimpleNamespace(recount=lambda: self.recounted.append(name))


class Base(unittest.TestCase):
	def setUp(self):
		self.db = FakeDB()
		self.frappe = FakeFrappe(self.db)
		patcher = patch.object(bs, "frappe", self.frappe)
		patcher.start()
		self.addCleanup(patcher.stop)

	def row(self, name="R1"):
		return self.db.recipients[name]


class TestApplyStatus(Base):
	def test_fixture_sequence_sent_delivered_read_by_wamid(self):
		wamid = fixture_status("status_sent.json")["id"]
		self.db.add("R1", status="sending", wamid=wamid)
		for fx, expected in (("status_sent.json", "sent"), ("status_delivered.json", "delivered"), ("status_read.json", "read")):
			s = fixture_status(fx)
			self.assertTrue(bs.apply_status(s["id"], s["status"], s["timestamp"], None, None), fx)
			self.assertEqual(self.row()["status"], expected)
		self.assertEqual(self.frappe.recounted, ["BC-1"] * 3)

	def test_never_regresses_and_replay_is_noop(self):
		self.db.add("R1", status="read", wamid="w1")
		self.assertFalse(bs.apply_status("w1", "delivered", 1, None, None))
		self.assertFalse(bs.apply_status("w1", "sent", 1, None, None))
		self.assertFalse(bs.apply_status("w1", "read", 1, None, None))
		self.assertEqual(self.row()["status"], "read")
		self.assertEqual(self.frappe.recounted, [])

	def test_failed_never_overwrites_delivered_or_read(self):
		for st in ("delivered", "read"):
			self.db.add("R1", status=st, wamid="w1")
			self.assertFalse(bs.apply_status("w1", "failed", 1, [{"code": 131026}], None))
			self.assertEqual(self.row()["status"], st)

	def test_out_of_order_read_before_delivered(self):
		self.db.add("R1", status="sent", wamid="w1")
		self.assertTrue(bs.apply_status("w1", "read", 1, None, None))
		self.assertFalse(bs.apply_status("w1", "delivered", 1, None, None))
		self.assertEqual(self.row()["status"], "read")

	def test_failed_stores_code_and_message_from_fixture(self):
		s = fixture_status("status_failed.json")
		self.db.add("R1", status="sent", wamid=s["id"])
		self.assertTrue(bs.apply_status(s["id"], "failed", s["timestamp"], s["errors"], None))
		self.assertEqual(self.row()["status"], "failed")
		self.assertEqual(self.row()["error_code"], 131047)
		self.assertIn("Re-engagement", self.row()["error_message"])
		self.assertFalse(bs.apply_status(s["id"], "failed", s["timestamp"], s["errors"], None))

	def test_failed_131049_and_131050_only_record(self):
		with patch.object(bs, "_pause") as pause:
			for code, title in ((131049, "Healthy ecosystem"), (131050, "User stopped marketing")):
				self.db.add("R1", status="sent", wamid="w1")
				self.assertTrue(bs.apply_status("w1", "failed", 1, [{"code": code, "title": title}], None))
				self.assertEqual(self.row()["error_code"], code)
			pause.assert_not_called()

	def test_failed_135000_pauses_broadcast(self):
		self.db.add("R1", status="sent", wamid="w1")
		runner = MagicMock()
		with patch.dict("sys.modules", {"huf.ai.whatsapp.broadcast_runner": runner}), patch("huf.ai.whatsapp.broadcast_runner", runner, create=True):
			self.assertTrue(bs.apply_status("w1", "failed", 1, [{"code": 135000, "title": "Generic"}], None))
		runner.pause.assert_called_once()
		self.assertEqual(runner.pause.call_args[0][0], "BC-1")

	def test_pause_failure_never_raises(self):
		self.db.add("R1", status="sent", wamid="w1")
		runner = MagicMock()
		runner.pause.side_effect = RuntimeError("boom")
		with patch.dict("sys.modules", {"huf.ai.whatsapp.broadcast_runner": runner}), patch("huf.ai.whatsapp.broadcast_runner", runner, create=True):
			self.assertTrue(bs.apply_status("w1", "failed", 1, [{"code": 135000}], None))
		self.frappe.log_error.assert_called_once()

	def test_opaque_ref_fallback_adopts_wamid(self):
		self.db.add("R1", status="sending", wamid=None)
		self.assertTrue(bs.apply_status("wamid.NEW", "sent", 1, None, "R1"))
		self.assertEqual(self.row()["wamid"], "wamid.NEW")

	def test_unknown_row_resolves_via_status(self):
		self.db.add("R1", status="unknown", wamid="w1")
		self.assertTrue(bs.apply_status("w1", "delivered", 1, None, None))
		self.assertEqual(self.row()["status"], "delivered")

	def test_unmatched_and_unsupported_status(self):
		self.db.add("R1", status="sent", wamid="w1")
		self.assertFalse(bs.apply_status("nope", "delivered", 1, None, None))
		self.assertFalse(bs.apply_status("w1", "bogus", 1, None, None))
		self.assertFalse(bs.apply_status(None, "delivered", 1, None, None))

	def test_skipped_row_untouched(self):
		self.db.add("R1", status="skipped", wamid="w1")
		self.assertFalse(bs.apply_status("w1", "sent", 1, None, None))

	def test_played_counts_as_read(self):
		self.db.add("R1", status="delivered", wamid="w1")
		self.assertTrue(bs.apply_status("w1", "played", 1, None, None))
		self.assertEqual(self.row()["status"], "read")


class TestApplyUserStop(Base):
	def setUp(self):
		super().setUp()
		p = patch("huf.ai.whatsapp.account_events._norm_sender", lambda s: re.sub(r"\D", "", str(s)))
		p.start()
		self.addCleanup(p.stop)

	def test_skips_queued_and_deferred_in_unfinished_broadcasts_of_gateway_only(self):
		self.db.add("A", status="queued")
		self.db.add("B", status="deferred")
		self.db.add("C", status="sent")
		self.db.add("D", broadcast="BC-2", status="queued")
		self.db.add("E", broadcast="BC-3", status="queued")
		self.db.add("F", status="queued", recipient="15559990000")
		self.assertEqual(bs.apply_user_stop(GW, "+1 555 123 4567"), 2)
		self.assertEqual([self.db.recipients[k]["status"] for k in "ABCDEF"], ["skipped", "skipped", "sent", "queued", "queued", "queued"])
		self.assertEqual(self.row("A")["skip_reason"], "opted_out")
		self.assertEqual(self.frappe.recounted, ["BC-1"])

	def test_empty_input_is_noop(self):
		self.assertEqual(bs.apply_user_stop("", "1555"), 0)
		self.assertEqual(bs.apply_user_stop(GW, ""), 0)


class TestHooks(unittest.TestCase):
	def test_webhook_hook_swallows_errors(self):
		from huf.ai import gateway_webhook as gw

		with patch.object(bs, "apply_status", side_effect=RuntimeError("x")), patch.object(gw.frappe, "log_error") as log:
			gw._apply_broadcast_status({"id": "w", "status": "sent"})
		log.assert_called_once()

	def test_webhook_hook_passes_opaque_data(self):
		from huf.ai import gateway_webhook as gw

		with patch.object(bs, "apply_status") as apply:
			gw._apply_broadcast_status({"id": "w", "status": "Failed", "timestamp": "5", "errors": [{"code": 1}], "biz_opaque_callback_data": "R9"})
		apply.assert_called_once_with("w", "failed", "5", [{"code": 1}], "R9")

	def test_user_preferences_stop_calls_hook_and_swallows_errors(self):
		from huf.ai.whatsapp import account_events as ae

		item = {"wa_id": "15551234567", "category": ae.MARKETING, "value": "stop", "timestamp": 5}
		with patch.object(ae, "_insert_consent", return_value=True), patch.object(bs, "apply_user_stop", side_effect=RuntimeError("x")) as stop, patch.object(ae.frappe, "log_error"):
			self.assertEqual(ae.record_user_preferences(GW, [item]), 1)
		stop.assert_called_once_with(GW, "15551234567")

	def test_resume_does_not_skip(self):
		from huf.ai.whatsapp import account_events as ae

		item = {"wa_id": "15551234567", "category": ae.MARKETING, "value": "resume", "timestamp": 5}
		with patch.object(ae, "_insert_consent", return_value=True), patch.object(bs, "apply_user_stop") as stop:
			ae.record_user_preferences(GW, [item])
		stop.assert_not_called()
