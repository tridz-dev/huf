# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Broadcast template-parameter requirements and the preview's missing/extra-value checks."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_template_guard as guard
from huf.ai.whatsapp.broadcast import limits as bl
from huf.ai.whatsapp.broadcast import api_read as mgmt

NAMED_TPL = {
	"template": "Hi {{first_name}}, welcome!", "header_type": "", "header": "", "sample": "",
	"whatsapp_account": "ACC", "status": "APPROVED", "category": "MARKETING",
	"buttons": [], "parameter_format": "NAMED", "header_format": "",
}
POS_TPL = dict(NAMED_TPL, template="Hi {{1}}, order {{2}}", parameter_format="POSITIONAL")
EXTRA = {"named_samples": [{"name": "first_name", "example": "Sam"}], "components_json": []}


def _req(tpl, extra=EXTRA):
	with patch.object(bridge, "_template_row", return_value=dict(tpl)), patch.object(guard, "get_extra", return_value=extra):
		return bl.template_requirements("welcome_huf-en")


class TestRequirements(unittest.TestCase):
	def test_named_body(self):
		req = _req(NAMED_TPL)
		self.assertEqual(req["parameter_format"], "NAMED")
		self.assertEqual(req["body"], [{"name": "first_name", "sample": "Sam"}])
		self.assertIsNone(req["header"])

	def test_positional_body_with_samples_from_components(self):
		extra = {"components_json": [{"type": "BODY", "example": {"body_text": [["Ann", "A1"]]}}]}
		req = _req(POS_TPL, extra)
		self.assertEqual(req["parameter_format"], "POSITIONAL")
		self.assertEqual(req["body"], [{"index": 1, "sample": "Ann"}, {"index": 2, "sample": "A1"}])

	def test_media_header_and_buttons(self):
		tpl = dict(NAMED_TPL, template="Hi", header_type="IMAGE", parameter_format="",
			buttons=[{"button_type": "Visit Website", "url_type": "Dynamic", "button_label": "Go"},
				{"button_type": "Quick Reply", "url_type": None, "button_label": "Stop"}])
		req = _req(tpl, {})
		self.assertEqual(req["header"], {"type": "IMAGE", "required": True})
		self.assertEqual([b["sub_type"] for b in req["buttons"]], ["url", "quick_reply"])
		self.assertTrue(req["buttons"][0]["required"])

	def test_missing_template_is_none(self):
		with patch.object(bridge, "_template_row", return_value=None):
			self.assertIsNone(bl.template_requirements("nope"))


class TestSendProblems(unittest.TestCase):
	def setUp(self):
		self.named = _req(NAMED_TPL)
		self.pos = _req(POS_TPL)

	def test_named_none_missing(self):
		self.assertEqual(bl.send_problems(self.named, None, None, None)["missing"], ["first_name"])

	def test_named_ok(self):
		out = bl.send_problems(self.named, {"first_name": "A"}, None, None)
		self.assertEqual(out, {"missing": [], "extra": [], "invalid": []})

	def test_named_unknown_is_extra(self):
		out = bl.send_problems(self.named, {"first_name": "A", "zzz": "1"}, None, None)
		self.assertEqual(out["extra"], ["zzz"])

	def test_positional_partial_missing_and_extra(self):
		self.assertEqual(bl.send_problems(self.pos, ["A"], None, None)["missing"], ["2"])
		self.assertTrue(bl.send_problems(self.pos, ["A", "B", "C"], None, None)["extra"])


class TestMergeAndPreview(unittest.TestCase):
	BC = {"gateway": "GW", "template": "t", "consent_attested": 1, "body_params": None, "header_params": None, "button_params": None}

	def _run(self, bc, rows, tpl=NAMED_TPL):
		blocking = []
		with patch.object(bridge, "_template_row", return_value=dict(tpl)), patch.object(guard, "get_extra", return_value=EXTRA), \
			patch.object(bl, "_queued_params", return_value=rows):
			bl._check_params(bc, "B", blocking)
		return [b["message"] for b in blocking], []

	def test_no_params_anywhere_blocks_with_count(self):
		blocking, _ = self._run(dict(self.BC), [(None, 3)])
		self.assertEqual(blocking, ["3 recipients are missing values for template variables: first_name"])

	def test_broadcast_default_satisfies(self):
		blocking, _ = self._run(dict(self.BC, body_params=json.dumps({"first_name": "Friend"})), [(None, 3)])
		self.assertEqual(blocking, [])

	def test_recipient_overrides_and_mixed(self):
		rows = [(json.dumps({"body": {"first_name": "Zed"}}), 2), (None, 1)]
		blocking, _ = self._run(dict(self.BC), rows)
		self.assertEqual(blocking, ["1 recipients are missing values for template variables: first_name"])

	def test_csv_style_list_params_satisfy_positional(self):
		blocking, _ = self._run(dict(self.BC), [(json.dumps({"body": ["Ann", "A1"]}), 4)], tpl=POS_TPL)
		self.assertEqual(blocking, [])

	def test_extra_values_block(self):
		blocking, _ = self._run(dict(self.BC, body_params=json.dumps({"first_name": "x", "extra": "y"})), [(None, 2)])
		self.assertTrue(any("do not use" in b or "does not use" in b for b in blocking))


class TestEndpoint(unittest.TestCase):
	def test_shape(self):
		req = _req(NAMED_TPL)
		with patch.object(mgmt, "_gateway_read_allowed", return_value=True), \
			patch.object(mgmt, "_gateway_whatsapp_account", return_value="ACC"), \
			patch.object(frappe.db, "exists", return_value=True), \
			patch.object(bridge, "_template_docname", return_value="welcome_huf-en"), \
			patch.object(bl, "template_requirements", return_value=req):
			out = mgmt.get_broadcast_template_params("GW", "welcome_huf")
		self.assertEqual(out["success"], True)
		self.assertEqual(out["parameter_format"], "NAMED")
		self.assertEqual(out["body"], [{"name": "first_name", "sample": "Sam"}])
		self.assertEqual(set(out), {"success", "template", "parameter_format", "body", "header", "buttons"})

	def test_permission_denied(self):
		with patch.object(mgmt, "_gateway_read_allowed", return_value=False), patch.object(frappe.db, "exists", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				mgmt.get_broadcast_template_params("GW", "welcome_huf")
