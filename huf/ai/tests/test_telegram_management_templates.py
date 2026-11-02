# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram template management: permissions, save validation, test-send guards (all mocked, no site)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import frappe

from huf.ai import telegram_management_templates as _m


class _Unwrapped:
	"""The module with whitelisted functions stripped of frappe's request-time type validation wrapper."""

	def __getattr__(self, name):
		attr = getattr(_m, name)
		return getattr(attr, "__wrapped__", attr) if callable(attr) else attr


m = _Unwrapped()
P = "huf.ai.telegram_management_templates"


def fake_frappe(**over):
	"""Stand-in for the module's ``frappe`` (db/session are unbound proxies without a site)."""
	f = mock.MagicMock()
	f.PermissionError = frappe.PermissionError
	f.DuplicateEntryError = frappe.DuplicateEntryError
	f.ValidationError = frappe.ValidationError
	f.whitelist = frappe.whitelist
	for k, v in over.items():
		setattr(f, k, v)
	return f


GOOD = {"template_name": "welcome", "parse_mode": "HTML", "body": "Hi {{name}}", "media_type": "none"}


class TestValidate(unittest.TestCase):
	def fields(self, **over):
		return {p["field"] for p in m.validate_values({**GOOD, **over})}

	def test_good(self):
		self.assertEqual(m.validate_values(GOOD), [])

	def test_name_and_mode(self):
		self.assertIn("template_name", self.fields(template_name=""))
		self.assertIn("template_name", self.fields(template_name="bad/name"))
		self.assertIn("parse_mode", self.fields(parse_mode="Markdown"))

	def test_body_required_without_media(self):
		self.assertIn("body", self.fields(body="  "))
		self.assertNotIn("body", self.fields(body="", media_type="photo", media="/files/a.png"))

	def test_media_needs_file_and_caption_limit(self):
		self.assertIn("media", self.fields(media_type="photo"))
		# the sender splits media + long text into two messages, so a long body with media is fine
		self.assertNotIn("body", self.fields(media_type="photo", media="/f.png", body="x" * 1025))
		self.assertIn("body", self.fields(body="x" * 4097))

	def test_buttons_validated_with_variables(self):
		ok = '{"rows": [[{"text": "Open", "url": "https://x.com/{{id}}"}]]}'
		self.assertNotIn("buttons_json", self.fields(buttons_json=ok))
		self.assertIn("buttons_json", self.fields(buttons_json="{nope"))
		self.assertIn("buttons_json", self.fields(buttons_json='{"rows": [[{"text": "A"}]]}'))

	def test_name_matrix_matches_doctype_grammar(self):
		for name, ok in [
			("welcome", True), ("a-b_c1", True), ("My Tpl", False), ("Welcome", False),
			("_x", False), ("a" * 64, False), ("bad/name", False),
		]:  # fmt: skip
			self.assertEqual("template_name" not in self.fields(template_name=name), ok, name)
		self.assertIn("lowercase", m.validate_values({**GOOD, "template_name": "My Tpl"})[0]["message"])

	def test_url_kind_buttons_accept_placeholders(self):
		for key in ("web_app", "login_url", "url"):
			raw = json.dumps({"rows": [[{"text": "Go", key: "{{url}}"}]]})
			self.assertEqual(m.validate_values({**GOOD, "buttons_json": raw}), [], key)
		self.assertIn(
			"buttons_json",
			self.fields(buttons_json='{"rows": [[{"text": "Go", "web_app": "http://insecure.io"}]]}'),
		)

	def test_unknown_placeholder_forms_rejected(self):
		self.assertIn("body", self.fields(body="Hi {{user.name}}"))
		self.assertIn("body", self.fields(body="Hi {{name|upper}}"))
		self.assertNotIn("body", self.fields(body="Hi {{name|url}}"))

	def test_variable_names_are_identifiers(self):
		self.assertIn("variables.0", self.fields(variables=[{"variable": "a.b"}]))
		self.assertIn("variables.0", self.fields(variables=[{"variable": "a-b"}]))

	def test_duplicate_variable(self):
		self.assertIn("variables.1", self.fields(variables=[{"variable": "a"}, {"variable": "a"}]))


