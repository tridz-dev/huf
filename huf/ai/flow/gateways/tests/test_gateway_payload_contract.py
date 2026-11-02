# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""The flat ``input.*`` payload of a gateway message equals the registry's generic ``payload_fields``."""

import unittest
from types import SimpleNamespace

from huf.ai.flow.gateways import gateway_payload as gp
from huf.ai.flow.gateways.generic import generic_fields

#: Present in the payload for older flows but not offered in the picker.
LEGACY_KEYS = {"wa_id", "interactive_reply"}
#: Only filled when a matching trigger asks for voice notes (Q7), so absent from a plain payload.
OPTIONAL_KEYS = {"transcript"}


def event(raw):
	return SimpleNamespace(
		name="GWE-1", sender_id="15550001111", conversation_id="15550001111", thread_id="15550001111",
		provider_event_id="wamid.1", message_text="Hello", raw_payload=raw, received_at="2026-01-15 17:15:00",
	)


GW = SimpleNamespace(name="Support", provider="whatsapp")


class TestPayloadContract(unittest.TestCase):
	def test_generic_registry_paths_equal_payload_keys(self):
		payload = gp.build_payload(event({"message": {"type": "text"}}), GW, [])
		registry = {f["path"].removeprefix("input.") for f in generic_fields()}
		self.assertEqual(registry - OPTIONAL_KEYS - set(payload), set())
		self.assertEqual(set(payload) - registry - LEGACY_KEYS, set())

	def test_values(self):
		raw = {"contact_name": "Asha", "message": {"type": "text", "context": {"id": "wamid.0"}}}
		p = gp.build_payload(event(raw), GW, ["/files/a.png"])
		self.assertEqual((p["display_name"], p["text"], p["message"], p["kind"]), ("Asha", "Hello", "Hello", "message"))
		self.assertEqual((p["is_room"], p["mentioned"], p["language"], p["message_type"]), (False, False, "", "text"))
		self.assertEqual(p["attachments"], ["/files/a.png"])
		self.assertEqual((p["received_at"], p["reply_to_message_id"]), ("2026-01-15 17:15:00", "wamid.0"))

	def test_message_type_whatsapp(self):
		cases = {
			"image": "image", "video": "video", "document": "document", "sticker": "sticker", "location": "location",
			"contacts": "contact", "order": "order", "button": "button_reply", "weird": "other",
		}
		for wa, want in cases.items():
			self.assertEqual(gp.normalize_message_type({"message": {"type": wa}}), want, wa)
		self.assertEqual(gp.normalize_message_type({"message": {"type": "audio", "audio": {"voice": True}}}), "voice")
		self.assertEqual(gp.normalize_message_type({"message": {"type": "audio", "audio": {}}}), "audio")
		self.assertEqual(
			gp.normalize_message_type({"message": {"type": "interactive", "interactive": {"list_reply": {"id": "1"}}}}), "list_reply"
		)
		self.assertEqual(
			gp.normalize_message_type({"message": {"type": "interactive", "interactive": {"button_reply": {"id": "1"}}}}), "button_reply"
		)
		self.assertEqual(gp.normalize_message_type({}), "text")

	def test_telegram_shapes(self):
		raw = {
			"message": {"text": "hi", "chat": {"type": "supergroup"}, "from": {"first_name": "Asha", "last_name": "K", "language_code": "en"}},
			"telegram_meta": {"mentioned": True},
		}
		p = gp.build_payload(event(raw), SimpleNamespace(name="Bot", provider="telegram"), [])
		self.assertEqual((p["display_name"], p["is_room"], p["mentioned"], p["language"]), ("Asha K", True, True, "en"))
		self.assertEqual(gp.normalize_message_type({"message": {"voice": {"file_id": "x"}}}), "voice")
		self.assertEqual(gp.normalize_message_type({"message": {"photo": [{}]}}), "image")
		self.assertEqual(gp.normalize_message_type({"callback_query": {"data": "x"}}), "button_reply")
		self.assertEqual(gp.event_kind({"callback_query": {}}), "callback")
		self.assertEqual(gp.event_kind({"kind": "reaction"}), "reaction")

	def test_extra_fields_hook_is_merged_last(self):
		p = gp.build_payload(event({}), GW, [], lambda ev, gw, sender: {"wa_id": sender, "command": "start"})
		self.assertEqual((p["wa_id"], p["command"]), ("15550001111", "start"))

	def test_string_raw_payload(self):
		p = gp.build_payload(event('{"contact_name": "Asha"}'), GW, [])
		self.assertEqual(p["display_name"], "Asha")
		self.assertEqual(gp.build_payload(event("not json"), GW, [])["display_name"], "")


if __name__ == "__main__":
	unittest.main()
