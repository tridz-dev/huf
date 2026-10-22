# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Table-driven pass/fail cases for every template rule (pure Python, no frappe)."""

import unittest

from huf.ai.gateway_adapters import whatsapp_templates as wt

IMG = "https://cdn.example/a.png"
URLB = {"type": "URL", "text": "Go", "url": "https://x.example/{{1}}", "example": "https://x.example/9"}


def _spec(**extra):
	base = {"body": "Hi {{1}}, welcome", "sample_values": ["Ann"]}
	base.update(extra)
	return base


def _named(**extra):
	base = {"body": "Hi {{first_name}}, welcome", "named_samples": [{"name": "first_name", "example": "Ann"}]}
	base.update(extra)
	return base


def _qr(n):
	return [{"type": "QUICK_REPLY", "text": f"q{i}"} for i in range(n)]


def _urls(n):
	return [{"type": "URL", "text": f"u{i}", "url": f"https://x{i}.example"} for i in range(n)]


# (label, payload, expected (field, code) or None for valid)
CASES = [
	# body
	("body ok", _spec(), None),
	("body required", {"body": ""}, ("body", "required")),
	("body max 1024 ok", {"body": "x" * 1024}, None),
	("body over 1024", {"body": "x" * 1025}, ("body", "too_long")),
	("body starts with var", _spec(body="{{1}} hello"), ("body", "body_starts_with_variable")),
	("body ends with var", _spec(body="hello {{1}}"), ("body", "body_ends_with_variable")),
	("positional gap", _spec(body="a {{1}} b {{3}} c", sample_values=["x", "y"]), ("body", "placeholder_sequence")),
	("bad braces", _spec(body="a {{ b"), ("body", "bad_placeholder")),
	# samples
	("sample missing count", _spec(sample_values=[]), ("sample_values", "sample_count")),
	("sample empty", _spec(sample_values=[""]), ("sample_values", "sample_empty")),
	("sample comma list", _spec(sample_values=["a,b"]), ("sample_values", "sample_comma")),
	("sample phone", _spec(sample_values=["+1 555 123 4567"]), ("sample_values[0]", "sample_looks_like_personal_data")),
	("sample phone plain digits", _spec(sample_values=["5551234"]), ("sample_values[0]", "sample_looks_like_personal_data")),
	("sample short number ok", _spec(sample_values=["123456"]), None),
	("sample email", _spec(sample_values=["a@b.co"]), ("sample_values[0]", "sample_looks_like_personal_data")),
	# named
	("named ok", _named(), None),
	("named bad name upper", _named(body="Hi {{First}}, x"), ("body", "invalid_variable_name")),
	("named bad name digit start", _named(body="Hi {{1st}}, x"), ("body", "invalid_variable_name")),
	("named mixed", _named(body="Hi {{first_name}} {{1}} x"), ("body", "mixed_parameter_format")),
	("named sample missing", _named(named_samples=[]), ("named_samples.first_name", "sample_missing")),
	("named sample unknown", _named(named_samples={"first_name": "A", "zzz": "B"}), ("named_samples.zzz", "sample_unknown_variable")),
	("named sample empty", _named(named_samples={"first_name": ""}), ("named_samples.first_name", "sample_empty")),
	("named sample dict ok", _named(named_samples={"first_name": "Ann"}), None),
	("named sample email", _named(named_samples={"first_name": "a@b.co"}), ("named_samples.first_name", "sample_looks_like_personal_data")),
	("declared named w/ positional", _spec(parameter_format="NAMED"), ("parameter_format", "parameter_format_mismatch")),
	("declared positional w/ named", _named(parameter_format="POSITIONAL"), ("parameter_format", "parameter_format_mismatch")),
	("bad parameter_format", _spec(parameter_format="X"), ("parameter_format", "invalid_parameter_format")),
	# header
	("header text ok", _spec(header="Hello"), None),
	("header 60 ok", _spec(header="h" * 60), None),
	("header 61", _spec(header="h" * 61), ("header", "too_long")),
	("header var needs sample", _spec(header="Order {{1}}"), ("sample", "required")),
	("header var ok", _spec(header="Order {{1}}", sample="A-1"), None),
	("header 2 vars", _spec(header="{{1}} {{2}}", sample="x"), ("header", "too_many_variables")),
	("header named ok", _named(header="Hi {{first_name}}", sample="Ann"), None),
	("header image ok", _spec(header_type="IMAGE", sample=IMG), None),
	("header image no sample", _spec(header_type="IMAGE"), ("sample", "required")),
	("header image handle ok", _spec(header_type="IMAGE", header_handle="4::abc"), None),
	("header video ok", _spec(header_type="VIDEO", sample="https://cdn.example/a.mp4"), None),
	("header video no sample", _spec(header_type="VIDEO"), ("sample", "required")),
	("header video w/ text", {**_spec(header_type="VIDEO", sample=IMG), "header": {"type": "VIDEO", "text": "x"}}, ("header", "not_allowed")),
	("header media bad sample", _spec(header_type="DOCUMENT", sample="nope"), ("sample", "invalid_sample")),
	("header location ok", _spec(header_type="LOCATION"), None),
	("header location w/ text", {**_spec(), "header": {"type": "LOCATION", "text": "x"}}, ("header", "not_allowed")),
	("header bad type", _spec(header_type="GIF"), ("header_type", "unsupported_header_type")),
	# footer
	("footer 60 ok", _spec(footer="f" * 60), None),
	("footer 61", _spec(footer="f" * 61), ("footer", "too_long")),
	("footer var", _spec(footer="hi {{1}}"), ("footer", "no_variables")),
	# buttons
	("qr 10 ok", _spec(buttons=_qr(10)), None),
	("buttons 11", _spec(buttons=_qr(11)), ("buttons", "too_many_buttons")),
	("btn text 25 ok", _spec(buttons=[{"type": "QUICK_REPLY", "text": "t" * 25}]), None),
	("btn text 26", _spec(buttons=[{"type": "QUICK_REPLY", "text": "t" * 26}]), ("buttons[0].text", "too_long")),
	("url 2 ok", _spec(buttons=_urls(2)), None),
	("url 3", _spec(buttons=_urls(3)), ("buttons", "too_many_url_buttons")),
	("phone 2", _spec(buttons=[{"type": "PHONE_NUMBER", "text": "c", "phone_number": "+15550001234"}] * 2), ("buttons", "too_many_phone_buttons")),
	("phone invalid", _spec(buttons=[{"type": "PHONE_NUMBER", "text": "c", "phone_number": "12"}]), ("buttons[0].phone_number", "invalid_phone")),
	("phone > 20", _spec(buttons=[{"type": "PHONE_NUMBER", "text": "c", "phone_number": "+" + "1" * 20}]), ("buttons[0].phone_number", "invalid_phone")),
	("copy code ok", _spec(buttons=[{"type": "COPY_CODE", "example": "SAVE20"}]), None),
	("copy code 20 ok", _spec(buttons=[{"type": "COPY_CODE", "example": "A" * 20}]), None),
	("copy code 21", _spec(buttons=[{"type": "COPY_CODE", "example": "A" * 21}]), ("buttons[0].example", "too_long")),
	("copy code no example", _spec(buttons=[{"type": "COPY_CODE"}]), ("buttons[0].example", "required")),
	("copy code 2", _spec(buttons=[{"type": "COPY_CODE", "example": "A"}] * 2), ("buttons", "too_many_copy_code_buttons")),
	("grouped ok", _spec(buttons=_qr(2) + _urls(1)), None),
	("not grouped", _spec(buttons=[_qr(1)[0], _urls(1)[0], _qr(2)[1]]), ("buttons", "buttons_not_grouped")),
	("url dynamic ok", _spec(buttons=[URLB]), None),
	("url dynamic named ok", _spec(buttons=[{**URLB, "url": "https://x.example/{{code}}"}]), None),
	("url var not at end", _spec(buttons=[{**URLB, "url": "https://x.example/{{1}}/y", "example": "https://x.example/1/y"}]), ("buttons[0].url", "bad_placeholder")),
	("url two vars", _spec(buttons=[{**URLB, "url": "https://x.example/{{1}}{{2}}"}]), ("buttons[0].url", "bad_placeholder")),
	("url no example", _spec(buttons=[{k: v for k, v in URLB.items() if k != "example"}]), ("buttons[0].example", "required")),
	("url bad example", _spec(buttons=[{**URLB, "example": "https://y.example/9"}]), ("buttons[0].example", "invalid_example")),
	("url not http", _spec(buttons=[{"type": "URL", "text": "u", "url": "ftp://x"}]), ("buttons[0].url", "invalid_url")),
	("url > 2000", _spec(buttons=[{"type": "URL", "text": "u", "url": "https://x.example/" + "a" * 2000}]), ("buttons[0].url", "too_long")),
	("button bad type", _spec(buttons=[{"type": "FLOW", "text": "x"}]), ("buttons[0].type", "invalid_type")),
	# category / ttl
	("category utility", _spec(category="UTILITY"), None),
	("category marketing", _spec(category="MARKETING"), None),
	("category authentication", _spec(category="AUTHENTICATION"), ("category", "category_not_supported")),
	("category junk", _spec(category="FOO"), ("category", "invalid_category")),
	("ttl ok", _spec(category="UTILITY", ttl_seconds=30), None),
	("ttl max ok", _spec(category="UTILITY", ttl_seconds=43200), None),
	("ttl -1 ok", _spec(category="UTILITY", ttl_seconds=-1), None),
	("ttl low", _spec(category="UTILITY", ttl_seconds=29), ("ttl_seconds", "ttl_out_of_range")),
	("ttl high", _spec(category="UTILITY", ttl_seconds=43201), ("ttl_seconds", "ttl_out_of_range")),
	("ttl marketing", _spec(category="MARKETING", ttl_seconds=60), ("ttl_seconds", "ttl_not_allowed")),
	("ttl no category", _spec(ttl_seconds=60), ("ttl_seconds", "ttl_not_allowed")),
	("ttl not int", _spec(category="UTILITY", ttl_seconds="60"), ("ttl_seconds", "invalid_ttl")),
]


