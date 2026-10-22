# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-3a ingest guard: field whitelist, echo drop, record-only kinds, reaction short-circuit, ingest order."""

import json
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service
from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CREDS = {
	"phone_number_id": "106540352242922",
	"access_token": "t",
	"webhook_verify_token": "v",
	"app_secret": "s",
}
ORIGINAL = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgUM0E1NTQ2RTE2QjdBOEFBQzAzMjAA"


def parse(name):
	adapter = WhatsAppGatewayAdapter(CREDS)
	body = (FIXTURES / name).read_bytes()
	return adapter.parse_payload(GatewayInboundRequest(body=body, headers={}, method="POST"))


class TestFieldWhitelistAndEcho(unittest.TestCase):
	def test_non_whitelisted_fields_produce_zero_events(self):
		for name in ("standby.json", "other_field.json"):
			parsed = parse(name)
			self.assertEqual(parsed.messages, (), name)
			self.assertEqual(parsed.statuses, (), name)
			self.assertGreaterEqual(parsed.ignored, 1, name)

	def test_echo_shaped_message_under_messages_is_dropped(self):
		parsed = parse("echo.json")
		self.assertEqual(parsed.messages, ())
		self.assertGreaterEqual(parsed.ignored, 1)

	def test_normal_message_still_ingested(self):
		parsed = parse("text_inbound.json")
		self.assertEqual(len(parsed.messages), 1)
		self.assertEqual(parsed.messages[0].kind, "message")


class TestKinds(unittest.TestCase):
	def test_kinds(self):
		for name, kind in (
			("edit.json", "edit"),
			("revoke.json", "revoke"),
			("system.json", "system"),
			("unknown.json", "unknown"),
			("unsupported.json", "unsupported"),
			("reaction.json", "reaction"),
			("image_with_caption.json", "message"),
			("location.json", "message"),
		):
			events = parse(name).messages
			self.assertEqual(len(events), 1, name)
			self.assertEqual(events[0].kind, kind, name)
			if kind != "message":
				self.assertEqual(events[0].raw_payload["kind"], kind, name)

	def test_edit_and_revoke_carry_original_id(self):
		self.assertEqual(parse("edit.json").messages[0].raw_payload["original_message_id"], ORIGINAL)
		self.assertEqual(parse("revoke.json").messages[0].raw_payload["original_message_id"], ORIGINAL)

	def test_event_context_carries_kind(self):
		from huf.ai.gateway_webhook import _event_context

		event = parse("revoke.json").messages[0]
		ctx = _event_context(event)
		self.assertEqual(ctx["kind"], "revoke")
		self.assertEqual(ctx["original_message_id"], ORIGINAL)
		self.assertEqual(_event_context(parse("text_inbound.json").messages[0])["kind"], "message")


def _gateway(**kw):
	values = {"name": "GW", "provider": "WhatsApp", "is_enabled": 1}
	values.update(kw)
	return SimpleNamespace(**values)


