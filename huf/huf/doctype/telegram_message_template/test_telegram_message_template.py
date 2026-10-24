# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.telegram_message_template import telegram_message_template as tmt


class TestTemplateHelpers(unittest.TestCase):
	"""Pure logic: no site needed."""

	def test_body_variables(self):
		self.assertEqual(tmt.body_variables("Hi {{ name }}, {{name}} {{ code }}"), ["name", "code"])
		self.assertEqual(tmt.body_variables(""), [])

	def test_slug_and_language(self):
		self.assertTrue(tmt.SLUG_RE.match("welcome_1-a"))
		self.assertFalse(tmt.SLUG_RE.match("Welcome"))
		self.assertFalse(tmt.SLUG_RE.match("a b"))
		self.assertTrue(tmt.LANG_RE.match("pt-BR"))
		self.assertTrue(tmt.LANG_RE.match("en"))
		self.assertFalse(tmt.LANG_RE.match("English!"))

	def test_html_problems(self):
		self.assertEqual(tmt.html_problems("<b>hi</b> <a href='x'>y</a>"), [])
		self.assertTrue(tmt.html_problems("<b>hi"))
		self.assertTrue(tmt.html_problems("<div>hi</div>"))
		self.assertTrue(tmt.html_problems("<b><i>x</b></i>"))

	def test_buttons_errors(self):
		good = json.dumps({"rows": [[{"text": "Yes", "callback": "yes"}]]})
		self.assertEqual(tmt.buttons_errors(good), [])
		self.assertTrue(tmt.buttons_errors("not json"))
		self.assertTrue(tmt.buttons_errors("{}"))


class TestTelegramMessageTemplate(IntegrationTestCase):
	def _doc(self, **kw):
		data = {"doctype": "Telegram Message Template", "template_name": "t-s1", "body": "Hi {{name}}"}
		data.update(kw)
		return frappe.get_doc(data)

	def test_valid_insert(self):
		doc = self._doc(variables=[{"variable": "name", "default_value": "there"}])
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Telegram Message Template", doc.name, force=True)
		self.assertEqual(doc.name, "t-s1")

	def test_rejects(self):
		for kw in (
			{"template_name": "Bad Name"},
			{"body": ""},
			{"media_type": "photo"},
			{"language": "x!"},
			{"body": "<b>open"},
			{"buttons_json": "nope"},
		):
			with self.assertRaises(frappe.ValidationError, msg=str(kw)):
				self._doc(**kw).validate()