class TestTemplateRules(unittest.TestCase):
	def test_table(self):
		for label, payload, expected in CASES:
			with self.subTest(label):
				_, errors = wt.validate_template_spec(payload)
				codes = {(e["field"], e["code"]) for e in errors}
				if expected is None:
					self.assertEqual(errors, [])
				else:
					self.assertIn(expected, codes)
				for e in errors:
					self.assertEqual(set(e), {"field", "code", "message"})

	def test_every_rule_code_is_exercised(self):
		wanted = {
			"too_long", "required", "body_starts_with_variable", "body_ends_with_variable", "mixed_parameter_format",
			"invalid_variable_name", "sample_missing", "sample_looks_like_personal_data", "category_not_supported",
			"ttl_out_of_range", "ttl_not_allowed", "too_many_url_buttons", "too_many_copy_code_buttons",
			"too_many_phone_buttons", "buttons_not_grouped", "too_many_buttons", "parameter_format_mismatch",
		}
		seen = {exp[1] for _, _, exp in CASES if exp}
		self.assertFalse(wanted - seen)

	def test_parameter_format_inferred(self):
		self.assertEqual(wt.validate_template_spec(_spec())[0]["parameter_format"], "POSITIONAL")
		self.assertEqual(wt.validate_template_spec(_named())[0]["parameter_format"], "NAMED")