class TestPreview(unittest.TestCase):
	def run_preview(self, values, variables=None):
		with mock.patch(f"{P}._can_manage_integrations", return_value=True):
			return m.preview_template(values, variables or {})["preview"]

	def test_unsaved_values_use_the_send_render_and_examples(self):
		out = self.run_preview(
			{**GOOD, "body": "<b>{{name}}</b> {{x}}", "variables": [{"variable": "x", "example": "ex"}]},
			{"name": "<i>"},
		)
		self.assertEqual(out["text"], "<b>&lt;i&gt;</b> ex")
		self.assertEqual(out["missing"], [])
		self.assertFalse(out["split"])

	def test_missing_is_empty_and_default_used(self):
		out = self.run_preview(
			{
				**GOOD,
				"body": "Hi {{name}}{{y}}",
				"variables": [{"variable": "name", "default_value": "friend"}],
			}
		)
		self.assertEqual((out["text"], out["missing"]), ("Hi friend", ["y"]))

	def test_long_text_with_media_previews_as_two_messages(self):
		out = self.run_preview({**GOOD, "body": "x" * 1500, "media_type": "photo", "media": "/f.png"})
		self.assertTrue(out["split"])
		self.assertEqual(out["errors"], [])

	def test_callback_buttons_preview_unsigned(self):
		out = self.run_preview({**GOOD, "buttons_json": '{"rows": [[{"text": "Y", "callback": "yes"}]]}'})
		self.assertEqual(out["errors"], [])
		self.assertEqual(out["markup"]["inline_keyboard"][0][0]["text"], "Y")


class TestPermissions(unittest.TestCase):
	def test_non_admin_denied_everywhere(self):
		with (
			mock.patch(f"{P}._can_manage_integrations", return_value=False),
			mock.patch(f"{P}._", lambda x: x),
		):
			for fn, args in [
				(m.list_templates, ()),
				(m.get_template, ("a",)),
				(m.save_template, ({},)),
				(m.delete_template, ("a",)),
				(m.preview_template, ("a",)),
				(m.send_test_template, ("G", "1", "a", {}, 1)),
			]:
				with self.assertRaises(frappe.PermissionError, msg=fn.__name__):
					fn(*args)

	def test_save_invalid_returns_problems_before_writing(self):
		with (
			mock.patch(f"{P}._can_manage_integrations", return_value=True),
			mock.patch(f"{P}.frappe", fake_frappe()) as fr,
		):
			gd = fr.get_doc
			out = m.save_template({"template_name": ""})
		self.assertEqual(out["error"], "invalid")
		self.assertTrue(out["problems"])
		gd.assert_not_called()

	def test_save_denied_without_doctype_permission(self):
		with (
			mock.patch(f"{P}._can_manage_integrations", return_value=True),
			mock.patch(f"{P}.frappe", fake_frappe(has_permission=mock.Mock(return_value=False))) as fr,
			mock.patch(f"{P}._", lambda x: x),
		):
			gd = fr.get_doc
			with self.assertRaises(frappe.PermissionError):
				m.save_template(GOOD)
		gd.assert_not_called()


class TestSendTest(unittest.TestCase):
	def run_send(self, chat="123", confirm=1, entries=(), user="me@x.com"):
		stack = [
			mock.patch(f"{P}._can_manage_integrations", return_value=True),
			mock.patch(f"{P}._require_gateway_admin"),
			mock.patch(
				f"{P}.frappe",
				fake_frappe(
					get_all=mock.Mock(return_value=list(entries)),
					session=mock.Mock(user=user),
				),
			),
		]
		for p in stack:
			p.start()
			self.addCleanup(p.stop)
		return m.send_test_template("G", chat, "welcome", {}, confirm)

	def test_requires_confirm(self):
		self.assertEqual(self.run_send(confirm=None)["error"], "confirm_required")

	def test_rejects_non_numeric_chat(self):
		self.assertEqual(self.run_send(chat="@someone")["error"], "invalid_chat")

	def test_refuses_arbitrary_chat(self):
		self.assertEqual(self.run_send(entries=[])["error"], "chat_not_allowed")
		self.assertEqual(
			self.run_send(entries=[{"approved_by": "other@x.com", "notes": ""}])["error"], "chat_not_allowed"
		)

	def test_allows_own_paired_and_marked_test_chat(self):
		fake = mock.Mock()
		fake.send_template.return_value = {"message_ids": [1]}
		with mock.patch(f"{P}.telegram_templates", fake):
			own = self.run_send(entries=[{"approved_by": "me@x.com", "notes": ""}])
			marked = self.run_send(entries=[{"approved_by": "o@x.com", "notes": "Telegram-Test chat"}])
		self.assertTrue(own["success"])
		self.assertTrue(marked["success"])
