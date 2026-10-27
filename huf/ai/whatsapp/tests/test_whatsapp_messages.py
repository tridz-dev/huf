# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure tests for the outbound message builders (no frappe, no network): every type and every limit boundary."""

import unittest

from huf.ai.gateway_adapters import whatsapp_messages as wm
from huf.ai.gateway_adapters import whatsapp_templates as wt

TO = "15551234567"


def codes(errors):
	return [e["code"] for e in errors]


def fields(errors):
	return [e["field"] for e in errors]


class TestMediaBuilders(unittest.TestCase):
	def test_kinds_include_sticker(self):
		self.assertEqual(set(wt.MEDIA_KINDS), {"image", "document", "audio", "video", "sticker"})

	def test_link_or_id_exactly_one(self):
		for kind in wt.MEDIA_KINDS:
			by_link, errors = wm.build_media_payload(TO, kind, link="https://cdn.example/a")
			self.assertEqual(errors, [])
			self.assertEqual(by_link[kind], {"link": "https://cdn.example/a"})
			by_id, errors = wm.build_media_payload(TO, kind, media_id="123")
			self.assertEqual((errors, by_id[kind]), ([], {"id": "123"}))
			self.assertIn("link_or_id", codes(wm.build_media_payload(TO, kind)[1]))
			self.assertIn("link_or_id", codes(wm.build_media_payload(TO, kind, link="https://a/b", media_id="1")[1]))
		self.assertIn("invalid_link", codes(wm.build_media_payload(TO, "image", link="ftp://x/y")[1]))
		self.assertIn("invalid_kind", codes(wm.build_media_payload(TO, "gif", link="https://a/b")[1]))

	def test_caption_boundaries_and_where_allowed(self):
		for kind in ("image", "video", "document"):
			ok, errors = wm.build_media_payload(TO, kind, link="https://a/b", caption="x" * 1024)
			self.assertEqual((errors, len(ok[kind]["caption"])), ([], 1024))
			self.assertIn("too_long", codes(wm.build_media_payload(TO, kind, link="https://a/b", caption="x" * 1025)[1]))
		for kind in ("audio", "sticker"):
			self.assertIn("not_allowed", codes(wm.build_media_payload(TO, kind, link="https://a/b", caption="hi")[1]))

	def test_filename_only_for_documents(self):
		doc, _ = wm.build_media_payload(TO, "document", link="https://a/b.pdf", filename="b.pdf")
		self.assertEqual(doc["document"]["filename"], "b.pdf")
		img, _ = wm.build_media_payload(TO, "image", link="https://a/b.png", filename="ignored.png")
		self.assertNotIn("filename", img["image"])
		self.assertEqual(wm.build_media_payload(TO, "document", link="https://a/b", filename="f" * 240)[1], [])
		self.assertIn("too_long", codes(wm.build_media_payload(TO, "document", link="https://a/b", filename="f" * 241)[1]))

	def test_voice_note_only_for_audio(self):
		voice, errors = wm.build_media_payload(TO, "audio", media_id="9", voice=True)
		self.assertEqual((errors, voice["audio"]), ([], {"id": "9", "voice": True}))
		self.assertNotIn("voice", wm.build_media_payload(TO, "audio", media_id="9")[0]["audio"])
		self.assertIn("not_allowed", codes(wm.build_media_payload(TO, "image", media_id="9", voice=True)[1]))

	def test_sticker_and_reply_context(self):
		payload, errors = wm.build_sticker_payload(TO, media_id="55", reply_to="wamid.X")
		self.assertEqual(errors, [])
		self.assertEqual(payload["type"], "sticker")
		self.assertEqual(payload["context"], {"message_id": "wamid.X"})
		self.assertEqual(payload["sticker"], {"id": "55"})

	def test_legacy_wt_functions_still_work(self):
		media, errors = wt.validate_media_request("image", "https://a/b.png", None, "cap", None)
		self.assertEqual(errors, [])
		body = wt.build_media_payload(TO, media, "wamid.R")
		self.assertEqual(body["image"], {"link": "https://a/b.png", "caption": "cap"})
		self.assertEqual(body["context"], {"message_id": "wamid.R"})
		self.assertIs(wt.build_location_payload, wm.build_location_payload)