class TestMetaPayload(unittest.TestCase):
	def test_positional(self):
		spec, errors = wt.validate_template_spec(_spec(header="Order {{1}}", sample="A-1", footer="f", buttons=[URLB]))
		self.assertEqual(errors, [])
		payload = wt.build_meta_payload(spec)
		self.assertEqual(payload["parameter_format"], "POSITIONAL")
		self.assertNotIn("message_send_ttl_seconds", payload)
		self.assertEqual(payload["components"], [
			{"type": "HEADER", "format": "TEXT", "text": "Order {{1}}", "example": {"header_text": ["A-1"]}},
			{"type": "BODY", "text": "Hi {{1}}, welcome", "example": {"body_text": [["Ann"]]}},
			{"type": "FOOTER", "text": "f"},
			{"type": "BUTTONS", "buttons": [{"type": "URL", "text": "Go", "url": "https://x.example/{{1}}", "example": ["https://x.example/9"]}]},
		])
		self.assertEqual(wt.build_meta_components(spec), payload["components"])

	def test_named_with_ttl(self):
		spec, errors = wt.validate_template_spec(
			_named(header="Hi {{first_name}}", sample="Ann", category="UTILITY", ttl_seconds=600)
		)
		self.assertEqual(errors, [])
		payload = wt.build_meta_payload(spec)
		self.assertEqual((payload["parameter_format"], payload["message_send_ttl_seconds"]), ("NAMED", 600))
		header, body = payload["components"]
		self.assertEqual(header["example"], {"header_text_named_params": [{"param_name": "first_name", "example": "Ann"}]})
		self.assertEqual(body["example"], {"body_text_named_params": [{"param_name": "first_name", "example": "Ann"}]})

	def test_media_location_copy_code(self):
		spec, _ = wt.validate_template_spec(_spec(header_type="VIDEO", header_handle="4::h", buttons=[{"type": "COPY_CODE", "example": "SAVE20"}]))
		comps = wt.build_meta_components(spec)
		self.assertEqual(comps[0], {"type": "HEADER", "format": "VIDEO", "example": {"header_handle": ["4::h"]}})
		self.assertEqual(comps[-1], {"type": "BUTTONS", "buttons": [{"type": "COPY_CODE", "example": "SAVE20"}]})
		spec, _ = wt.validate_template_spec(_spec(header_type="LOCATION"))
		self.assertEqual(wt.build_meta_components(spec)[0], {"type": "HEADER", "format": "LOCATION"})
		reuse = {"type": "HEADER", "format": "IMAGE", "example": {"header_handle": ["x"]}}
		spec, _ = wt.validate_template_spec(_spec(header_type="IMAGE", sample=IMG))
		self.assertEqual(wt.build_meta_components(spec, reuse)[0], reuse)


