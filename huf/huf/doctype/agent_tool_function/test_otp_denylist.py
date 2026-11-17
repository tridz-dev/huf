import unittest

import frappe

from huf.ai.app_seeding.loaders import upsert_tool
from huf.huf.doctype.agent_tool_function.agent_tool_function import (
	OTP_TOOL_DENYLIST,
	is_otp_tool_path,
)


class TestOtpToolDenylist(unittest.TestCase):
	def test_paths_denied(self):
		for path in OTP_TOOL_DENYLIST:
			self.assertTrue(is_otp_tool_path(path))
			self.assertTrue(is_otp_tool_path(f"  {path} "))
		self.assertFalse(is_otp_tool_path("huf.ai.tools.functions.get_document"))
		self.assertFalse(is_otp_tool_path(None))

	def test_doctype_validate_rejects(self):
		doc = frappe.get_doc({
			"doctype": "Agent Tool Function", "tool_name": "otp_sender", "types": "Custom Function",
			"function_path": OTP_TOOL_DENYLIST[0], "description": "x",
		})
		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_seeding_rejects(self):
		ok, msg = upsert_tool({"tool_name": "otp_x", "function_path": OTP_TOOL_DENYLIST[1]}, "app", "f.json")
		self.assertFalse(ok)
		self.assertIn("OTP", msg)