class TestMediaFileRules(unittest.TestCase):
	def test_size_boundaries_per_kind(self):
		mb = 1024 * 1024
		cases = [
			("image", "image/jpeg", 5 * mb, 5 * mb + 1),
			("image", "image/png", 5 * mb, 5 * mb + 1),
			("video", "video/mp4", 16 * mb, 16 * mb + 1),
			("video", "video/3gpp", 16 * mb, 16 * mb + 1),
			("audio", "audio/mpeg", 16 * mb, 16 * mb + 1),
			("document", "application/pdf", 100 * mb, 100 * mb + 1),
		]
		for kind, mime, ok_size, bad_size in cases:
			self.assertEqual(wm.validate_media_file(kind, mime, ok_size), [], (kind, mime))
			self.assertEqual(codes(wm.validate_media_file(kind, mime, bad_size)), ["too_large"], (kind, mime))

	def test_sticker_static_and_animated_caps(self):
		static_head = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16
		anim_head = b"RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x02" + b"\x00" * 8  # byte 20 = 0x02 (animation flag)
		self.assertFalse(wm.webp_is_animated(static_head))
		self.assertTrue(wm.webp_is_animated(anim_head))
		self.assertEqual(wm.validate_media_file("sticker", "image/webp", 100 * 1024, static_head), [])
		self.assertEqual(codes(wm.validate_media_file("sticker", "image/webp", 100 * 1024 + 1, static_head)), ["too_large"])
		self.assertEqual(wm.validate_media_file("sticker", "image/webp", 500 * 1024, anim_head), [])
		self.assertEqual(codes(wm.validate_media_file("sticker", "image/webp", 500 * 1024 + 1, anim_head)), ["too_large"])

	def test_mime_whitelist(self):
		self.assertEqual(codes(wm.validate_media_file("image", "image/gif", 10)), ["unsupported_mime"])
		self.assertEqual(codes(wm.validate_media_file("image", "image/svg+xml", 10)), ["unsupported_mime"])
		self.assertEqual(codes(wm.validate_media_file("sticker", "image/png", 10)), ["unsupported_mime"])
		self.assertEqual(codes(wm.validate_media_file("audio", "audio/wav", 10)), ["unsupported_mime"])
		self.assertEqual(codes(wm.validate_media_file("document", "application/zip", 10)), ["unsupported_mime"])
		self.assertEqual(codes(wm.validate_media_file("image", "image/png", 0)), ["empty_file"])
		self.assertEqual(codes(wm.validate_media_file("gif", "image/png", 10)), ["invalid_kind"])
		self.assertEqual(wm.kind_for_mime("image/webp"), "sticker")
		self.assertEqual(wm.kind_for_mime("audio/ogg; codecs=opus"), "audio")
		self.assertEqual(wm.kind_for_mime("text/html"), "")

	def test_validate_upload_infers_the_kind(self):
		self.assertEqual(wm.validate_upload("image/webp", b"RIFF", None), ("sticker", []))
		self.assertEqual(wm.validate_upload("image/png", b"x" * 10, "image"), ("image", []))
		kind, errors = wm.validate_upload("image/gif", b"GIF89a")
		self.assertEqual((kind, codes(errors)), ("", ["unsupported_mime"]))
		self.assertEqual(codes(wm.validate_upload("image/png", b"", None)[1]), ["empty_file"])
		self.assertEqual(codes(wm.validate_upload("image/png", b"x", "video")[1]), ["unsupported_mime"])

	def test_voice_note_needs_ogg_opus(self):
		self.assertEqual(wm.validate_media_file("audio", "audio/ogg; codecs=opus", 10, voice=True), [])
		self.assertEqual(wm.validate_media_file("audio", "audio/ogg", 10, voice=True), [])
		self.assertEqual(codes(wm.validate_media_file("audio", "audio/mpeg", 10, voice=True)), ["voice_needs_ogg_opus"])
		self.assertEqual(codes(wm.validate_media_file("audio", "audio/ogg; codecs=vorbis", 10, voice=True)), ["voice_needs_ogg_opus"])