class TestIngestOrder(unittest.TestCase):
	def _run(self, context, *, limited="", consent=None, admitted=(True, ""), route_status="Queued"):
		event = MagicMock()
		event.name = "GE-NEW"
		order = MagicMock()
		order.consent.return_value = consent
		order.admission.return_value = admitted
		order.rate.return_value = limited
		order.reply = MagicMock()
		self.event, self.order = event, order

		def get_doc(arg, *a, **k):
			return _gateway() if arg == "Gateway" else event

		def get_value(doctype, filters, fieldname=None, *a, **k):
			return None

		with patch.object(gateway_service, "frappe") as fr, patch.object(
			gateway_service, "_idempotency_key", side_effect=lambda g, e: "orig-key" if e == ORIGINAL else "new-key"
		), patch.object(gateway_service, "_handle_consent_event", order.consent), patch.object(
			gateway_service, "_admission", order.admission
		), patch.object(gateway_service, "_sender_rate_limit_reason", order.rate), patch.object(
			gateway_service, "_send_plain_reply", order.reply
		), patch.object(
			gateway_service, "resolve_gateway_route", return_value={"status": route_status, "target_type": "Agent", "agent": "A"}
		):
			fr.get_doc.side_effect = get_doc
			fr.db.get_value.side_effect = get_value
			self.fr = fr
			return gateway_service.ingest_gateway_event(
				"GW", "wamid.NEW", context, verified_sender=True, raw_payload={"x": 1}
			)

	def test_reaction_short_circuits_before_everything(self):
		result = self._run({"sender_id": "1", "kind": "reaction", "message_text": "[Reaction]"})
		self.assertEqual(result["status"], "Recorded")
		self.order.consent.assert_not_called()
		self.order.admission.assert_not_called()
		self.order.rate.assert_not_called()
		self.fr.enqueue.assert_not_called()

	def test_rate_limit_runs_before_consent(self):
		manager = MagicMock()
		with patch.object(gateway_service, "_sender_rate_limit_reason", manager.rate), patch.object(
			gateway_service, "_handle_consent_event", manager.consent
		), patch.object(gateway_service, "_admission", return_value=(True, "")), patch.object(
			gateway_service, "frappe"
		) as fr, patch.object(
			gateway_service, "resolve_gateway_route", return_value={"status": "Queued", "target_type": "Agent"}
		):
			manager.rate.return_value = ""
			manager.consent.return_value = None
			fr.db.get_value.return_value = None
			fr.get_doc.side_effect = lambda a, *x, **k: _gateway() if a == "Gateway" else MagicMock(name="E")
			gateway_service.ingest_gateway_event("GW", "w1", {"sender_id": "1", "message_text": "STOP"}, verified_sender=True)
		names = [c[0] for c in manager.mock_calls if c[0] in ("rate", "consent")]
		self.assertEqual(names[:2], ["rate", "consent"])

	def test_rate_limited_sender_never_reaches_consent(self):
		result = self._run({"sender_id": "1", "message_text": "STOP"}, limited="sender_rate_limited: x")
		self.assertEqual(result["status"], "Rejected")
		self.order.consent.assert_not_called()
		self.order.admission.assert_not_called()
		self.fr.enqueue.assert_not_called()

	def test_record_only_kinds_never_queue_or_admit(self):
		for kind in ("edit", "revoke", "system", "unknown"):
			result = self._run({"sender_id": "1", "kind": kind, "message_text": "[x]", "original_message_id": ORIGINAL})
			self.assertEqual(result["status"], "Recorded", kind)
			self.order.consent.assert_not_called()
			self.order.admission.assert_not_called()
			self.order.reply.assert_not_called()
			self.fr.enqueue.assert_not_called()

	def test_revoke_neutralises_queued_original_of_same_sender(self):
		original = {"name": "GE-OLD", "status": "Queued", "sender_id": "1", "raw_payload": "{}"}
		self._run_revoke(original, sender="1")
		self.fr.db.set_value.assert_called()
		values = self.fr.db.set_value.call_args.args[2]
		self.assertEqual(values["status"], "Rejected")
		self.assertIn("revoked", values["error_message"])
		self.assertEqual(json.loads(values["raw_payload"])["revoked"], True)

	def test_revoke_from_a_different_sender_is_ignored(self):
		original = {"name": "GE-OLD", "status": "Queued", "sender_id": "2", "raw_payload": "{}"}
		self._run_revoke(original, sender="1")
		self.fr.db.set_value.assert_not_called()

	def test_revoke_of_running_original_marks_but_keeps_status(self):
		original = {"name": "GE-OLD", "status": "Running", "sender_id": "1", "raw_payload": "{}"}
		self._run_revoke(original, sender="1")
		values = self.fr.db.set_value.call_args.args[2]
		self.assertNotIn("status", values)
		self.assertEqual(json.loads(values["raw_payload"])["revoked"], True)

	def test_edit_marks_original_superseded_without_rerun(self):
		original = {"name": "GE-OLD", "status": "Succeeded", "sender_id": "1", "raw_payload": "{}"}
		self._run_revoke(original, sender="1", kind="edit")
		values = self.fr.db.set_value.call_args.args[2]
		self.assertEqual(json.loads(values["raw_payload"])["superseded_by"], "wamid.NEW")
		self.fr.enqueue.assert_not_called()

	def _run_revoke(self, original, *, sender, kind="revoke"):
		event = MagicMock()
		event.name = "GE-NEW"
		with patch.object(gateway_service, "frappe") as fr, patch.object(
			gateway_service, "_idempotency_key", side_effect=lambda g, e: "orig-key" if e == ORIGINAL else "new-key"
		):
			def get_value(doctype, filters, fieldname=None, *a, **k):
				if isinstance(filters, dict) and filters.get("idempotency_key") == "orig-key":
					return original
				return None

			fr.db.get_value.side_effect = get_value
			fr.get_doc.return_value = event
			self.fr = fr
			return gateway_service.ingest_gateway_event(
				"GW",
				"wamid.NEW",
				{"sender_id": sender, "kind": kind, "message_text": "[x]", "original_message_id": ORIGINAL},
				verified_sender=True,
			)

	def test_unsupported_gets_deterministic_reply_without_run(self):
		result = self._run(
			{"sender_id": "1", "kind": "unsupported", "message_text": "[unsupported message]", "provider_error_codes": [131051]}
		)
		self.assertEqual(result["status"], "Recorded")
		self.order.reply.assert_called_once()
		self.assertEqual(self.order.reply.call_args.args[3], gateway_service.UNSUPPORTED_REPLY)
		self.fr.enqueue.assert_not_called()

	def test_unsupported_131060_is_silent(self):
		result = self._run(
			{"sender_id": "1", "kind": "unsupported", "message_text": "x", "provider_error_codes": [131060]}
		)
		self.assertEqual(result["status"], "Recorded")
		self.order.reply.assert_not_called()

	def test_unsupported_from_unadmitted_sender_gets_no_reply(self):
		result = self._run({"sender_id": "1", "kind": "unsupported", "message_text": "x"}, admitted=(False, "no"))
		self.assertEqual(result["status"], "Rejected")
		self.order.reply.assert_not_called()
