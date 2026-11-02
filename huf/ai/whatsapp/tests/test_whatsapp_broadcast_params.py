# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Header / button parameters: location headers, per-recipient CSV columns, validation, merge."""

from __future__ import annotations

import unittest

from huf.ai.whatsapp.broadcast import params as bp
from huf.ai.whatsapp.broadcast import recipients as br
from huf.ai.whatsapp.broadcast import send as bs

LOC = {"type": "location", "latitude": 12.97, "longitude": 77.59, "name": "HQ", "address": "MG Road"}


class TestValidation(unittest.TestCase):
	def test_location_ranges(self):
		self.assertIsNone(bp.header_error([LOC]))
		self.assertIn("latitude", bp.header_error([{**LOC, "latitude": 91}]))
		self.assertIn("longitude", bp.header_error([{**LOC, "longitude": "x"}]))
		self.assertIn("latitude", bp.header_error([{**LOC, "latitude": float("nan")}]))
		self.assertIn("1000", bp.header_error([{**LOC, "name": "n" * 1001}]))

	def test_media_link_must_be_https(self):
		self.assertIsNone(bp.header_error(["https://x.test/a.png"]))
		self.assertIn("https", bp.header_error(["http://x.test/a.png"]))
		self.assertIn("https", bp.header_error([{"type": "image", "link": "http://x.test/a.png"}]))

	def test_buttons(self):
		self.assertIsNone(bp.button_error([{"index": 0, "sub_type": "url", "text": "a/b?c=1"}, {"index": 1, "sub_type": "copy_code", "code": "SAVE10"}]))
		self.assertIn("scheme", bp.button_error([{"index": 0, "sub_type": "url", "text": "https://evil"}]))
		self.assertIn("copy code", bp.button_error([{"index": 1, "sub_type": "copy_code", "code": "has space"}]))
		self.assertIn("copy code", bp.button_error([{"index": 1, "sub_type": "copy_code", "code": "X" * 16}]))


class TestCsv(unittest.TestCase):
	def test_named_columns_become_header_and_button_params(self):
		rows = br.parse_csv("phone,name,header,button_url_0,button_code_1\n15550001,Ada,https://x.test/a.png,summer,SAVE10\n15550002,Bob,,,\n")
		self.assertEqual(rows[0]["params"], {
			"body": ["Ada"], "header": ["https://x.test/a.png"],
			"button": [{"index": 0, "sub_type": "url", "text": "summer"}, {"index": 1, "sub_type": "copy_code", "code": "SAVE10"}],
		})
		self.assertEqual(rows[1]["params"], {"body": ["Bob"]})  # empty cells use the broadcast defaults

	def test_location_columns(self):
		rows = br.parse_csv("phone,header_lat,header_lng,header_name\n15550001,12.9,77.5,Shop\n")
		self.assertEqual(rows[0]["params"]["header"], [{"type": "location", "latitude": "12.9", "longitude": "77.5", "name": "Shop"}])
		self.assertIsNone(bp.params_error(rows[0]["params"]))

	def test_plain_columns_stay_body(self):
		self.assertEqual(br.parse_csv("phone,first_name,city\n15550001,Ada,Paris\n")[0]["params"], {"body": ["Ada", "Paris"]})

	def test_bad_cells_are_flagged_by_params_error(self):
		p = br.parse_csv("phone,header_lat,header_lng\n15550001,120,10\n")[0]["params"]
		self.assertIn("latitude", bp.params_error(p))


class TestMerge(unittest.TestCase):
	def test_button_values_merge_by_index(self):
		default = [{"index": 0, "sub_type": "url", "text": "d"}, {"index": 1, "sub_type": "copy_code", "code": "DEF"}]
		mine = [{"index": 1, "sub_type": "copy_code", "code": "MINE"}]
		self.assertEqual(bp.merge_buttons(default, mine), [default[0], mine[0]])

	def test_send_merge_uses_recipient_header_and_buttons(self):
		bc = {"header_params": '["https://d.test/a.png"]', "button_params": '[{"index":0,"sub_type":"url","text":"d"}]', "body_params": None}
		row = {"params": '{"header": ["https://m.test/b.png"], "button": [{"index": 0, "sub_type": "url", "text": "m"}]}'}
		body, header, button = bs._merge_params(bc, row)
		self.assertEqual((body, header, button), (None, ["https://m.test/b.png"], [{"index": 0, "sub_type": "url", "text": "m"}]))
		body, header, button = bs._merge_params(bc, {"params": None})
		self.assertEqual(header, ["https://d.test/a.png"])


if __name__ == "__main__":
	unittest.main()
