# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FX-B: account events apply only to the receiving gateway; consent ordering/dedupe; deferred 503 pass."""

import json
import pathlib
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_webhook
from huf.ai.whatsapp import account_events as ae
from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "whatsapp"
CREDS = {"phone_number_id": "106540352242922", "access_token": "t", "webhook_verify_token": "v", "app_secret": "s"}
REMOVED = {"event": "PARTNER_REMOVED"}
PREFS = [{"wa_id": "16315551181", "category": "marketing_messages", "value": "resume", "timestamp": 1731700000}]


def _ident(phone="106540352242922", waba="W-A"):
	return {"phone_number_id": phone, "waba_id": waba}


def _parse_payload(payload):
	body = json.dumps(payload).encode()
	return WhatsAppGatewayAdapter(CREDS).parse_payload(GatewayInboundRequest(body=body, headers={}, method="POST"))


def _prefs_payload(phone_id):
	payload = json.loads((FIXTURES / "user_preferences_stop.json").read_text())
	payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = phone_id
	return payload


class TestReceivingGatewayOnly(unittest.TestCase):
	def test_account_update_for_another_waba_is_ignored(self):
		with patch.object(ae, "_gateway_identity", return_value=_ident(waba="W-A")), patch.object(ae, "_set_state") as setter:
			out = ae.apply_account_event({"field": "account_update", "waba_id": "W-B", **REMOVED}, "GW-A")
		self.assertEqual(out, [])
		setter.assert_not_called()

	def test_account_update_for_own_waba_updates_only_this_gateway(self):
		with (
			patch.object(ae, "_gateway_identity", return_value=_ident(waba="W-A")),
			patch.object(ae, "_set_state") as setter,
			patch.object(ae, "_audit"),
		):
			out = ae.apply_account_event({"field": "account_update", "waba_id": "W-A", **REMOVED}, "GW-A")
		self.assertEqual(out, ["GW-A"])
		self.assertEqual(setter.call_args.args[:2], ("GW-A", "Disconnected"))

	def test_account_update_with_foreign_phone_id_ignored(self):
		with patch.object(ae, "_gateway_identity", return_value=_ident()), patch.object(ae, "_set_state") as setter:
			out = ae.apply_account_event({"field": "account_update", "waba_id": "W-A", "phone_id": "999", **REMOVED}, "GW-A")
		self.assertEqual(out, [])
		setter.assert_not_called()

	def test_gateway_without_known_waba_ignores_account_update(self):
		with patch.object(ae, "_gateway_identity", return_value=_ident(waba="")), patch.object(ae, "_set_state") as setter:
			out = ae.apply_account_event({"field": "account_update", "waba_id": "W-A", **REMOVED}, "GW-A")
		self.assertEqual(out, [])
		setter.assert_not_called()

	def test_user_preferences_requires_own_phone_id(self):
		event = {"field": "user_preferences", "waba_id": "W-A", "user_preferences": PREFS}
		with patch.object(ae, "_gateway_identity", return_value=_ident()), patch.object(ae, "record_user_preferences") as rec:
			self.assertEqual(ae.apply_account_event({**event, "phone_id": "999"}, "GW-A"), [])
			self.assertEqual(ae.apply_account_event({**event, "phone_id": ""}, "GW-A"), [])
			rec.assert_not_called()
			self.assertEqual(ae.apply_account_event({**event, "phone_id": "106540352242922"}, "GW-A"), ["GW-A"])
			rec.assert_called_once_with("GW-A", PREFS)

	def test_apply_account_events_passes_receiving_gateway(self):
		with patch.object(ae, "apply_account_event", return_value=["GW-A"]) as one:
			self.assertEqual(ae.apply_account_events([{"field": "account_update"}], "GW-A"), 1)
		self.assertEqual(one.call_args.args[1], "GW-A")


