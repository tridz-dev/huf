# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Contract tests for the WhatsApp Cloud API adapter, driven by recorded webhook fixtures.

Each fixture under ``fixtures/`` is a realistic Meta webhook body. Bodies are
signed with a test app secret so ``verify_inbound`` and ``parse_payload`` run exactly
as they do for a live delivery.
"""

import hashlib
import hmac
import json
import pathlib
import unittest

from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp_bridge import message_time
from huf.ai.gateway_adapters.whatsapp_inbound import render_message_text
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"

TEST_APP_SECRET = "test-app-secret-not-real"
PHONE_NUMBER_ID = "106540352242922"
WRONG_PHONE_NUMBER_ID = "999999999999999"
SENDER_DIGITS = "919876543210"

WAMID = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgUM0E1NTQ2RTE2QjdBOEFBQzAzMTMA"
WAMID2 = "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgUM0E1NTQ2RTE2QjdBOEFBQzAzMjAA"

CREDENTIALS = {
	"phone_number_id": PHONE_NUMBER_ID,
	"access_token": "test-access-token",
	"webhook_verify_token": "test-verify-token",
	"app_secret": TEST_APP_SECRET,
}


def load_body(name):
	"""Return the exact bytes Meta would deliver for a fixture (raw bytes for the malformed case)."""
	path = FIXTURE_DIR / name
	if name == "malformed_json.json":
		return json.loads(path.read_text(encoding="utf-8"))["raw_body"].encode("utf-8")
	return path.read_bytes()


def sign(body, secret=TEST_APP_SECRET):
	return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def make_request(body, secret=TEST_APP_SECRET, signature=None):
	headers = {"content-type": "application/json"}
	if signature is None and secret is not None:
		signature = sign(body, secret)
	if signature is not None:
		headers["x-hub-signature-256"] = signature
	return GatewayInboundRequest(body=body, headers=headers, method="POST")


def signed_request(name):
	return make_request(load_body(name))


class WhatsAppContractBase(unittest.TestCase):
	def setUp(self):
		self.adapter = WhatsAppGatewayAdapter(CREDENTIALS)

	def parse(self, name):
		return self.adapter.parse_payload(signed_request(name))


class TestSignatureVerification(WhatsAppContractBase):
	def test_good_signature_verifies(self):
		self.assertTrue(self.adapter.verify_inbound(signed_request("text_inbound.json")))

	def test_forged_signature_fails(self):
		body = load_body("text_inbound.json")
		request = make_request(body, secret="attacker-secret")
		self.assertFalse(self.adapter.verify_inbound(request))

	def test_tampered_body_fails(self):
		body = load_body("text_inbound.json")
		request = make_request(body + b" ", signature=sign(body))
		self.assertFalse(self.adapter.verify_inbound(request))

	def test_missing_signature_header_fails(self):
		request = make_request(load_body("text_inbound.json"), signature=None, secret=None)
		self.assertFalse(self.adapter.verify_inbound(request))

	def test_signature_without_sha256_prefix_fails(self):
		body = load_body("text_inbound.json")
		bare = hmac.new(TEST_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
		self.assertFalse(self.adapter.verify_inbound(make_request(body, signature=bare)))

	def test_missing_app_secret_is_rejected_at_construction(self):
		creds = dict(CREDENTIALS, app_secret="")
		with self.assertRaises(ValueError):
			WhatsAppGatewayAdapter(creds)

	def test_empty_app_secret_at_verify_time_fails_closed(self):
		# Construction refuses an empty secret; this guards the verify path if state is mutated.
		self.adapter._app_secret = ""
		self.assertFalse(self.adapter.verify_inbound(signed_request("text_inbound.json")))

	def test_malformed_body_with_valid_signature_still_verifies(self):
		# Signature check is independent of JSON validity; parsing is where it fails.
		self.assertTrue(self.adapter.verify_inbound(signed_request("malformed_json.json")))

	def test_replayed_body_verifies_again_with_same_bytes(self):
		# Meta signatures carry no timestamp (A13): a replay verifies; dedupe happens on wamid.
		first = signed_request("text_inbound.json")
		second = signed_request("text_inbound.json")
		self.assertTrue(self.adapter.verify_inbound(first))
		self.assertTrue(self.adapter.verify_inbound(second))


class TestParseMessages(WhatsAppContractBase):
	def test_text_inbound(self):
		parsed = self.parse("text_inbound.json")
		self.assertEqual(len(parsed.messages), 1)
		event = parsed.messages[0]
		self.assertEqual(event.provider_event_id, WAMID)
		self.assertEqual(event.sender_id, SENDER_DIGITS)
		self.assertEqual(event.conversation_id, SENDER_DIGITS)
		self.assertEqual(event.message_text, "Hi, what are my open leave requests?")
		self.assertIsNone(event.thread_id)
		self.assertEqual(event.display_name, "Ravi Kumar")
		self.assertEqual(tuple(event.attachments), ())
		self.assertEqual((parsed.statuses, parsed.template_updates, parsed.ignored), ((), (), 0))

	def test_formatted_sender_is_normalised_to_digits(self):
		parsed = self.parse("text_inbound_formatted_sender.json")
		event = parsed.messages[0]
		self.assertEqual(event.sender_id, SENDER_DIGITS)
		self.assertEqual(event.conversation_id, SENDER_DIGITS)
		self.assertEqual(event.display_name, "Ravi Kumar")

	def test_quoted_reply_keeps_thread_none_and_records_quoted_id(self):
		event = self.parse("text_quoted_reply.json").messages[0]
		self.assertIsNone(event.thread_id)
		self.assertEqual(event.raw_payload["quoted_message_id"], WAMID2)
		self.assertEqual(event.message_text, "Yes, please approve that one")

	def test_interactive_button_reply_uses_title(self):
		event = self.parse("interactive_button_reply.json").messages[0]
		self.assertEqual(event.message_text, "Approve")
		self.assertIsNone(event.thread_id)

	def test_interactive_list_reply_uses_title(self):
		event = self.parse("interactive_list_reply.json").messages[0]
		self.assertEqual(event.message_text, "HR Department")

	def test_image_with_caption(self):
		event = self.parse("image_with_caption.json").messages[0]
		self.assertEqual(event.message_text, "Receipt for the team lunch")
		self.assertEqual(len(event.attachments), 1)
		attachment = event.attachments[0]
		self.assertEqual(attachment.kind, "image")
		self.assertEqual(attachment.file_id, "1234567890123456")
		self.assertEqual(attachment.mime_type, "image/jpeg")

	def test_document_carries_filename_and_caption(self):
		event = self.parse("document.json").messages[0]
		self.assertEqual(event.message_text, "Signed offer letter")
		attachment = event.attachments[0]
		self.assertEqual(attachment.kind, "document")
		self.assertEqual(attachment.filename, "offer_letter_signed.pdf")
		self.assertEqual(attachment.mime_type, "application/pdf")

	def test_audio_without_caption_gets_placeholder_text(self):
		event = self.parse("audio.json").messages[0]
		self.assertEqual(event.message_text, "[audio message]")
		self.assertEqual(event.attachments[0].kind, "audio")
		self.assertEqual(event.attachments[0].file_id, "3234567890123456")

	def test_location_text_and_window_anchor(self):
		event = self.parse("location.json").messages[0]
		self.assertEqual(event.message_text, '[Location: 12.9716,77.5946 "Head office" MG Road, Bengaluru]')
		self.assertEqual(event.kind, "message")
		self.assertEqual(event.provider_event_id, WAMID)
		self.assert_anchors_window(event, "location")

	def test_location_partial_omits_missing_parts(self):
		self.assertEqual(self.parse("location_minimal.json").messages[0].message_text, "[Location: -33.86,151.2]")

	def test_contacts_text_and_caps(self):
		event = self.parse("contacts.json").messages[0]
		self.assertEqual(
			event.message_text,
			"[Contact: Barbara J. Johnson +1 (415) 555-0829 +1 650 555 0100]\n[Contact: Zoë 山田]",
		)
		self.assert_anchors_window(event, "contacts")

	def test_contacts_cap_five_and_three_phones(self):
		cards = [{"name": {"formatted_name": f"C{i}"}, "phones": [{"phone": str(n)} for n in range(6)]} for i in range(8)]
		text = render_message_text({"type": "contacts", "contacts": cards})
		self.assertEqual(text.count("[Contact:"), 5)
		self.assertIn("[+3 more contacts]", text)
		self.assertIn("[Contact: C0 0 1 2]", text)

	def test_order_text(self):
		event = self.parse("order.json").messages[0]
		self.assertEqual(
			event.message_text,
			"[Order: 2 items, catalog CAT123] SKU-1 x2 @ 30 USD, SKU-2 x1 @ 7.99 USD Please deliver after 5pm",
		)
		self.assert_anchors_window(event, "order")

	def test_order_cap_ten_items(self):
		items = [{"product_retailer_id": f"S{i}", "quantity": 1} for i in range(14)]
		text = render_message_text({"type": "order", "order": {"product_items": items}})
		self.assertTrue(text.startswith("[Order: 14 items]"))
		self.assertIn("S9 x1", text)
		self.assertNotIn("S10", text)
		self.assertIn("(+4 more)", text)

	def test_nfm_reply_flow_response_compacted(self):
		event = self.parse("interactive_nfm_reply.json").messages[0]
		self.assertEqual(
			event.message_text, 'Form submitted: city=Bengaluru, note=café 😀'
		)
		self.assert_anchors_window(event, "interactive")

	def test_nfm_reply_capped_at_2kb(self):
		big = json.dumps({"k": "é" * 5000})
		text = render_message_text({"type": "interactive", "interactive": {"type": "nfm_reply", "nfm_reply": {"name": "f", "response_json": big}}})
		payload = text.split(": ", 1)[1]
		self.assertLessEqual(len(payload.encode("utf-8")), 2048)
		self.assertTrue(payload.endswith("..."))

	def test_nfm_reply_invalid_json_passes_through(self):
		text = render_message_text({"type": "interactive", "interactive": {"type": "nfm_reply", "nfm_reply": {"response_json": "not json"}}})
		self.assertEqual(text, "Form submitted: not json")

	def test_system_message(self):
		event = self.parse("system_number_change.json").messages[0]
		self.assertEqual(event.message_text, "[system message] User A changed from 919876543210 to 919876500000")

	def test_unsupported_message(self):
		event = self.parse("unsupported.json").messages[0]
		self.assertEqual(event.message_text, "[unsupported message: edit] Message type unknown")

	def test_sticker_passes_with_attachment(self):
		event = self.parse("sticker.json").messages[0]
		self.assertEqual(event.message_text, "[sticker message]")
		self.assertEqual(event.attachments[0].kind, "sticker")
		self.assertEqual(event.attachments[0].file_id, "7234567890123456")

	def test_button_quick_reply_keeps_text_and_reply_id(self):
		event = self.parse("button_quick_reply.json").messages[0]
		self.assertEqual(event.message_text, "Confirm")
		self.assertEqual(event.raw_payload["reply_to_message_id"], "wamid.PREV")

	def test_reaction_event_kind_and_ids(self):
		event = self.parse("reaction.json").messages[0]
		self.assertEqual(event.kind, "reaction")
		self.assertEqual(event.reaction_emoji, "👍")
		self.assertEqual(event.reaction_to, WAMID2)
		self.assertEqual(event.message_text, f"[Reaction: 👍 to {WAMID2}]")
		self.assertEqual(event.raw_payload["kind"], "reaction")
		self.assertEqual(event.raw_payload["reaction_to"], WAMID2)

	def test_reaction_removed_has_no_emoji(self):
		event = self.parse("reaction_removed.json").messages[0]
		self.assertEqual((event.kind, event.reaction_emoji), ("reaction", ""))
		self.assertEqual(event.message_text, f"[Reaction removed from {WAMID2}]")

	def test_ctwa_referral_prefix_and_raw(self):
		event = self.parse("text_ctwa_referral.json").messages[0]
		self.assertEqual(event.message_text, "[Ad referral: Summer sale] Is this still available?")
		self.assertEqual(event.raw_payload["referral"]["ctwa_clid"], "AR-abc")
		self.assertEqual(event.raw_payload["referral"]["source_url"], "https://fb.me/ad1")
		self.assertNotIn("referral", self.parse("text_inbound.json").messages[0].raw_payload)

	def test_forwarded_flag(self):
		self.assertTrue(self.parse("text_forwarded.json").messages[0].raw_payload["forwarded"])
		self.assertFalse(self.parse("text_inbound.json").messages[0].raw_payload["forwarded"])

	def test_malformed_and_partial_payloads_do_not_raise(self):
		base = {"from": "919876543210", "id": "wamid.X", "timestamp": "1792000000"}
		bad = [
			{"type": "location", "location": None},
			{"type": "location", "location": "x"},
			{"type": "contacts", "contacts": "oops"},
			{"type": "contacts", "contacts": [None, 3, {"name": None, "phones": [None]}]},
			{"type": "order", "order": []},
			{"type": "order", "order": {"product_items": [None, {"quantity": object.__name__}]}},
			{"type": "interactive", "interactive": None},
			{"type": "interactive", "interactive": {"type": "nfm_reply", "nfm_reply": None}},
			{"type": "system", "system": None},
			{"type": "unsupported", "errors": "x", "unsupported": 5},
			{"type": "reaction", "reaction": None},
			{"type": "carrier_pigeon"},
			{"type": "image", "image": None},
			{"type": "text", "text": {"body": "hi"}, "context": "x", "referral": ["x"]},
		]
		for extra in bad:
			with self.subTest(extra=extra):
				event = self.adapter._message_event({**base, **extra}, {}, {})
				if event is not None:
					self.assertIsInstance(event.message_text, str)
					self.assertTrue(event.message_text.strip())

	def assert_anchors_window(self, event, msg_type):
		"""bridge.window_state reads raw_payload.message.timestamp: it must survive for every type."""
		message = event.raw_payload["message"]
		self.assertEqual(message["type"], msg_type)
		self.assertEqual(message["timestamp"], "1792000000")
		self.assertIsNotNone(message_time(event.raw_payload))

	def test_batch_yields_two_messages_and_one_status(self):
		parsed = self.parse("batch_two_messages_one_status.json")
		self.assertEqual([m.provider_event_id for m in parsed.messages], [WAMID, WAMID2])
		self.assertEqual([m.message_text for m in parsed.messages], [
			"First message in the batch",
			"Second message in the batch",
		])
		self.assertEqual(len(parsed.statuses), 1)
		self.assertEqual(parsed.statuses[0]["status"], "delivered")
		self.assertEqual(parsed.ignored, 0)


class TestParseStatusesAndNonMessages(WhatsAppContractBase):
	def test_status_states(self):
		for name, state in (
			("status_sent.json", "sent"),
			("status_delivered.json", "delivered"),
			("status_read.json", "read"),
			("status_failed.json", "failed"),
			("status_played.json", "played"),
		):
			with self.subTest(fixture=name):
				parsed = self.parse(name)
				self.assertEqual(parsed.messages, ())
				self.assertEqual(len(parsed.statuses), 1)
				self.assertEqual(parsed.statuses[0]["status"], state)

	def test_failed_status_carries_error_code(self):
		status = self.parse("status_failed.json").statuses[0]
		self.assertEqual(status["errors"][0]["code"], 131047)

	def test_template_status_updates(self):
		approved = self.parse("template_status_approved.json")
		self.assertEqual(approved.messages, ())
		self.assertEqual(len(approved.template_updates), 1)
		self.assertEqual(approved.template_updates[0]["event"], "APPROVED")
		self.assertEqual(approved.template_updates[0]["message_template_name"], "leave_approved")

		rejected = self.parse("template_status_rejected.json")
		self.assertEqual(len(rejected.template_updates), 1)
		self.assertEqual(rejected.template_updates[0]["event"], "REJECTED")
		self.assertEqual(rejected.template_updates[0]["reason"], "INVALID_FORMAT")

	def test_status_fixture_shapes(self):
		failed = self.parse("status_failed.json").statuses[0]
		self.assertNotIn("conversation", failed)
		self.assertNotIn("pricing", failed)
		sent = self.parse("status_sent.json").statuses[0]
		self.assertEqual(sent["conversation"]["expiration_timestamp"], "1792086400")
		for name in ("status_sent.json", "status_delivered.json", "status_read.json"):
			pricing = self.parse(name).statuses[0]["pricing"]
			self.assertEqual(pricing["pricing_model"], "PMP")
			self.assertEqual({"billable", "type", "category"} - set(pricing), set())

	def test_template_quality_category_and_language_variants(self):
		quality = self.parse("template_quality_update.json")
		self.assertEqual(quality.messages, ())
		self.assertEqual(len(quality.template_updates), 1)
		self.assertEqual(quality.template_updates[0]["kind"], "quality")
		self.assertEqual(quality.template_updates[0]["new_quality_score"], "RED")
		category = self.parse("template_category_update.json")
		self.assertEqual(category.template_updates[0]["kind"], "category")
		self.assertEqual(category.template_updates[0]["new_category"], "MARKETING")
		self.assertEqual(self.parse("template_status_approved.json").template_updates[0]["kind"], "status")
		hyphen = self.parse("template_status_approved_en-US.json").template_updates[0]
		self.assertEqual(hyphen["message_template_language"], "en-US")

	def test_errors_only_message_change_is_ignored(self):
		parsed = self.parse("errors_only_message_change.json")
		self.assertEqual((parsed.messages, parsed.statuses, parsed.template_updates), ((), (), ()))
		self.assertEqual(parsed.ignored, 1)

	def test_account_update_is_ignored(self):
		parsed = self.parse("account_update.json")
		self.assertEqual((parsed.messages, parsed.statuses, parsed.template_updates), ((), (), ()))
		self.assertEqual(parsed.ignored, 1)

	def test_wrong_phone_number_id_is_ignored(self):
		parsed = self.parse("wrong_phone_number_id.json")
		self.assertEqual(parsed.messages, ())
		self.assertEqual(parsed.ignored, 1)
		self.assertNotEqual(WRONG_PHONE_NUMBER_ID, PHONE_NUMBER_ID)

	def test_malformed_json_raises_in_parse_and_normalize(self):
		request = signed_request("malformed_json.json")
		with self.assertRaises(ValueError):
			self.adapter.parse_payload(request)
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(request)

	def test_normalize_inbound_raises_for_status_only(self):
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(signed_request("status_read.json"))

	def test_normalize_inbound_returns_first_message(self):
		event = self.adapter.normalize_inbound(signed_request("batch_two_messages_one_status.json"))
		self.assertEqual(event.provider_event_id, WAMID)


class TestReplayDedupeKey(WhatsAppContractBase):
	def test_duplicate_delivery_yields_identical_provider_event_id(self):
		# A13: replay = duplicate wamid -> one Run. Two deliveries must share the dedupe key.
		first = self.parse("text_inbound.json").messages[0]
		second = self.parse("text_inbound.json").messages[0]
		self.assertEqual(first.provider_event_id, second.provider_event_id)
		self.assertEqual(first.provider_event_id, WAMID)
		self.assertEqual(first, second)

	def test_distinct_wamids_yield_distinct_event_ids(self):
		batch = self.parse("batch_two_messages_one_status.json").messages
		self.assertNotEqual(batch[0].provider_event_id, batch[1].provider_event_id)


if __name__ == "__main__":
	unittest.main()


class TestRecordIncomingMirror(WhatsAppContractBase):
	"""bridge.record_incoming mirrors every non-reaction type with the right content_type and text."""

	def mirror(self, fixture):
		from unittest.mock import MagicMock, patch

		import frappe

		from huf.ai.gateway_adapters import whatsapp_bridge as wb

		message = self.parse(fixture).messages[0].raw_payload["message"]
		doc = MagicMock()
		doc.name = "WAM-1"
		with patch.object(wb, "is_available", return_value=True), patch.object(
			frappe.db, "get_value", return_value=None
		), patch.object(frappe, "get_doc", return_value=doc) as get_doc:
			result = wb.record_incoming("ACC", message, "Ravi")
		return result, (get_doc.call_args.args[0] if get_doc.called else None)

	def test_mirrored_types(self):
		for fixture, content_type, text in (
			("location.json", "location", '[Location: 12.9716,77.5946 "Head office" MG Road, Bengaluru]'),
			("contacts.json", "contact", None),
			("order.json", "order", None),
			("interactive_nfm_reply.json", "interactive", None),
			("sticker.json", "image", "[sticker message]"),
			("system_number_change.json", "text", None),
			("unsupported.json", "text", "[unsupported message: edit] Message type unknown"),
			("image_with_caption.json", "image", "Receipt for the team lunch"),
			("text_inbound.json", "text", "Hi, what are my open leave requests?"),
		):
			with self.subTest(fixture=fixture):
				result, values = self.mirror(fixture)
				self.assertEqual(result, "WAM-1")
				self.assertEqual(values["content_type"], content_type)
				self.assertTrue(values["message"])
				if text:
					self.assertEqual(values["message"], text)

	def test_reaction_not_mirrored(self):
		result, values = self.mirror("reaction.json")
		self.assertIsNone(result)
		self.assertIsNone(values)
