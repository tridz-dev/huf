# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Contract tests for the WhatsApp Cloud API adapter, driven by recorded webhook fixtures.

Each fixture under ``fixtures/whatsapp`` is a realistic Meta webhook body. Bodies are
signed with a test app secret so ``verify_inbound`` and ``parse_payload`` run exactly
as they do for a live delivery.
"""

import hashlib
import hmac
import json
import pathlib
import unittest

from huf.ai.gateway_adapters.types import GatewayInboundRequest
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "whatsapp"

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

	def test_location_is_unsupported_and_ignored(self):
		parsed = self.parse("location_unsupported.json")
		self.assertEqual(parsed.messages, ())
		self.assertEqual(parsed.ignored, 1)

	def test_reaction_is_unsupported_and_ignored(self):
		parsed = self.parse("reaction.json")
		self.assertEqual(parsed.messages, ())
		self.assertEqual(parsed.ignored, 1)

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
