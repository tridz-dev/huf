"""Root pytest configuration.

Stubs the ``frappe`` module when it is not installed (e.g. during local
unit-test runs for Frappe-free modules such as ``huf.ai.acp``). This conftest
is loaded before any test package imports, so ``huf/__init__.py`` can import
``frappe`` without failing.
"""

from __future__ import annotations

import json
import logging
import sys
import types


def _install_frappe_stub() -> None:
	if "frappe" in sys.modules:
		return

	frappe = types.ModuleType("frappe")
	frappe.logger = lambda name=None: logging.getLogger(name or "frappe")
	frappe.get_doc = lambda *args, **kwargs: None
	frappe.get_cached_doc = lambda *args, **kwargs: None
	frappe.get_all = lambda *args, **kwargs: []
	frappe.get_value = lambda *args, **kwargs: None
	frappe.get_cached_value = lambda *args, **kwargs: None
	frappe.throw = lambda *args, **kwargs: (_ for _ in ()).throw(Exception(args[0]) if args else Exception())
	frappe.DoesNotExistError = Exception
	frappe.ValidationError = Exception
	frappe.PermissionError = Exception
	frappe._ = lambda s, *args, **kwargs: s
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.is_whitelisted = lambda fn: None
	frappe.get_attr = lambda path: None
	frappe.local = types.SimpleNamespace(site="test_site", conf={})
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.get_roles = lambda user=None: ["System Manager", "Administrator"]
	frappe.parse_json = json.loads
	frappe.cache = lambda: None

	# Minimal frappe.model.document stub so DocType controllers can be imported in tests.
	frappe_model = types.ModuleType("frappe.model")
	frappe_model_document = types.ModuleType("frappe.model.document")
	frappe_model_document.Document = type("Document", (), {})
	frappe.model = frappe_model
	frappe_model.document = frappe_model_document
	sys.modules["frappe.model"] = frappe_model
	sys.modules["frappe.model.document"] = frappe_model_document

	frappe_tests = types.ModuleType("frappe.tests")
	frappe_tests.FrappeTestCase = type("FrappeTestCase", (object,), {})
	frappe.tests = frappe_tests
	sys.modules["frappe.tests"] = frappe_tests
	sys.modules["frappe.tests.utils"] = types.ModuleType("frappe.tests.utils")

	sys.modules["frappe"] = frappe


_install_frappe_stub()
