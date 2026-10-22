# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-11: account_update fail-fast, connection state, send refusal, user_preferences consent."""

import json
import pathlib
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.whatsapp import account_events as ae
from huf.ai.whatsapp import health as wh
from huf.ai.gateway_adapters import whatsapp_errors as we
from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "whatsapp"
CREDS = {"phone_number_id": "106540352242922", "access_token": "t", "webhook_verify_token": "v", "app_secret": "s"}


def load(name):
	return json.loads((FIXTURES / name).read_text())


def parse(name):
	body = (FIXTURES / name).read_bytes()
	return WhatsAppGatewayAdapter(CREDS).parse_payload(GatewayInboundRequest(body=body, headers={}, method="POST"))


def change_value(name):
	return load(name)["entry"][0]["changes"][0]["value"]


class TestClassify(unittest.TestCase):
	def test_partner_removed_disconnects_with_plain_reason(self):
		r = ae.classify_account_update(change_value("account_update_partner_removed.json"))
		self.assertEqual(r["state"], "Disconnected")
		self.assertIn("disconnected", r["reason"].lower())

	def test_offboarded_deleted_and_ban_disconnect(self):
		for v in (
			{"event": "ACCOUNT_OFFBOARDED"},
			{"event": "ACCOUNT_DELETED"},
			{"event": "DISABLED_UPDATE", "ban_info": {"waba_ban_state": "DISABLE"}},
		):
			self.assertEqual(ae.classify_account_update(v)["state"], "Disconnected", v)

	def test_restriction_violation_degrade(self):
		for v in (
			change_value("account_update_restriction.json"),
			{"event": "ACCOUNT_VIOLATION"},
			{"event": "DISABLED_UPDATE", "ban_info": {"waba_ban_state": "SCHEDULE_FOR_DISABLE"}},
		):
			self.assertEqual(ae.classify_account_update(v)["state"], "Degraded", v)

	def test_reconnect_and_reinstate_connect(self):
		for v in (change_value("account_update_reconnected.json"), {"event": "DISABLED_UPDATE", "ban_info": {"waba_ban_state": "REINSTATE"}}):
			self.assertEqual(ae.classify_account_update(v)["state"], "Connected", v)

	def test_unknown_or_neutral_events_do_not_change_state(self):
		for v in ({"event": "PARTNER_ADDED"}, {"event": "X"}, {}, "junk"):
			self.assertIsNone(ae.classify_account_update(v), v)


class TestAdapterRouting(unittest.TestCase):
	def test_account_update_is_collected_by_waba_id_before_phone_gate(self):
		parsed = parse("account_update_partner_removed.json")
		self.assertEqual(parsed.messages, ())
		self.assertEqual(len(parsed.account_events), 1)
		ev = parsed.account_events[0]
		self.assertEqual((ev["field"], ev["waba_id"]), ("account_update", "102290129340398"))
		self.assertEqual(parsed.ignored, 0)

	def test_neutral_account_update_still_ignored(self):
		parsed = parse("account_update.json")  # PARTNER_ADDED
		self.assertEqual(parsed.account_events, ())
		self.assertEqual(parsed.ignored, 1)

	def test_user_preferences_collected(self):
		parsed = parse("user_preferences_stop.json")
		self.assertEqual(len(parsed.account_events), 1)
		self.assertEqual(parsed.account_events[0]["field"], "user_preferences")


class TestApply(unittest.TestCase):
	def test_sets_state_on_receiving_gateway_and_audits(self):
		with (
			patch.object(ae, "_gateway_identity", return_value={"phone_number_id": "p", "waba_id": "W1"}),
			patch.object(ae, "_set_state") as setter,
			patch.object(ae, "_audit") as audit,
		):
			out = ae.apply_account_event({"field": "account_update", "waba_id": "W1", **change_value("account_update_partner_removed.json")}, "GW-1")
		self.assertEqual(out, ["GW-1"])
		self.assertEqual(setter.call_args.args[:2], ("GW-1", "Disconnected"))
		audit.assert_called_once()

	def test_non_matching_waba_changes_nothing(self):
		with patch.object(ae, "_gateway_identity", return_value={"phone_number_id": "p", "waba_id": "W1"}), patch.object(ae, "_set_state") as setter:
			self.assertEqual(ae.apply_account_event({"field": "account_update", "waba_id": "nope", "event": "ACCOUNT_OFFBOARDED"}, "GW-1"), [])
		setter.assert_not_called()


