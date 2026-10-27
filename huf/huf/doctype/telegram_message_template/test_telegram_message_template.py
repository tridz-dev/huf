# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.telegram_message_template import telegram_message_template as tmt


class TestTemplateHelpers(unittest.TestCase):
	"""Pure logic: no site needed."""

	def test_slug_and_language(self):
		self.assertTrue(tmt.TEMPLATE_NAME_RE.match("welcome_1-a"))
		self.assertFalse(tmt.TEMPLATE_NAME_RE.match("Welcome"))
		self.assertFalse(tmt.TEMPLATE_NAME_RE.match("a b"))
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
		self.assertEqual(tmt.button_problems(good), [])
		self.assertEqual(tmt.button_problems('{"rows": [[{"text": "Go", "web_app": "{{url}}"}]]}'), [])
		self.assertTrue(tmt.button_problems("not json"))
		self.assertTrue(tmt.button_problems("{}"))


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


class TestTemplateSave(IntegrationTestCase):
	"""Doctype validation shares the endpoint's rules (site test)."""

	def make(self, name, **kw):
		return frappe.get_doc(
			{
				"doctype": "Telegram Message Template",
				"template_name": name,
				"parse_mode": "HTML",
				"body": "Hi {{n}}",
				"media_type": "none",
				**kw,
			}
		)

	def tearDown(self):
		frappe.db.rollback()

	def test_placeholder_url_buttons_and_long_media_text_save(self):
		self.make("f9-web-app", buttons_json='{"rows": [[{"text": "Open", "web_app": "{{url}}"}]]}').insert()
		self.make("f9-long-media", body="x" * 1500, media_type="photo", media="https://x.io/a.jpg").insert()

	def test_bad_names_and_placeholders_rejected(self):
		for name in ("My Tpl", "Upper"):
			with self.assertRaises(frappe.ValidationError, msg=name):
				self.make(name).insert()
		with self.assertRaises(frappe.ValidationError):
			self.make("f9-badph", body="Hi {{a.b}}").insert()