class TestSendComponents(unittest.TestCase):
	def test_named(self):
		spec, _ = wt.validate_template_spec(_named(header="Hi {{first_name}}", sample="Ann"))
		comps, errors = wt.build_send_components(spec, {"first_name": "Bob"}, ["Bob"], [])
		self.assertEqual(errors, [])
		self.assertEqual(comps[0], {"type": "header", "parameters": [{"type": "text", "parameter_name": "first_name", "text": "Bob"}]})
		self.assertEqual(comps[1], {"type": "body", "parameters": [{"type": "text", "parameter_name": "first_name", "text": "Bob"}]})

	def test_named_from_meta_components_and_errors(self):
		comps_in = [{"type": "BODY", "text": "Hi {{a}} and {{b}} ok"}]
		comps, errors = wt.build_send_components(comps_in, [{"name": "a", "value": "1"}, {"name": "b", "value": "2"}])
		self.assertEqual(errors, [])
		self.assertEqual([p["parameter_name"] for p in comps[0]["parameters"]], ["a", "b"])
		self.assertEqual(comps[0]["parameters"][1]["text"], "2")
		_, errors = wt.build_send_components(comps_in, {"a": "1", "zz": "3"})
		self.assertEqual({e["code"] for e in errors}, {"param_unknown", "param_missing"})
		_, errors = wt.build_send_components(comps_in, ["only one"])
		self.assertEqual(errors[0]["code"], "param_count_mismatch")

	def test_positional_and_buttons_and_location(self):
		spec, _ = wt.validate_template_spec(_spec(header_type="LOCATION"))
		loc = {"type": "location", "latitude": 1.5, "longitude": 2.5, "name": "HQ", "address": "Main St"}
		comps, errors = wt.build_send_components(spec, ["Ann"], [loc], ["A-1"])
		self.assertEqual(errors, [])
		self.assertEqual(comps[0]["parameters"][0], {"type": "location", "location": {"latitude": 1.5, "longitude": 2.5, "name": "HQ", "address": "Main St"}})
		self.assertEqual(comps[1], {"type": "body", "parameters": [{"type": "text", "text": "Ann"}]})
		self.assertEqual(comps[2]["sub_type"], "url")
		self.assertNotIn("parameter_name", comps[1]["parameters"][0])