class TestOwnWaba(unittest.TestCase):
	def test_direct_gateway_uses_waba_stored_on_gateway(self):
		row = {"phone_number_id": "1", "whatsapp_account": "", "whatsapp_business_account_id": " W-D "}
		with patch.object(ae.frappe.db, "get_value", return_value=row):
			self.assertEqual(ae._gateway_identity("GW-D"), {"phone_number_id": "1", "waba_id": "W-D"})

	def test_linked_account_business_id_wins(self):
		row = {"phone_number_id": "1", "whatsapp_account": "ACC", "whatsapp_business_account_id": "W-D"}
		with (
			patch.object(ae.frappe.db, "get_value", return_value=row),
			patch("huf.ai.gateway_adapters.whatsapp_bridge.account_business_id", return_value="W-ACC"),
		):
			self.assertEqual(ae._gateway_identity("GW")["waba_id"], "W-ACC")

	def test_direct_gateway_can_be_disconnected(self):
		with (
			patch.object(ae, "_gateway_identity", return_value=_ident(waba="W-D")),
			patch.object(ae, "_set_state") as setter,
			patch.object(ae, "_audit"),
		):
			ae.apply_account_event({"field": "account_update", "waba_id": "W-D", **REMOVED}, "GW-D")
		setter.assert_called_once()

	def test_gateway_json_declares_waba_field(self):
		meta = json.loads((pathlib.Path(__file__).parents[2] / "huf/doctype/gateway/gateway.json").read_text())
		self.assertIn("whatsapp_business_account_id", meta["field_order"])
		self.assertIn("whatsapp_business_account_id", [f["fieldname"] for f in meta["fields"]])


class TestAdapterParse(unittest.TestCase):
	def test_user_preferences_for_foreign_phone_id_not_collected(self):
		parsed = _parse_payload(_prefs_payload("999"))
		self.assertEqual(parsed.account_events, ())
		self.assertIn("999", parsed.unknown_phone_ids)

	def test_user_preferences_without_phone_id_not_collected(self):
		self.assertEqual(_parse_payload(_prefs_payload("")).account_events, ())

	def test_user_preferences_for_own_phone_id_collected(self):
		self.assertEqual(len(_parse_payload(_prefs_payload("106540352242922")).account_events), 1)

	def test_account_update_with_foreign_phone_id_not_collected(self):
		payload = json.loads((FIXTURES / "account_update_partner_removed.json").read_text())
		payload["entry"][0]["changes"][0]["value"]["metadata"] = {"phone_number_id": "999"}
		self.assertEqual(_parse_payload(payload).account_events, ())


class TestConsentOrdering(unittest.TestCase):
	def test_meta_timestamp_stored_and_dedupe_checked(self):
		with patch.object(ae.frappe.db, "exists", return_value=False) as exists, patch.object(ae.frappe, "get_doc") as get_doc, patch.object(ae.frappe.utils, "now_datetime", return_value=datetime(2026, 1, 1)):
			ae.record_user_preferences("GW", PREFS)
		doc = get_doc.call_args.args[0]
		self.assertEqual(doc["meta_timestamp"], 1731700000)
		flt = exists.call_args.args[1]
		self.assertEqual(
			(flt["gateway"], flt["sender_id"], flt["category"], flt["value"], flt["meta_timestamp"]),
			("GW", "16315551181", "marketing_messages", "resume", 1731700000),
		)

	def test_duplicate_delivery_inserts_nothing(self):
		with patch.object(ae.frappe.db, "exists", return_value=True), patch.object(ae.frappe, "get_doc") as get_doc, patch.object(ae.frappe.utils, "now_datetime", return_value=datetime(2026, 1, 1)):
			self.assertEqual(ae.record_user_preferences("GW", PREFS), 0)
		get_doc.assert_not_called()

	def test_latest_consent_orders_by_meta_timestamp_first(self):
		with patch.object(ae.frappe, "get_all", return_value=[{"value": "stop"}]) as get_all:
			ae._latest_consent("GW", "1", "marketing_messages")
		self.assertTrue(get_all.call_args.kwargs["order_by"].startswith("meta_timestamp desc"))

	def test_consent_doctype_declares_meta_timestamp(self):
		meta = json.loads((pathlib.Path(__file__).parents[2] / "huf/doctype/gateway_consent/gateway_consent.json").read_text())
		self.assertIn("meta_timestamp", meta["field_order"])