class TestLocation(unittest.TestCase):
	def test_valid(self):
		payload, errors = wm.build_location_payload(TO, "37.44", -122.16, "Philz", "101 Forest Ave")
		self.assertEqual(errors, [])
		self.assertEqual(payload["location"], {"latitude": 37.44, "longitude": -122.16, "name": "Philz", "address": "101 Forest Ave"})
		self.assertNotIn("name", wm.build_location_payload(TO, 1, 2)[0]["location"])

	def test_range_boundaries(self):
		for lat, lng, ok in ((90, 180, True), (-90, -180, True), (0, 0, True), (90.0001, 0, False), (-90.0001, 0, False), (0, 180.0001, False), (0, -180.0001, False)):
			errors = wm.build_location_payload(TO, lat, lng)[1]
			self.assertEqual(errors == [], ok, (lat, lng, errors))

	def test_required_and_types(self):
		self.assertEqual(codes(wm.build_location_payload(TO, None, 1)[1]), ["required"])
		self.assertEqual(codes(wm.build_location_payload(TO, 1, "")[1]), ["required"])
		self.assertEqual(codes(wm.build_location_payload(TO, "abc", 1)[1]), ["invalid_coordinate"])
		self.assertEqual(codes(wm.build_location_payload(TO, True, 1)[1]), ["required"])
		self.assertEqual(codes(wm.build_location_payload(TO, float("nan"), 1)[1]), ["out_of_range"])

	def test_text_length_boundaries(self):
		self.assertEqual(wm.build_location_payload(TO, 1, 2, "n" * 100, "a" * 300)[1], [])
		self.assertEqual(fields(wm.build_location_payload(TO, 1, 2, "n" * 101)[1]), ["name"])
		self.assertEqual(fields(wm.build_location_payload(TO, 1, 2, None, "a" * 301)[1]), ["address"])


class TestContacts(unittest.TestCase):
	def good(self, **over):
		return {"name": {"formatted_name": "Ann Lee", "first_name": "Ann"}, "phones": [{"phone": "+15551230000", "type": "CELL", "wa_id": "15551230000"}], **over}

	def test_full_contact(self):
		contact = self.good(
			emails=[{"email": "ann@example.com", "type": "WORK"}],
			urls=[{"url": "https://example.com", "type": "WORK"}],
			addresses=[{"street": "1 Main", "city": "Paris", "country_code": "FR", "type": "HOME"}],
			org={"company": "Acme", "title": "CEO"},
			birthday="1990-02-28",
		)
		payload, errors = wm.build_contacts_payload(TO, [contact])
		self.assertEqual(errors, [])
		self.assertEqual(payload["contacts"][0]["birthday"], "1990-02-28")
		self.assertEqual(payload["contacts"][0]["phones"][0]["wa_id"], "15551230000")

	def test_formatted_name_required_and_string_shorthand(self):
		self.assertIn("required", codes(wm.build_contacts_payload(TO, [{"phones": [{"phone": "1"}]}])[1]))
		self.assertIn("required", codes(wm.build_contacts_payload(TO, [{"name": {"first_name": "A"}}])[1]))
		payload, errors = wm.build_contacts_payload(TO, [{"name": "Bob"}])
		self.assertEqual((errors, payload["contacts"][0]["name"]), ([], {"formatted_name": "Bob"}))

	def test_count_boundaries(self):
		one = {"name": "A"}
		self.assertEqual(wm.build_contacts_payload(TO, [one] * 257)[1], [])
		self.assertEqual(codes(wm.build_contacts_payload(TO, [one] * 258)[1]), ["too_many"])
		self.assertEqual(codes(wm.build_contacts_payload(TO, [])[1]), ["required"])
		self.assertEqual(codes(wm.build_contacts_payload(TO, None)[1]), ["required"])
		self.assertEqual(wm.build_contacts_payload(TO, one)[1], [])  # a single dict is accepted

	def test_field_validation(self):
		bad = {
			"email": self.good(emails=[{"email": "nope"}]),
			"url": self.good(urls=[{"url": "ftp://x"}]),
			"birthday_format": self.good(birthday="28/02/1990"),
			"birthday_date": self.good(birthday="1990-02-30"),
			"country_code": self.good(addresses=[{"country_code": "FRA"}]),
			"unknown": self.good(nickname="x"),
			"phone_empty": self.good(phones=[{"type": "CELL"}]),
			"org_type": self.good(org="Acme"),
		}
		expect = {
			"email": "invalid_email", "url": "invalid_url", "birthday_format": "invalid_birthday", "birthday_date": "invalid_birthday",
			"country_code": "invalid_country_code", "unknown": "unknown_field", "phone_empty": "required", "org_type": "invalid_type",
		}
		for key, contact in bad.items():
			self.assertIn(expect[key], codes(wm.build_contacts_payload(TO, [contact])[1]), key)
		self.assertEqual(wm.build_contacts_payload(TO, [self.good(birthday="2024-02-29")])[1], [])  # leap day

	def test_text_cap_and_simple_contact(self):
		self.assertEqual(wm.build_contacts_payload(TO, [{"name": "n" * 200}])[1], [])
		self.assertIn("too_long", codes(wm.build_contacts_payload(TO, [{"name": "n" * 201}])[1]))
		simple = wm.simple_contact("Ann", "+1555", "a@b.co", "Acme")
		self.assertEqual(wm.build_contacts_payload(TO, [simple])[1], [])
		self.assertEqual(simple["org"], {"company": "Acme"})


