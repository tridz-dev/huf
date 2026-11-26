# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""safety.py must import when WeasyPrint's system libraries (pango) are missing."""

import importlib
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

MISSING_PANGO_MESSAGE = "cannot load library 'libpango-1.0-0'"


def _load_safety_without_pango():
	if "frappe" not in sys.modules:
		sys.modules["frappe"] = MagicMock(name="frappe")

	path = os.path.join(os.path.dirname(__file__), "safety.py")
	spec = importlib.util.spec_from_file_location("_safety_under_test", path)
	mod = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules):
		real_import = __import__

		def fake_import(name, *a, **k):
			if name == "weasyprint" or name.startswith("weasyprint."):
				raise OSError(MISSING_PANGO_MESSAGE)
			return real_import(name, *a, **k)

		with patch("builtins.__import__", fake_import):
			spec.loader.exec_module(mod)
	return mod


class TestMissingPango(unittest.TestCase):
	def test_import_succeeds_and_flags_unavailable(self):
		mod = _load_safety_without_pango()
		self.assertFalse(mod.WEASYPRINT_AVAILABLE)

	def test_allowlist_unchanged(self):
		mod = _load_safety_without_pango()
		self.assertEqual(mod.ALLOWED_RESOURCE_HOSTS, frozenset({"fonts.googleapis.com", "fonts.gstatic.com"}))
		with self.assertRaises(ValueError):
			mod.safe_url_fetcher("http://169.254.169.254/latest")
		with self.assertRaises(ValueError):
			mod.safe_url_fetcher("https://evil.example.com/x.css")

	def test_allowed_host_has_no_engine(self):
		mod = _load_safety_without_pango()
		with self.assertRaises(RuntimeError):
			mod.safe_url_fetcher("https://fonts.gstatic.com/a.woff2")
