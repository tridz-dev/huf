# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Outbound matrix (mocked Graph, no network): one case per outbound row, asserting the exact wire body that
reaches ``/messages`` per the Meta Cloud API docs, the voice-note rules, and Graph error mapping on send.

Builder boundaries live in ``test_whatsapp_messages``; the strict fake-Graph schema runs in
``test_whatsapp_fake_graph``. This module drives ``whatsapp_bridge`` with a stub ``http_post``.
"""

import json
import unittest
from unittest.mock import patch

from huf.ai.gateway_adapters import whatsapp_bridge as wb
from huf.ai.gateway_adapters import whatsapp_format as wf
from huf.ai.gateway_adapters import whatsapp_messages as wm

TO = "15551234567"
ACCT = {"name": "ACC", "phone_id": "111", "token": "tok", "url": "https://graph.facebook.com", "version": "v25.0"}


class Resp:
	def __init__(self, body, status=200):
		self._body, self.status_code = body, status
		self.text = json.dumps(body)

	def json(self):
		return self._body


class Post:
	"""Stub for ``http_post``: records calls, answers 200 with a wamid or the scripted response."""

	def __init__(self, response=None):
		self.calls, self.response = [], response

	def __call__(self, url, *, json, headers, timeout):
		self.calls.append({"url": url, "json": json, "headers": headers})
		return self.response or Resp({"messages": [{"id": "wamid.OUT1"}]})

	@property
	def body(self):
		return self.calls[-1]["json"]


def graph_error(code, status=400, message="boom"):
	return Resp({"error": {"code": code, "message": message}}, status)


class _Base(unittest.TestCase):
	def setUp(self):
		for p in (
			patch.object(wb, "_account_or_error", return_value=ACCT),
			patch.object(wb, "is_available", return_value=True),
			patch.object(wb, "_mirror_direct_send", side_effect=lambda a, p, w, t: {"success": True, "message_id": w}),
			patch("frappe.has_permission", return_value=True),
		):
			p.start()
			self.addCleanup(p.stop)
		self.post = Post()


class TestOutboundWireShapes(_Base):
	def assertBase(self, body, mtype):
		self.assertEqual(body["messaging_product"], "whatsapp")
		self.assertEqual(body["recipient_type"], "individual")
		self.assertEqual((body["to"], body["type"]), (TO, mtype))

	def send_media(self, kind, **kw):
		res = wb.send_media("ACC", TO, kind, http_post=self.post, trusted=True, **kw)
		self.assertTrue(res["success"])
		return self.post.body

	def test_endpoint_and_auth(self):
		self.send_media("image", media_id="1")
		call = self.post.calls[0]
		self.assertEqual(call["url"], "https://graph.facebook.com/v25.0/111/messages")
		self.assertEqual(call["headers"]["Authorization"], "Bearer tok")

	def test_text_markdown_is_converted_for_whatsapp(self):
		out = wf.to_whatsapp("**bold** and *it* and [x](https://a.example)")
		self.assertIn("*bold*", out)
		self.assertNotIn("**", out)

	def test_long_text_splits_under_the_4096_cap(self):
		parts = wf.split_body("\n\n".join(["p" * 1000] * 6))
		self.assertGreater(len(parts), 1)
		self.assertTrue(all(0 < len(p) <= 4096 for p in parts))

	def test_image_by_link_and_by_media_id(self):
		# a plain link send goes through the frappe_whatsapp document (not a direct Graph post), so check the body
		body, errors = wm.build_media_payload(TO, "image", link="https://cdn.example/a.png", caption="hi")
		self.assertEqual(errors, [])
		self.assertBase(body, "image")
		self.assertEqual(body["image"], {"link": "https://cdn.example/a.png", "caption": "hi"})
		body = self.send_media("image", media_id="42")
		self.assertEqual(body["image"], {"id": "42"})

	def test_document_carries_filename_and_caption(self):
		body = self.send_media("document", link="https://cdn.example/a.pdf", filename="a.pdf", caption="doc")
		self.assertBase(body, "document")
		self.assertEqual(body["document"], {"link": "https://cdn.example/a.pdf", "caption": "doc", "filename": "a.pdf"})

	def test_audio_plain_has_no_voice_flag_and_no_caption(self):
		body = self.send_media("audio", media_id="7")
		self.assertBase(body, "audio")
		self.assertEqual(body["audio"], {"id": "7"})

	def test_voice_note_sets_voice_true(self):
		body = self.send_media("audio", media_id="7", voice=True)
		self.assertEqual(body["audio"], {"id": "7", "voice": True})

	def test_send_voice_note_helper(self):
		res = wb.send_voice_note("ACC", TO, link="https://cdn.example/v.ogg", http_post=self.post, trusted=True)
		self.assertTrue(res["success"])
		self.assertBase(self.post.body, "audio")
		self.assertEqual(self.post.body["audio"], {"link": "https://cdn.example/v.ogg", "voice": True})
		wb.send_voice_note("ACC", TO, media_id="9", reply_to="wamid.IN", http_post=self.post, trusted=True)
		self.assertEqual(self.post.body["context"], {"message_id": "wamid.IN"})

	def test_send_voice_note_rejects_non_ogg_before_any_call(self):
		for link in ("https://cdn.example/v.mp3", "https://cdn.example/v.m4a", "https://cdn.example/v"):
			with self.assertRaises(wb.BridgeError) as cm:
				wb.send_voice_note("ACC", TO, link=link, http_post=self.post, trusted=True)
			self.assertEqual(cm.exception.payload["errors"][0]["code"], "voice_needs_ogg_opus")
		self.assertEqual(self.post.calls, [])

	def test_voice_link_extension_check(self):
		for ok in ("https://x.example/v.ogg", "https://x.example/v.OPUS?sig=1", "https://x.example/v.oga#t"):
			self.assertEqual(wm.validate_voice_link(ok), [])
		self.assertEqual(wm.build_voice_note_payload(TO, link="https://x.example/v.wav")[0], None)
		payload, errors = wm.build_voice_note_payload(TO, media_id="5")
		self.assertEqual((errors, payload["audio"]), ([], {"id": "5", "voice": True}))

	def test_video(self):
		body, errors = wm.build_media_payload(TO, "video", link="https://cdn.example/a.mp4", caption="clip")
		self.assertEqual(errors, [])
		self.assertBase(body, "video")
		self.assertEqual(body["video"], {"link": "https://cdn.example/a.mp4", "caption": "clip"})

	def test_sticker_by_id(self):
		wb.send_sticker("ACC", TO, media_id="77", http_post=self.post, trusted=True)
		self.assertBase(self.post.body, "sticker")
		self.assertEqual(self.post.body["sticker"], {"id": "77"})

	def test_location(self):
		wb.send_location("ACC", TO, 12.5, 77.5, "Office", "MG Road", http_post=self.post, trusted=True)
		self.assertBase(self.post.body, "location")
		self.assertEqual(
			self.post.body["location"], {"latitude": 12.5, "longitude": 77.5, "name": "Office", "address": "MG Road"}
		)

	def test_contacts(self):
		contact = {"name": {"formatted_name": "Ann Lee"}, "phones": [{"phone": "+15551230000", "wa_id": "15551230000"}]}
		wb.send_contacts("ACC", TO, [contact], http_post=self.post, trusted=True)
		self.assertBase(self.post.body, "contacts")
		self.assertEqual(self.post.body["contacts"][0]["name"]["formatted_name"], "Ann Lee")
		self.assertEqual(self.post.body["contacts"][0]["phones"][0]["phone"], "+15551230000")

	def test_reaction_and_remove(self):
		wb.send_reaction("ACC", TO, "wamid.IN1", "\U0001F44D", http_post=self.post, trusted=True)
		self.assertBase(self.post.body, "reaction")
		self.assertEqual(self.post.body["reaction"], {"message_id": "wamid.IN1", "emoji": "\U0001F44D"})
		wb.send_reaction("ACC", TO, "wamid.IN1", "", http_post=self.post, trusted=True)
		self.assertEqual(self.post.body["reaction"], {"message_id": "wamid.IN1", "emoji": ""})

	def interactive(self, kind, spec):
		wb.send_interactive("ACC", TO, kind, spec, http_post=self.post, trusted=True)
		self.assertBase(self.post.body, "interactive")
		return self.post.body["interactive"]

	def test_interactive_buttons(self):
		i = self.interactive("buttons", {"body": "Pick", "buttons": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]})
		self.assertEqual(i["type"], "button")
		self.assertEqual(i["body"], {"text": "Pick"})
		self.assertEqual(i["action"]["buttons"][1], {"type": "reply", "reply": {"id": "b", "title": "B"}})

	def test_interactive_list(self):
		spec = {"body": "Menu", "button_text": "Open", "sections": [{"title": "S", "rows": [{"id": "1", "title": "One"}]}]}
		i = self.interactive("list", spec)
		self.assertEqual(i["type"], "list")
		self.assertEqual(i["action"]["button"], "Open")
		self.assertEqual(i["action"]["sections"][0]["rows"][0], {"id": "1", "title": "One"})

	def test_interactive_cta_url(self):
		i = self.interactive("cta_url", {"body": "See", "display_text": "Open", "url": "https://shop.example/x"})
		self.assertEqual(i["type"], "cta_url")
		self.assertEqual(
			i["action"], {"name": "cta_url", "parameters": {"display_text": "Open", "url": "https://shop.example/x"}}
		)

	def test_interactive_location_request(self):
		i = self.interactive("location_request", {"body": "Where are you?"})
		self.assertEqual(i["type"], "location_request_message")
		self.assertEqual(i["action"], {"name": "send_location"})

	def test_reply_context_on_media(self):
		body = self.send_media("image", media_id="1", reply_to="wamid.Q")
		self.assertEqual(body["context"], {"message_id": "wamid.Q"})


class TestOutboundGraphErrors(_Base):
	"""A Graph error on send surfaces as a BridgeError carrying the classified code, kind and retryability."""

	CASES = {
		131047: ("window_closed", False),
		130429: ("rate_limited", True),
		131056: ("pair_rate_limited", True),
		190: ("auth", False),
	}

	def test_error_codes_map_on_every_typed_send(self):
		sends = {
			"media": lambda post: wb.send_media("ACC", TO, "image", media_id="1", http_post=post, trusted=True),
			"voice": lambda post: wb.send_voice_note("ACC", TO, media_id="1", http_post=post, trusted=True),
			"location": lambda post: wb.send_location("ACC", TO, 1, 2, http_post=post, trusted=True),
			"reaction": lambda post: wb.send_reaction("ACC", TO, "wamid.X", "\U0001F44D", http_post=post, trusted=True),
			"interactive": lambda post: wb.send_interactive(
				"ACC", TO, "location_request", {"body": "Where?"}, http_post=post, trusted=True
			),
		}
		for code, (kind, retryable) in self.CASES.items():
			for name, send in sends.items():
				with self.subTest(code=code, send=name):
					post = Post(graph_error(code, 401 if code == 190 else 400))
					with self.assertRaises(wb.BridgeError) as cm:
						send(post)
					payload = cm.exception.payload
					self.assertEqual(payload["graph_code"], code)
					self.assertEqual((payload["kind"], payload["retryable"]), (kind, retryable))
					self.assertEqual(len(post.calls), 1)

	def test_transport_failure_is_send_failed(self):
		def boom(*a, **k):
			raise ConnectionError("down")

		with self.assertRaises(wb.BridgeError) as cm:
			wb.send_media("ACC", TO, "image", media_id="1", http_post=boom, trusted=True)
		self.assertEqual(cm.exception.payload["error"], "send_failed")

	def test_invalid_voice_never_reaches_graph(self):
		with self.assertRaises(wb.BridgeError):
			wb.send_media("ACC", TO, "image", media_id="1", voice=True, http_post=self.post, trusted=True)
		self.assertEqual(self.post.calls, [])


if __name__ == "__main__":
	unittest.main()