class TestReaction(unittest.TestCase):
	def test_single_emoji_table(self):
		ok = ["👍", "❤️", "❤", "😀", "🙏🏽", "👨‍👩‍👧", "🇮🇳", "1️⃣", "✅", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "👍🏻", "🔥"]
		bad = ["", "a", "ab", "👍👍", "😀a", "1", "#", "hello", "🇮", "🇮🇳🇮🇳", "👍‍", "‍👍", "text 👍", "👍 "]
		for e in ok:
			self.assertTrue(wm.is_single_emoji(e), repr(e))
		for e in bad:
			self.assertFalse(wm.is_single_emoji(e), repr(e))

	def test_payload(self):
		payload, errors = wm.build_reaction_payload(TO, "wamid.ABC", "👍")
		self.assertEqual(errors, [])
		self.assertEqual(payload["reaction"], {"message_id": "wamid.ABC", "emoji": "👍"})
		self.assertNotIn("context", payload)

	def test_remove(self):
		for args in (("wamid.ABC", ""), ("wamid.ABC", None), ("wamid.ABC", "👍", True)):
			payload, errors = wm.build_reaction_payload(TO, *args)
			self.assertEqual((errors, payload["reaction"]), ([], {"message_id": "wamid.ABC", "emoji": ""}))

	def test_validation(self):
		self.assertEqual(codes(wm.build_reaction_payload(TO, "", "👍")[1]), ["required"])
		self.assertEqual(codes(wm.build_reaction_payload(TO, None, "👍")[1]), ["required"])
		self.assertEqual(codes(wm.build_reaction_payload(TO, "wamid.A B", "👍")[1]), ["invalid_message_id"])
		self.assertEqual(codes(wm.build_reaction_payload(TO, "wamid.A", "hi")[1]), ["invalid_emoji"])
		self.assertEqual(codes(wm.build_reaction_payload(TO, "wamid.A", "👍👍")[1]), ["invalid_emoji"])
		self.assertEqual(wm.build_reaction_payload(TO, "w" * 256, "👍")[1], [])
		self.assertEqual(codes(wm.build_reaction_payload(TO, "w" * 257, "👍")[1]), ["invalid_message_id"])


