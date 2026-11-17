# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Carousel template send components and validation (pure Python, no frappe)."""

import unittest

from huf.ai.gateway_adapters import whatsapp_templates as wt

IMG = "https://cdn.example/a.png"


def _card():
	return {"components": [
		{"type": "HEADER", "format": "IMAGE"},
		{"type": "BODY", "text": "Deal {{1}}"},
		{"type": "BUTTONS", "buttons": [
			{"type": "QUICK_REPLY", "text": "Hi"},
			{"type": "URL", "text": "Go", "url": "https://x.example/{{1}}"},
		]},
	]}


COMPS = [
	{"type": "BODY", "text": "Hi {{1}}"},
	{"type": "CAROUSEL", "cards": [_card(), _card()]},
]


def _good(n=2):
	return [
		{"header": {"link": IMG}, "body": [f"d{i}"], "buttons": [
			{"index": 0, "sub_type": "quick_reply", "text": f"p{i}"}, {"index": 1, "sub_type": "url", "text": f"s{i}"},
		]}
		for i in range(n)
	]


def _codes(carousel, comps=COMPS):
	_, errors = wt.build_send_components(comps, ["Ann"], None, None, carousel)
	return {e["code"] for e in errors}


class CarouselSendTest(unittest.TestCase):
	def test_payload(self):
		comps, errors = wt.build_send_components(COMPS, ["Ann"], None, None, _good())
		self.assertEqual(errors, [])
		self.assertEqual(comps[0]["type"], "body")
		car = comps[-1]
		self.assertEqual(car["type"], "carousel")
		c1 = car["cards"][1]
		self.assertEqual(c1["card_index"], 1)
		self.assertEqual(c1["components"][0], {"type": "header", "parameters": [{"type": "image", "image": {"link": IMG}}]})
		self.assertEqual(c1["components"][1]["parameters"][0]["text"], "d1")
		self.assertEqual(c1["components"][2]["sub_type"], "quick_reply")
		self.assertEqual(c1["components"][3]["parameters"][0], {"type": "text", "text": "s1"})

	def test_media_id(self):
		g = _good()
		g[0]["header"] = {"id": "123"}
		comps, errors = wt.build_send_components(COMPS, ["Ann"], None, None, g)
		self.assertEqual(errors, [])
		self.assertEqual(comps[-1]["cards"][0]["components"][0]["parameters"][0]["image"], {"id": "123"})

	def test_errors(self):
		self.assertIn("carousel_required", _codes(None))
		self.assertIn("carousel_card_count", _codes(_good(3)))
		self.assertIn("carousel_card_count", _codes(_good(1)))
		g = _good()
		g[1]["header"] = None
		self.assertIn("card_header_required", _codes(g))
		g = _good()
		g[0]["header"] = {"type": "video", "link": IMG}
		self.assertIn("card_header_invalid", _codes(g))
		g = _good()
		g[0]["body"] = []
		self.assertIn("card_body_count_mismatch", _codes(g))
		g = _good()
		g[0]["buttons"] = g[0]["buttons"][:1]
		self.assertIn("card_button_required", _codes(g))
		g = _good()
		g[0]["buttons"][0]["sub_type"] = "url"
		self.assertIn("card_button_unexpected", _codes(g))

	def test_count_range_and_non_carousel(self):
		self.assertIn("carousel_card_count", _codes(_good(11), [{"type": "CAROUSEL", "cards": [_card()] * 11}]))
		self.assertIn("carousel_not_expected", _codes(_good(), [{"type": "BODY", "text": "Hi {{1}}"}]))

	def test_view_and_cards(self):
		self.assertEqual(len(wt.components_to_view(COMPS)["carousel"]), 2)
		self.assertEqual(wt.carousel_cards(COMPS)[0]["header_type"], "IMAGE")
		self.assertIsNone(wt.carousel_cards([{"type": "BODY", "text": "x"}]))


class CarouselBroadcastParamsTest(unittest.TestCase):
	def test_params_error(self):
		from huf.ai.whatsapp.broadcast import params as bp

		self.assertIsNone(bp.params_error({"carousel": _good()}))
		self.assertIn("2 to 10", bp.params_error({"carousel": _good(1)}))
		bad = _good()
		bad[0]["header"] = {"link": "http://x/a.png"}
		self.assertIn("https", bp.params_error({"carousel": bad}))
		bad = _good()
		bad[1]["header"] = None
		self.assertIn("card 1", bp.params_error({"carousel": bad}))


if __name__ == "__main__":
	unittest.main()