class TestSendRefusal(unittest.TestCase):
	def test_disconnected_refuses_with_structured_error(self):
		with patch.object(ae, "_state_for_phone_id", return_value=("Disconnected", "Account disconnected.")):
			r = ae.send_refusal("106540352242922")
		self.assertEqual(r["error"], "gateway_disconnected")
		self.assertFalse(r["success"])

	def test_degraded_connected_and_unknown_allow(self):
		for st in ("Degraded", "Connected", "", None):
			with patch.object(ae, "_state_for_phone_id", return_value=(st, "")):
				self.assertIsNone(ae.send_refusal("1"), st)

	def test_never_raises(self):
		with patch.object(ae, "_state_for_phone_id", side_effect=RuntimeError("db")):
			self.assertIsNone(ae.send_refusal("1"))


class TestHealth(unittest.TestCase):
	def base(self, **over):
		f = {
			"enabled": True, "has_integration": True, "access_token_present": True, "phone_number_id_present": True,
			"verify_token_present": True, "app_secret_present": True, "app_id_present": True,
			"account_phone_mismatch": False, "last_event_at": wh.frappe.utils.now_datetime() if hasattr(wh.frappe, "utils") else None,
			"last_error": "", "events_ever": 5, "replied_ever": True,
			"events_24h": {"received": 1, "failed": 0, "unrouted": 0, "rejected": 0},
		}
		f.update(over)
		return f

	def test_disconnected_is_blocked_not_healthy(self):
		r = wh.evaluate(self.base(connection_state="Disconnected", connection_reason="Partner removed"))
		self.assertNotEqual(r["health"], "healthy")
		self.assertEqual(r["health"], "blocked")
		self.assertIn("gateway_disconnected", {x["code"] for x in r["reasons"]})

	def test_degraded_warns(self):
		r = wh.evaluate(self.base(connection_state="Degraded", connection_reason="Restricted"))
		self.assertEqual(r["health"], "degraded")

	def test_connected_stays_healthy(self):
		self.assertEqual(wh.evaluate(self.base(connection_state="Connected"))["health"], "healthy")


class TestErrorCodes(unittest.TestCase):
	def test_131060_and_2593109_informational(self):
		for code in (131060, 2593109):
			c = we.classify({"error": {"code": code, "message": "x"}})
			self.assertEqual(c["kind"], "informational", code)
			self.assertTrue(we.is_informational(c))

	def test_190_still_auth(self):
		c = we.classify({"error": {"code": 190, "message": "x"}})
		self.assertEqual(c["kind"], "auth")
		self.assertFalse(we.is_informational(c))


class TestUserPreferences(unittest.TestCase):
	ITEM = {"wa_id": "16315551181", "category": "marketing_messages", "value": "stop", "detail": "d"}

	def test_stop_appends_row_and_blocks_marketing(self):
		with patch.object(ae, "_insert_consent") as ins:
			n = ae.record_user_preferences("GW", [self.ITEM])
		self.assertEqual(n, 1)
		self.assertEqual(ins.call_args.args[:4], ("GW", "16315551181", "marketing_messages", "stop"))

	def test_user_id_and_wa_id_both_recorded(self):
		with patch.object(ae, "_insert_consent") as ins:
			ae.record_user_preferences("GW", [{**self.ITEM, "user_id": "US.1"}])
		self.assertEqual(ins.call_count, 2)

	def test_other_category_or_value_ignored(self):
		with patch.object(ae, "_insert_consent") as ins:
			ae.record_user_preferences("GW", [{**self.ITEM, "category": "other"}, {**self.ITEM, "value": "maybe"}, "junk", {"value": "stop", "category": "marketing_messages"}])
		ins.assert_not_called()

	def test_is_marketing_allowed_latest_row_wins(self):
		with patch.object(ae, "_latest_consent", return_value="stop"):
			self.assertFalse(ae.is_marketing_allowed("GW", "+1 631 555 1181"))
		with patch.object(ae, "_latest_consent", return_value="resume"):
			self.assertTrue(ae.is_marketing_allowed("GW", "16315551181"))
		with patch.object(ae, "_latest_consent", return_value=None):
			self.assertTrue(ae.is_marketing_allowed("GW", "16315551181"))

	def test_is_marketing_allowed_normalises_sender(self):
		with patch.object(ae, "_latest_consent", return_value=None) as latest:
			ae.is_marketing_allowed("GW", "+1 631 555 1181")
		self.assertEqual(latest.call_args.args[:2], ("GW", "16315551181"))
