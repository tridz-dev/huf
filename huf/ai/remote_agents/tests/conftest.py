"""Test fixtures for the remote_agents package.

The ``huf`` package root imports ``frappe`` at import time, so these tests need a
minimal stub in ``sys.modules`` before any ``huf.*`` import is resolved.
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
	frappe.parse_json = json.loads
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.get_roles = lambda user=None: ["System Manager", "Administrator"]
	frappe.DoesNotExistError = Exception
	frappe.ValidationError = Exception
	frappe.PermissionError = Exception
	frappe._ = lambda s, *args, **kwargs: s

	frappe_tests = types.ModuleType("frappe.tests")
	frappe_tests.FrappeTestCase = type("FrappeTestCase", (object,), {})
	frappe.tests = frappe_tests
	sys.modules["frappe.tests"] = frappe_tests
	sys.modules["frappe.tests.utils"] = types.ModuleType("frappe.tests.utils")

	sys.modules["frappe"] = frappe


_install_frappe_stub()
