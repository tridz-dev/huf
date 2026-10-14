"""Signed WhatsApp ingress: batched fan-out, status acks, rate limit, 403 verify (T3)."""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai import gateway_webhook
from huf.ai.gateway_adapters import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

BRIDGE = "huf.ai.gateway_adapters.whatsapp_bridge"
CREDS = {
	"phone_number_id": "phone-123",
	"access_token": "access-token",
	"webhook_verify_token": "verify-value",
	"app_secret": "s3cret",
}


def _msg(wamid, text="hello", sender="1234567890", **extra):
	m = {"from": sender, "id": wamid, "type": "text", "text": {"body": text}}
	m.update(extra)
	return m


def _payload(messages=None, statuses=None):
	value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "phone-123"}}
	if messages is not None:
		value["messages"] = messages
		value["contacts"] = [{"wa_id": "1234567890", "profile": {"name": "Ann"}}]
	if statuses is not None:
		value["statuses"] = statuses
	return {"entry": [{"id": "biz", "changes": [{"field": "messages", "value": value}]}]}


class TestWhatsAppIngress(unittest.TestCase):
	def _call(self, payload=None, *, secret="s3cret", method="POST", query=None, body=None, ingest=None, record=None, forward=None, account_matches=True, gateway_rows=(), gateway_account="Acct", waba_accounts=None, bridge_available=True):
		adapter = WhatsAppGatewayAdapter(CREDS, gateway_context={"gateway_name": "WA"})
		raw = body if body is not None else json.dumps(payload or {}).encode()
		sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
		request = GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query=query or {}, method=method)
		response = SimpleNamespace()
		self.mock_frappe = MagicMock()
		self.mock_frappe.PermissionError = frappe.PermissionError
		self.mock_frappe.QueryDeadlockError = frappe.QueryDeadlockError
		self.mock_frappe.request = SimpleNamespace(args={"gateway_name": "WA"})
		self.mock_frappe.local = SimpleNamespace(response=response)
		self.mock_frappe.get_doc.return_value = SimpleNamespace(
			name="WA", provider="WhatsApp", is_enabled=1, whatsapp_account=gateway_account
		)
		self.mock_frappe.get_all.return_value = list(gateway_rows)
		self.gate = MagicMock()
		self.ingest = ingest or MagicMock(
			side_effect=lambda gw, eid, ctx, **kw: {"event_name": f"GE-{eid}", "status": "Queued"}
		)
		self.forward = forward or MagicMock(return_value=True)
		self.record = record or MagicMock(return_value="WM-1")
		with patch("huf.ai.gateway_webhook.frappe", self.mock_frappe), patch(
			"huf.ai.gateway_webhook.get_gateway_adapter", return_value=adapter
		), patch("huf.ai.gateway_webhook._inbound_request", return_value=request), patch(
			"huf.ai.gateway_webhook._ingest_rate_gate", self.gate
		), patch("huf.ai.gateway_service.ingest_gateway_event", self.ingest), patch(
			f"{BRIDGE}.forward_status", self.forward
		), patch(f"{BRIDGE}.record_incoming", self.record), patch(
			f"{BRIDGE}.account_matches_phone_id", return_value=account_matches
		) as self.matches, patch(f"{BRIDGE}.is_available", return_value=bridge_available), patch(
			f"{BRIDGE}.accounts_for_waba",
			side_effect=lambda waba: list((waba_accounts if waba_accounts is not None else {"waba-1": ["Acct"]}).get(waba, [])),
		), patch(f"{BRIDGE}.record_template_webhook") as self.record_template, patch(
			f"{BRIDGE}.resolve_account", side_effect=AssertionError("webhook paths must not resolve a default account")
		), patch("huf.ai.gateway_webhook._text_response") as self.text:
			self.result = gateway_webhook.handle_gateway_webhook()
		self.response = response
		return self.result

	def test_batch_of_two_messages_and_one_status_fans_out(self):
		status = {"id": "wamid.out", "status": "delivered", "recipient_id": "1234567890"}
		result = self._call(_payload([_msg("wamid.1"), _msg("wamid.2", "second")], statuses=[status]))
		self.assertTrue(result["success"])
		self.assertEqual(self.ingest.call_count, 2)
		self.assertEqual(self.forward.call_count, 1)
		self.assertEqual(self.record.call_count, 2)
		self.assertEqual((result["ingested"], result["statuses"], result["forwarded"]), (2, 1, 1))
		first = self.ingest.call_args_list[0]
		self.assertEqual(first.args[:2], ("WA", "wamid.1"))
		self.assertTrue(first.kwargs["verified_sender"])
		self.gate.assert_called_once()

	def test_status_only_payload_succeeds_without_ingest_or_rate_limit(self):
		result = self._call(_payload(statuses=[{"id": "wamid.out", "status": "read"}]))
		self.assertTrue(result["success"])
		self.ingest.assert_not_called()
		self.gate.assert_not_called()
		self.assertEqual(self.forward.call_count, 1)

	def test_unknown_benign_payload_is_acked(self):
		result = self._call({"entry": [{"changes": [{"field": "account_update", "value": {"event": "X"}}]}]})
		self.assertTrue(result["success"])
		self.assertEqual(result["ignored"], 1)
		self.ingest.assert_not_called()
		self.gate.assert_not_called()

	def test_duplicate_wamid_is_counted_and_not_mirrored(self):
		dup = MagicMock(return_value={"duplicate": True, "event_name": "GE-1"})
		result = self._call(_payload([_msg("wamid.1")]), ingest=dup)
		self.assertEqual((result["ingested"], result["duplicates"]), (0, 1))
		self.record.assert_not_called()

	def test_mirror_failure_never_breaks_the_ack(self):
		result = self._call(_payload([_msg("wamid.1")]), record=MagicMock(side_effect=RuntimeError("boom")))
		self.assertTrue(result["success"])
		self.assertEqual(result["ingested"], 1)

	def test_forward_failure_never_breaks_the_ack(self):
		result = self._call(
			_payload(statuses=[{"id": "w", "status": "sent"}]), forward=MagicMock(side_effect=RuntimeError("x"))
		)
		self.assertTrue(result["success"])
		self.assertEqual(result["forwarded"], 0)

	def test_forged_signature_is_401_and_counts_against_budget(self):
		result = self._call(_payload([_msg("wamid.1")]), secret="wrong")
		self.assertEqual(result, {"success": False, "error": "Provider verification failed"})
		self.assertEqual(self.response.http_status_code, 401)
		self.ingest.assert_not_called()
		self.gate.assert_called_once()

	def test_verify_failure_on_get_is_403_not_500(self):
		query = {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "abc"}
		result = self._call(method="GET", query=query, body=b"")
		self.assertEqual(result["success"], False)
		self.assertEqual(self.response.http_status_code, 403)
		self.text.assert_not_called()

	def test_verify_success_on_get_returns_challenge(self):
		query = {"hub.mode": "subscribe", "hub.verify_token": "verify-value", "hub.challenge": "abc"}
		self.assertIsNone(self._call(method="GET", query=query, body=b""))
		self.text.assert_called_once_with("abc")

	def test_gateway_without_account_never_mirrors_and_never_guesses_a_default(self):
		result = self._call(_payload([_msg("wamid.1")]), gateway_account="")
		self.assertEqual(result["ingested"], 1)
		self.record.assert_not_called()
		self.matches.assert_not_called()
		self.assertIn("no WhatsApp Account linked", str(self.mock_frappe.logger.return_value.warning.call_args))

	def test_mirror_skipped_when_account_phone_differs_from_payload(self):
		result = self._call(_payload([_msg("wamid.1")]), account_matches=False)
		self.assertEqual(result["ingested"], 1)
		self.record.assert_not_called()
		self.matches.assert_called_once_with("Acct", "phone-123")

	def test_deterministic_ingest_error_is_logged_and_acked(self):
		boom = MagicMock(side_effect=[frappe.ValidationError("bad"), {"event_name": "GE-2", "status": "Queued"}])
		result = self._call(_payload([_msg("wamid.1"), _msg("wamid.2")]), ingest=boom)
		self.assertTrue(result["success"])
		self.assertEqual((result["ingested"], result["failed"]), (1, 1))
		self.mock_frappe.log_error.assert_called()

	def test_transient_ingest_errors_are_reraised_after_fanout(self):
		import pymysql

		for exc in (frappe.QueryDeadlockError("d"), frappe.QueryTimeoutError("t"), pymysql.OperationalError(2013, "lost"), ConnectionError("c")):
			ingest = MagicMock(side_effect=[exc, {"event_name": "GE-2", "status": "Queued"}])
			with self.assertRaises(type(exc)):
				self._call(_payload([_msg("wamid.1"), _msg("wamid.2")]), ingest=ingest)
			self.assertEqual(ingest.call_count, 2)  # the rest of the batch still ingested

	def _failed_status(self):
		return {
			"id": "wamid.out",
			"status": "failed",
			"recipient_id": "919876543210",
			"errors": [{"code": 131047, "title": "Re-engagement message Bearer abcdefghijkl"}],
		}

	def test_failed_status_sets_gateway_last_error_even_when_nothing_is_forwarded(self):
		result = self._call(_payload(statuses=[self._failed_status()]), forward=MagicMock(return_value=False))
		self.assertTrue(result["success"])
		self.assertEqual(result["forwarded"], 0)
		set_value = self.mock_frappe.db.set_value
		set_value.assert_called_once()
		args = set_value.call_args
		self.assertEqual(args.args[:2], ("Gateway", "WA"))
		values = args.args[2]
		self.assertIn("131047", values["last_error"])
		self.assertIn("3210", values["last_error"])
		self.assertNotIn("919876543210", values["last_error"])
		self.assertNotIn("abcdefghijkl", values["last_error"])  # redacted
		self.assertIn("last_event_at", values)
		self.mock_frappe.log_error.assert_called_once()

	def test_failed_status_recording_never_breaks_the_ack(self):
		with patch("huf.ai.gateway_webhook._set_gateway_error", side_effect=RuntimeError("db")):
			result = self._call(_payload(statuses=[self._failed_status()]))
		self.assertTrue(result["success"])

	def test_non_failed_status_leaves_last_error_alone(self):
		self._call(_payload(statuses=[{"id": "w", "status": "delivered"}]))
		self.mock_frappe.db.set_value.assert_not_called()

	def test_unknown_phone_number_id_is_recorded_not_silently_dropped(self):
		payload = _payload([_msg("wamid.1")])
		payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "other-999"
		result = self._call(payload)
		self.assertTrue(result["success"])  # still acked
		self.ingest.assert_not_called()
		values = self.mock_frappe.db.set_value.call_args.args[2]
		self.assertIn("payload for phone number id other-999 ignored; one Gateway per Meta app/number", values["last_error"])

	@staticmethod
	def _template_payload(event, name="reopen", waba="waba-1"):
		update = {"event": event, "message_template_name": name, "reason": "INVALID_FORMAT"}
		return {"entry": [{"id": waba, "changes": [{"field": "message_template_status_update", "value": update}]}]}

	def test_template_rejection_marks_gateways_of_the_wabas_account_using_it_as_fallback(self):
		rows = [
			{"name": "WA", "whatsapp_account": "Acct"},
			{"name": "WA2", "whatsapp_account": "Acct"},
			{"name": "OTHER", "whatsapp_account": "Elsewhere"},  # same fallback name, different account: untouched
		]
		for state in ("REJECTED", "PAUSED", "DISABLED"):
			result = self._call(self._template_payload(state), gateway_rows=rows)
			self.assertTrue(result["success"])
			self.assertEqual(
				self.mock_frappe.get_all.call_args.kwargs["filters"], {"provider": "WhatsApp", "fallback_template": "reopen"}
			)
			calls = self.mock_frappe.db.set_value.call_args_list
			self.assertEqual([c.args[1] for c in calls], ["WA", "WA2"])
			self.assertIn(f"reopen is {state}", calls[0].args[2]["last_error"])
			self.record_template.assert_called_once()
			self.assertEqual(self.record_template.call_args.args[1], "Acct")

	def test_template_update_routes_by_waba_id_not_by_receiving_gateway(self):
		result = self._call(
			self._template_payload("REJECTED", waba="waba-Y"),
			gateway_rows=[{"name": "WA", "whatsapp_account": "Acct"}],
			waba_accounts={"waba-Y": ["AcctY"], "waba-1": ["Acct"]},
		)
		self.assertEqual(self.record_template.call_args.args[1], "AcctY")
		self.mock_frappe.db.set_value.assert_not_called()  # WA is linked to Acct, not to the WABA's account
		self.assertEqual(result["forwarded"], 1)

	def test_template_update_for_unknown_waba_is_ignored_with_warning(self):
		result = self._call(
			self._template_payload("REJECTED", waba="waba-nobody"), gateway_rows=[{"name": "WA", "whatsapp_account": "Acct"}]
		)
		self.assertTrue(result["success"])
		self.record_template.assert_not_called()
		self.mock_frappe.db.set_value.assert_not_called()
		self.assertEqual(result["forwarded"], 0)  # not forwarded to frappe_whatsapp either
		self.assertIn("waba-nobody", str(self.mock_frappe.logger.return_value.warning.call_args))

	def test_template_update_without_bridge_is_recorded_unscoped_and_flags_receiving_gateway_only(self):
		self._call(
			self._template_payload("PAUSED"),
			gateway_rows=[{"name": "WA", "whatsapp_account": ""}, {"name": "WA2", "whatsapp_account": ""}],
			gateway_account="",
			bridge_available=False,
		)
		self.assertIsNone(self.record_template.call_args.args[1])
		self.assertEqual([c.args[1] for c in self.mock_frappe.db.set_value.call_args_list], ["WA"])

	def test_template_approval_or_unused_template_changes_nothing(self):
		self._call(self._template_payload("APPROVED"), gateway_rows=[{"name": "WA", "whatsapp_account": "Acct"}])
		self.mock_frappe.db.set_value.assert_not_called()
		self._call(self._template_payload("REJECTED", "other"), gateway_rows=[])  # no gateway uses it
		self.mock_frappe.db.set_value.assert_not_called()

	def test_template_quality_and_category_updates_surface_on_fallback_gateways(self):
		rows = [{"name": "WA", "whatsapp_account": "Acct"}]

		def payload(field, value):
			return {
				"entry": [
					{"id": "waba-1", "changes": [{"field": field, "value": {"message_template_name": "reopen", **value}}]}
				]
			}

		self._call(
			payload("message_template_quality_update", {"previous_quality_score": "GREEN", "new_quality_score": "RED"}),
			gateway_rows=rows,
		)
		self.assertIn("reopen quality dropped to RED (was GREEN)", self.mock_frappe.db.set_value.call_args.args[2]["last_error"])
		self.mock_frappe.db.set_value.reset_mock()
		self._call(
			payload("template_category_update", {"previous_category": "UTILITY", "new_category": "MARKETING"}),
			gateway_rows=rows,
		)
		self.assertIn("category changed to MARKETING (was UTILITY)", self.mock_frappe.db.set_value.call_args.args[2]["last_error"])
		self.mock_frappe.db.set_value.reset_mock()
		self._call(
			payload("message_template_quality_update", {"previous_quality_score": "RED", "new_quality_score": "GREEN"}),
			gateway_rows=rows,
		)
		self.mock_frappe.db.set_value.assert_not_called()

	def test_malformed_signed_json_is_400(self):
		result = self._call(body=b"not json")
		self.assertFalse(result["success"])
		self.assertEqual(self.response.http_status_code, 400)

	def test_quoted_reply_keeps_phone_as_conversation(self):
		self._call(_payload([_msg("wamid.q", "re", context={"id": "wamid.prev"})]))
		ctx = self.ingest.call_args.args[2]
		self.assertEqual(ctx["conversation_id"], "1234567890")
		self.assertEqual(ctx["sender_id"], "1234567890")
		self.assertFalse(ctx["thread_id"])
		self.assertEqual(self.ingest.call_args.kwargs["raw_payload"]["quoted_message_id"], "wamid.prev")


if __name__ == "__main__":
	unittest.main()