class TestReplyButtons(unittest.TestCase):
	def btns(self, n=3):
		return [{"id": f"id{i}", "title": f"Btn {i}"} for i in range(n)]

	def test_valid_with_header_and_footer(self):
		payload, errors = wm.build_reply_buttons_payload(TO, "Pick one", self.btns(), header="Header", footer="Foot")
		self.assertEqual(errors, [])
		inter = payload["interactive"]
		self.assertEqual(inter["type"], "button")
		self.assertEqual(inter["header"], {"type": "text", "text": "Header"})
		self.assertEqual(inter["action"]["buttons"][0], {"type": "reply", "reply": {"id": "id0", "title": "Btn 0"}})
		self.assertEqual(inter["footer"], {"text": "Foot"})

	def test_button_count_boundaries(self):
		self.assertEqual(wm.build_reply_buttons_payload(TO, "b", self.btns(1))[1], [])
		self.assertEqual(wm.build_reply_buttons_payload(TO, "b", self.btns(3))[1], [])
		self.assertIn("too_many", codes(wm.build_reply_buttons_payload(TO, "b", self.btns(4))[1]))
		self.assertEqual(codes(wm.build_reply_buttons_payload(TO, "b", [])[1]), ["required"])
		self.assertEqual(codes(wm.build_reply_buttons_payload(TO, "b", None)[1]), ["required"])

	def test_title_id_body_footer_header_boundaries(self):
		def one(**kw):
			b = {"id": kw.get("id", "i"), "title": kw.get("title", "t")}
			return wm.build_reply_buttons_payload(TO, kw.get("body", "b"), [b], kw.get("header"), kw.get("footer"))[1]

		self.assertEqual(one(title="t" * 20, id="i" * 256, body="b" * 1024, header="h" * 60, footer="f" * 60), [])
		self.assertEqual(codes(one(title="t" * 21)), ["too_long"])
		self.assertEqual(codes(one(id="i" * 257)), ["too_long"])
		self.assertEqual(codes(one(body="b" * 1025)), ["too_long"])
		self.assertEqual(codes(one(header="h" * 61)), ["too_long"])
		self.assertEqual(codes(one(footer="f" * 61)), ["too_long"])
		self.assertEqual(codes(one(body="")), ["required"])
		self.assertEqual(codes(one(title="")), ["required"])
		self.assertEqual(codes(one(id="")), ["required"])

	def test_uniqueness(self):
		self.assertEqual(codes(wm.build_reply_buttons_payload(TO, "b", [{"id": "a", "title": "X"}, {"id": "a", "title": "Y"}])[1]), ["duplicate"])
		self.assertEqual(codes(wm.build_reply_buttons_payload(TO, "b", [{"id": "a", "title": "X"}, {"id": "b", "title": "x"}])[1]), ["duplicate"])

	def test_string_shorthand_and_media_header(self):
		payload, errors = wm.build_reply_buttons_payload(TO, "b", ["Yes", "No"])
		self.assertEqual((errors, payload["interactive"]["action"]["buttons"][1]["reply"]), ([], {"id": "No", "title": "No"}))
		img, errors = wm.build_reply_buttons_payload(TO, "b", ["Yes"], header={"type": "image", "link": "https://a/b.png"})
		self.assertEqual((errors, img["interactive"]["header"]), ([], {"type": "image", "image": {"link": "https://a/b.png"}}))
		by_id, _ = wm.build_reply_buttons_payload(TO, "b", ["Yes"], header={"type": "document", "media_id": "7", "filename": "x.pdf"})
		self.assertEqual(by_id["interactive"]["header"]["document"], {"id": "7", "filename": "x.pdf"})
		self.assertIn("link_or_id", codes(wm.build_reply_buttons_payload(TO, "b", ["Yes"], header={"type": "image"})[1]))
		self.assertIn("invalid_type", codes(wm.build_reply_buttons_payload(TO, "b", ["Yes"], header={"type": "audio", "link": "https://a/b"})[1]))


