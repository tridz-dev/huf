# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure unit tests for rich-template validation and outbound payload builders."""

import unittest

from huf.ai.gateway_adapters import whatsapp_templates as wt


def _codes(errors):
	return {(e["field"], e["code"]) for e in errors}


class TestTemplateSpec(unittest.TestCase):
	def base(self, **extra):
		return {"template": "Hi {{1}}", "sample_values": "Ann", **extra}

	def test_minimal_valid(self):
		spec, errors = wt.validate_template_spec(self.base())
		self.assertEqual(errors, [])
		self.assertEqual(spec["sample_values"], ["Ann"])
		self.assertEqual(spec["header_type"], "")

	def test_legacy_flat_header_is_text(self):
		spec, errors = wt.validate_template_spec(self.base(header="Welcome"))
		self.assertEqual((errors, spec["header_type"], spec["header_text"]), ([], "TEXT", "Welcome"))

	def test_limits(self):
		_, errors = wt.validate_template_spec({"template": "x" * 1025})
		self.assertIn(("body", "too_long"), _codes(errors))
		_, errors = wt.validate_template_spec(self.base(header="h" * 61, footer="f" * 61))
		self.assertTrue({("header", "too_long"), ("footer", "too_long")} <= _codes(errors))
		_, errors = wt.validate_template_spec(self.base(buttons=[{"type": "QUICK_REPLY", "text": "t" * 26}]))
		self.assertIn(("buttons[0].text", "too_long"), _codes(errors))

	def test_header_variable_needs_single_sample(self):
		_, errors = wt.validate_template_spec(self.base(header="Order {{1}}"))
		self.assertIn(("sample", "required"), _codes(errors))
		_, errors = wt.validate_template_spec(self.base(header="Order {{1}}", sample="A-1"))
		self.assertEqual(errors, [])
		_, errors = wt.validate_template_spec(self.base(header="{{1}} {{2}}", sample="x"))
		self.assertIn(("header", "too_many_variables"), _codes(errors))

	def test_media_header_and_video(self):
		spec, errors = wt.validate_template_spec(self.base(header_type="IMAGE", sample="https://cdn.example/a.png"))
		self.assertEqual((errors, spec["header_type"]), ([], "IMAGE"))
		_, errors = wt.validate_template_spec(self.base(header_type="DOCUMENT"))
		self.assertIn(("sample", "required"), _codes(errors))
		_, errors = wt.validate_template_spec(self.base(header_type="VIDEO", sample="https://cdn.example/a.mp4"))
		self.assertIn(("header_type", "unsupported_header_type"), _codes(errors))

	def test_buttons(self):
		buttons = [
			{"type": "URL", "text": "Track", "url": "https://x.example/t/{{1}}", "example": "https://x.example/t/9"},
			{"type": "PHONE_NUMBER", "text": "Call", "phone_number": "+1 (555) 000-1234"},
		]
		spec, errors = wt.validate_template_spec(self.base(buttons=buttons))
		self.assertEqual(errors, [])
		rows = wt.button_rows(spec)
		self.assertEqual(rows[0], {"button_type": "Visit Website", "button_label": "Track", "sequence": 1, "website_url": "https://x.example/t/{{1}}", "url_type": "Dynamic", "example_url": "https://x.example/t/9"})
		self.assertEqual(rows[1]["phone_number"], "+15550001234")
		self.assertEqual(rows[1]["button_type"], "Call Phone")

	def test_button_counts_and_grouping(self):
		qr = lambda n: [{"type": "QUICK_REPLY", "text": f"q{i}"} for i in range(n)]  # noqa: E731
		self.assertEqual(wt.validate_template_spec(self.base(buttons=qr(3)))[1], [])
		self.assertIn(("buttons", "too_many_quick_replies"), _codes(wt.validate_template_spec(self.base(buttons=qr(4)))[1]))
		cta = [{"type": "URL", "text": f"u{i}", "url": f"https://x{i}.example"} for i in range(3)]
		self.assertIn(("buttons", "too_many_cta_buttons"), _codes(wt.validate_template_spec(self.base(buttons=cta))[1]))
		mixed = [qr(1)[0], cta[0], qr(2)[1]]
		self.assertIn(("buttons", "buttons_not_grouped"), _codes(wt.validate_template_spec(self.base(buttons=mixed))[1]))
		bad_url = [{"type": "URL", "text": "u", "url": "https://x.example/{{1}}/y", "example": "https://x.example/1/y"}]
		self.assertIn(("buttons[0].url", "bad_placeholder"), _codes(wt.validate_template_spec(self.base(buttons=bad_url))[1]))
		no_example = [{"type": "URL", "text": "u", "url": "https://x.example/{{1}}"}]
		self.assertIn(("buttons[0].example", "required"), _codes(wt.validate_template_spec(self.base(buttons=no_example))[1]))


class TestSendBuilders(unittest.TestCase):
	def test_param_text_rules(self):
		errors = []
		wt.validate_param_text("p", "ok", errors)
		self.assertEqual(errors, [])
		for bad in ("", "a\nb", "a\tb", "a    b"):
			errors = []
			wt.validate_param_text("p", bad, errors)
			self.assertTrue(errors, repr(bad))

	def test_components(self):
		headers, e1 = wt.normalize_header_params([{"type": "document", "link": "https://x.example/a.pdf", "filename": "a.pdf"}])
		buttons, e2 = wt.normalize_button_params(["A-1", {"index": 1, "sub_type": "quick_reply", "payload": "YES"}])
		self.assertEqual((e1, e2), ([], []))
		comps = wt.build_template_components(["Ann"], headers, buttons)
		self.assertEqual(comps[0], {"type": "header", "parameters": [{"type": "document", "document": {"link": "https://x.example/a.pdf", "filename": "a.pdf"}}]})
		self.assertEqual(comps[2], {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": "A-1"}]})
		self.assertEqual(comps[3]["parameters"], [{"type": "payload", "payload": "YES"}])

	def test_header_param_errors(self):
		self.assertTrue(wt.normalize_header_params(["a", "b"])[1])
		self.assertTrue(wt.normalize_header_params([{"type": "image", "link": "notaurl"}])[1])
		self.assertTrue(wt.normalize_button_params([{"index": 12, "text": "x"}])[1])

	def test_media_payloads(self):
		media, errors = wt.validate_media_request("Document", "https://x.example/a.pdf", None, "cap", "a.pdf")
		self.assertEqual(errors, [])
		self.assertEqual(
			wt.build_media_payload("1555", media, "wamid.1"),
			{"messaging_product": "whatsapp", "recipient_type": "individual", "to": "1555", "type": "document",
			 "document": {"link": "https://x.example/a.pdf", "caption": "cap", "filename": "a.pdf"}, "context": {"message_id": "wamid.1"}},
		)
		self.assertTrue(wt.validate_media_request("image", "", "", "", "")[1])  # neither link nor id
		self.assertTrue(wt.validate_media_request("image", "https://x.example/a.png", "ID", "", "")[1])  # both
		self.assertTrue(wt.validate_media_request("audio", "https://x.example/a.mp3", "", "caption", "")[1])
		self.assertTrue(wt.validate_media_request("sticker", "https://x.example/a.webp", "", "", "")[1])
		media, _ = wt.validate_media_request("image", "", "MID1", "", "")
		self.assertEqual(wt.build_media_payload("1555", media)["image"], {"id": "MID1"})
