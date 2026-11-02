"""Web-access launch: URL helper, /tg_open route context, static HTML checks. Fakes only."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest import mock

from huf.ai import telegram_web_access_url as u
from huf.www import tg_open

HTML = (Path(tg_open.__file__).parent / "tg_open.html").read_text()


class TestUrlHelper(unittest.TestCase):
	def test_uses_public_url(self):
		with mock.patch("huf.ai.telegram_public_url.public_url", return_value="https://h/x") as p:
			self.assertEqual(u.web_access_url("gw1"), "https://h/x")
		p.assert_called_once_with("/tg_open?gw=gw1")

	def test_encoding_and_to(self):
		with mock.patch("huf.ai.telegram_public_url.public_base_url", return_value="https://h.example"):
			url = u.web_access_url("my gw&x", "/app/query-report/A B?f=1&g=2")
		self.assertEqual(
			url, "https://h.example/tg_open?gw=my+gw%26x&to=%2Fapp%2Fquery-report%2FA+B%3Ff%3D1%26g%3D2"
		)

	def test_empty_to_omitted(self):
		with mock.patch("huf.ai.telegram_public_url.public_base_url", return_value="https://h.example"):
			self.assertEqual(u.web_access_url("g", ""), "https://h.example/tg_open?gw=g")


class TestRoute(unittest.TestCase):
	def test_context_no_cache_and_nothing_rendered(self):
		self.assertEqual(tg_open.no_cache, 1)
		self.assertEqual(tg_open.sitemap, 0)
		from unittest import mock

		with mock.patch.object(tg_open, "frappe", mock.Mock(session=mock.Mock(user="Guest"))):
			ctx = tg_open.get_context(type("C", (), {})())
		self.assertEqual(ctx.no_cache, 1)
		self.assertFalse(ctx.show_sidebar)
		self.assertFalse(hasattr(ctx, "gateway"))

	def test_only_the_server_generated_csrf_token_is_templated(self):
		"""Nothing request-derived is rendered. The single allowed expression is the CSRF token, which the
		server generates and Frappe's own pages embed the same way."""
		import re

		self.assertNotIn("{%", HTML)
		exprs = re.findall(r"\{\{.*?\}\}", HTML)
		self.assertEqual(exprs, ["{{ csrf_token or '' }}"])


class TestStaticHtml(unittest.TestCase):
	def test_no_innerhtml_or_inline_handlers(self):
		self.assertNotRegex(HTML, r"(?i)innerHTML|outerHTML|insertAdjacentHTML|document\.write")
		self.assertIsNone(re.search(r"(?i)<[^>]+\son[a-z]+\s*=", HTML))

	def test_contract(self):
		for s in (
			"telegram.org/js/telegram-web-app.js",
			"/api/method/huf.ai.telegram_web_access.exchange",
			"application/json",
			"same-origin",
			"Not authorized. Ask your administrator.",
			"Open this link from the Telegram app.",
			"Telegram Web cannot keep a sign-in here.",
			"location.replace",
		):
			self.assertIn(s, HTML)


class TestCsrfForReentry(unittest.TestCase):
	def test_context_carries_a_csrf_token_only_for_a_logged_in_session(self):
		from unittest import mock

		from huf.www import tg_open

		class Ctx(dict):
			def __setattr__(self, k, v):
				self[k] = v

		with mock.patch.object(tg_open, "frappe", mock.Mock(session=mock.Mock(user="Guest"))):
			self.assertEqual(tg_open.get_context(Ctx())["csrf_token"], "")
		with (
			mock.patch.object(tg_open, "frappe", mock.Mock(session=mock.Mock(user="a@b.c"))),
			mock.patch("frappe.sessions.get_csrf_token", return_value="tok123", create=True),
		):
			self.assertEqual(tg_open.get_context(Ctx())["csrf_token"], "tok123")

	def test_page_sends_the_csrf_header_from_the_meta_tag(self):
		html = open(tg_open_html_path()).read()
		self.assertIn('name="csrf-token"', html)
		self.assertIn("X-Frappe-CSRF-Token", html)
		self.assertNotIn("innerHTML", html)


def tg_open_html_path():
	import os

	import huf

	return os.path.join(os.path.dirname(huf.__file__), "www", "tg_open.html")