class TestList(unittest.TestCase):
	def sections(self, sections=1, rows=1):
		return [
			{"title": f"Sec {s}", "rows": [{"id": f"s{s}r{r}", "title": f"Row {r}", "description": "desc"} for r in range(rows)]}
			for s in range(sections)
		]

	def test_valid(self):
		payload, errors = wm.build_list_payload(TO, "Menu", "Open", self.sections(2, 2), header="H", footer="F")
		self.assertEqual(errors, [])
		inter = payload["interactive"]
		self.assertEqual((inter["type"], inter["action"]["button"]), ("list", "Open"))
		self.assertEqual(len(inter["action"]["sections"]), 2)

	def test_row_and_section_count_boundaries(self):
		self.assertEqual(wm.build_list_payload(TO, "b", "o", self.sections(1, 10))[1], [])
		self.assertIn("too_many_rows", codes(wm.build_list_payload(TO, "b", "o", self.sections(1, 11))[1]))
		self.assertEqual(wm.build_list_payload(TO, "b", "o", self.sections(10, 1))[1], [])
		self.assertIn("too_many", codes(wm.build_list_payload(TO, "b", "o", self.sections(11, 1))[1]))
		self.assertIn("too_many_rows", codes(wm.build_list_payload(TO, "b", "o", self.sections(5, 3))[1]))  # 15 rows across sections
		self.assertEqual(codes(wm.build_list_payload(TO, "b", "o", [])[1]), ["required"])

	def test_text_boundaries(self):
		def one(**kw):
			sec = [{"title": kw.get("st", "s"), "rows": [{"id": kw.get("rid", "r"), "title": kw.get("rt", "t"), "description": kw.get("rd", "d")}]}]
			return wm.build_list_payload(TO, kw.get("body", "b"), kw.get("btn", "o"), sec, kw.get("header"), kw.get("footer"))[1]

		self.assertEqual(one(st="s" * 24, rid="i" * 200, rt="t" * 24, rd="d" * 72, body="b" * 4096, btn="o" * 20, header="h" * 60, footer="f" * 60), [])
		for key, value in (("st", "s" * 25), ("rid", "i" * 201), ("rt", "t" * 25), ("rd", "d" * 73), ("body", "b" * 4097), ("btn", "o" * 21), ("header", "h" * 61), ("footer", "f" * 61)):
			self.assertEqual(codes(one(**{key: value})), ["too_long"], key)
		self.assertEqual(codes(one(btn="")), ["required"])
		self.assertEqual(codes(one(rt="")), ["required"])

	def test_section_title_rules_and_duplicates(self):
		single = [{"rows": [{"id": "a", "title": "A"}]}]
		self.assertEqual(wm.build_list_payload(TO, "b", "o", single)[1], [])
		two = [{"rows": [{"id": "a", "title": "A"}]}, {"rows": [{"id": "b", "title": "B"}]}]
		self.assertIn("required", codes(wm.build_list_payload(TO, "b", "o", two)[1]))
		dup = [{"title": "S", "rows": [{"id": "a", "title": "A"}, {"id": "a", "title": "B"}]}]
		self.assertIn("duplicate", codes(wm.build_list_payload(TO, "b", "o", dup)[1]))

	def test_flat_rows_and_header_rules(self):
		payload, errors = wm.build_list_payload(TO, "b", "o", [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}])
		self.assertEqual((errors, len(payload["interactive"]["action"]["sections"][0]["rows"])), ([], 2))
		self.assertIn("text_only", codes(wm.build_list_payload(TO, "b", "o", single_rows(), header={"type": "image", "link": "https://a/b.png"})[1]))


def single_rows():
	return [{"title": "S", "rows": [{"id": "a", "title": "A"}]}]


class TestCtaUrl(unittest.TestCase):
	def test_valid(self):
		payload, errors = wm.build_cta_url_payload(TO, "See dates", "Open", "https://shop.example/x?y=1", header="H", footer="F")
		self.assertEqual(errors, [])
		self.assertEqual(payload["interactive"]["action"], {"name": "cta_url", "parameters": {"display_text": "Open", "url": "https://shop.example/x?y=1"}})

	def test_boundaries(self):
		def one(**kw):
			return wm.build_cta_url_payload(TO, kw.get("body", "b"), kw.get("dt", "go"), kw.get("url", "https://a.example/x"), kw.get("header"), kw.get("footer"))[1]

		self.assertEqual(one(body="b" * 1024, dt="d" * 20, header="h" * 60, footer="f" * 60), [])
		for key, value in (("body", "b" * 1025), ("dt", "d" * 21), ("header", "h" * 61), ("footer", "f" * 61)):
			self.assertEqual(codes(one(**{key: value})), ["too_long"], key)
		self.assertEqual(one(url="https://a.example/" + "x" * (2000 - len("https://a.example/"))), [])
		self.assertEqual(codes(one(url="https://a.example/" + "x" * 2000)), ["too_long"])

	def test_https_only(self):
		for url in ("http://a.example", "ftp://a.example", "javascript:alert(1)", "a.example", "https://", "https://a b.example", ""):
			self.assertTrue(wm.build_cta_url_payload(TO, "b", "go", url)[1], url)
		self.assertEqual(codes(wm.build_cta_url_payload(TO, "b", "", "https://a.example")[1]), ["required"])

	def test_media_header(self):
		payload, errors = wm.build_cta_url_payload(TO, "b", "go", "https://a.example", header={"type": "video", "link": "https://a/b.mp4"})
		self.assertEqual((errors, payload["interactive"]["header"]["type"]), ([], "video"))


