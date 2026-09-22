"""Frappe-free collection shim for provider-neutral Decision Runtime tests."""
from __future__ import annotations

import sys
import types


if "frappe" not in sys.modules:
    frappe = types.ModuleType("frappe")
    frappe.__path__ = []
    frappe.logger = lambda *_args, **_kwargs: types.SimpleNamespace(level=20, setLevel=lambda *_: None)
    frappe.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    sys.modules["frappe"] = frappe