def _evt(i):
	return SimpleNamespace(
		provider_event_id=f"id{i}", sender_id="1", conversation_id="1", thread_id="", message_text="t",
		is_room=0, mentioned=0, kind="message", raw_payload={"message": {"id": f"id{i}"}},
	)


class _Resp:
	http_status_code = 200


def _run(n, duplicates=0, deferrals_seen=0):
	cap = gateway_webhook.MAX_INGEST_PER_REQUEST
	parsed = SimpleNamespace(
		messages=tuple(_evt(i) for i in range(n)), statuses=({"id": "w", "status": "failed"},), template_updates=(),
		ignored=0, unknown_phone_ids=(), calls=(), account_events=({"field": "account_update"},),
	)
	adapter = MagicMock()
	adapter.parse_payload.return_value = parsed
	gateway = SimpleNamespace(name="GW", whatsapp_account="")
	seen = {"n": 0}

	def ingest(*_a, **_k):
		seen["n"] += 1
		return {"event_name": "E", "status": "Rejected", "duplicate": seen["n"] <= duplicates}

	patches = {
		name: patch.object(gateway_webhook, name)
		for name in ("_ingest_rate_gate", "touch_last_event", "_warn", "_record_unknown_phone_ids", "_set_gateway_error",
		             "_savepoint", "_rollback_to_savepoint", "_update_reply_status", "_record_failed_status", "_handle_calls")
	}
	req = GatewayInboundRequest(body=b"{}", headers={}, query={}, method="POST")
	with (
		patch.object(gateway_webhook.frappe.local, "response", _Resp(), create=True),
		patch.object(gateway_webhook.frappe.local, "response_headers", {}, create=True),
		patch("huf.ai.gateway_service.ingest_gateway_event", side_effect=ingest),
		patch("huf.ai.gateway_service.store_ingest_dead_letter", return_value="DL") as dead,
		patch.object(gateway_webhook, "_apply_account_events", return_value=1) as acct,
		patch.object(gateway_webhook, "_deferral_count", return_value=deferrals_seen),
		patch.object(gateway_webhook, "_bump_deferral") as bump,
		ExitStack() as stack,
	):
		mocks = {k: stack.enter_context(p) for k, p in patches.items()}
		mocks["_handle_calls"].return_value = []
		result = gateway_webhook._handle_batched_payload(gateway, adapter, req)
		status = gateway_webhook.frappe.local.response.http_status_code
	return result, mocks, acct, dead, bump, status, cap


from contextlib import ExitStack  # noqa: E402


class TestDeferredPass(unittest.TestCase):
	def test_deferred_pass_skips_statuses_and_account_events(self):
		cap = gateway_webhook.MAX_INGEST_PER_REQUEST
		result, mocks, acct, _d, bump, status, _ = _run(cap + 3)
		self.assertEqual(status, 503)
		self.assertEqual(result["deferred"], 3)
		mocks["_update_reply_status"].assert_not_called()
		mocks["_record_failed_status"].assert_not_called()
		acct.assert_not_called()
		bump.assert_called_once()

	def test_final_pass_applies_statuses_and_account_events_once(self):
		result, mocks, acct, _d, bump, status, _ = _run(5)
		self.assertEqual(status, 200)
		mocks["_update_reply_status"].assert_called_once()
		acct.assert_called_once()
		bump.assert_not_called()

	def test_redelivery_progresses_past_already_ingested_duplicates(self):
		cap = gateway_webhook.MAX_INGEST_PER_REQUEST
		result, _m, _a, _d, _b, status, _ = _run(cap + 3, duplicates=cap)
		self.assertEqual(result["deferred"], 0)
		self.assertEqual(status, 200)

	def test_deferrals_are_bounded_then_remaining_dead_lettered_and_acked(self):
		cap = gateway_webhook.MAX_INGEST_PER_REQUEST
		result, _m, _a, dead, _b, status, _ = _run(cap + 3, deferrals_seen=gateway_webhook.MAX_DEFERRALS_PER_PAYLOAD)
		self.assertEqual(status, 200)
		self.assertEqual(result["deferred"], 0)
		self.assertEqual(dead.call_count, 3)