class TestLocationRequestAndFlow(unittest.TestCase):
	def test_location_request(self):
		payload, errors = wm.build_location_request_payload(TO, "Where are you?")
		self.assertEqual(errors, [])
		self.assertEqual(payload["interactive"], {"type": "location_request_message", "body": {"text": "Where are you?"}, "action": {"name": "send_location"}})
		self.assertEqual(wm.build_location_request_payload(TO, "b" * 1024)[1], [])
		self.assertEqual(codes(wm.build_location_request_payload(TO, "b" * 1025)[1]), ["too_long"])
		self.assertEqual(codes(wm.build_location_request_payload(TO, "")[1]), ["required"])

	def test_flow_requires_flow_id(self):
		payload, errors = wm.build_flow_payload(TO, "Fill in", flow_cta="Start")
		self.assertIsNone(payload)
		self.assertIn("flow_id_required", codes(errors))
		self.assertIn("flow_id_or_name", codes(wm.build_flow_payload(TO, "b", flow_id="1", flow_name="n", flow_cta="Go")[1]))

	def test_flow_payload_shape_untested(self):
		payload, errors = wm.build_flow_payload(
			TO, "Fill in", flow_id="123", flow_cta="Start", flow_token="tok", screen="HOME", flow_data={"a": 1}, mode="draft"
		)
		self.assertEqual(errors, [])
		params = payload["interactive"]["action"]["parameters"]
		self.assertEqual(params["flow_id"], "123")
		self.assertEqual(params["flow_message_version"], "3")
		self.assertEqual(params["flow_action_payload"], {"screen": "HOME", "data": {"a": 1}})
		self.assertEqual(params["mode"], "draft")
		for kw, code in (({"flow_action": "x"}, "invalid_action"), ({"mode": "live"}, "invalid_mode"), ({"flow_cta": "c" * 21}, "too_long"), ({"flow_cta": ""}, "required")):
			args = {"flow_id": "1", "flow_cta": "Go", **kw}
			self.assertIn(code, codes(wm.build_flow_payload(TO, "b", **args)[1]), kw)


class TestDispatchAndMirror(unittest.TestCase):
	def test_dispatch_every_kind(self):
		specs = {
			"buttons": {"body": "b", "buttons": ["A"]},
			"list": {"body": "b", "button_text": "o", "sections": [{"id": "1", "title": "t"}]},
			"cta_url": {"body": "b", "display_text": "go", "url": "https://a.example"},
			"location_request": {"body": "b"},
			"flow": {"body": "b", "flow_id": "1", "flow_cta": "Go"},
		}
		for kind, spec in specs.items():
			payload, errors = wm.build_interactive_payload(TO, kind, spec, "wamid.Q")
			self.assertEqual(errors, [], kind)
			self.assertEqual(payload["type"], "interactive")
			self.assertEqual(payload["context"], {"message_id": "wamid.Q"})
		self.assertEqual(codes(wm.build_interactive_payload(TO, "carousel", {})[1]), ["invalid_kind"])

	def test_recipient_required(self):
		self.assertIn("required", codes(wm.build_location_payload("", 1, 2)[1]))
		self.assertIn("required", codes(wm.build_reaction_payload(" ", "w", "👍")[1]))

	def test_mirror_summary(self):
		self.assertEqual(wm.mirror_summary(wm.build_media_payload(TO, "image", link="https://a/b", caption="hi")[0]), ("image", "hi"))
		self.assertEqual(wm.mirror_summary(wm.build_sticker_payload(TO, media_id="1")[0]), ("image", "[sticker]"))
		self.assertEqual(wm.mirror_summary(wm.build_media_payload(TO, "audio", media_id="1", voice=True)[0]), ("audio", "[voice note]"))
		self.assertEqual(wm.mirror_summary(wm.build_reaction_payload(TO, "w", "👍")[0]), ("reaction", "👍"))
		self.assertEqual(wm.mirror_summary(wm.build_contacts_payload(TO, [{"name": "Ann"}])[0]), ("contact", "Ann"))
		self.assertEqual(wm.mirror_summary(wm.build_location_payload(TO, 1, 2, "Pin")[0])[0], "location")
		self.assertEqual(wm.mirror_summary(wm.build_cta_url_payload(TO, "Go now", "go", "https://a.example")[0]), ("interactive", "Go now"))


if __name__ == "__main__":
	unittest.main()
