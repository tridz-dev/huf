# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for the permission gate on
`huf.ai.local_runtime.test_provider_connection`.

Context (ST-R6.4b): `test_provider_connection` probes a provider's live API
using stored (or caller-supplied) credentials — an outbound, credentialed
call. Before the fix, the `frappe.has_permission("AI Provider", "write")`
check only ran when the caller supplied override parameters (api_key,
api_base_url, provider_brand, is_local_llm). When called with NO overrides —
the common case, e.g. "test connection" on an already-saved provider — there
was no permission check at all: any authenticated user could trigger the
probe using the provider's stored secret.

The fix makes the permission check unconditional, before anything that would
use stored credentials to make an outbound call. These tests prove:

1. A caller lacking "AI Provider" write permission gets a permission error
   and no outbound call is attempted — with NO overrides supplied (the gap
   this fix closes) and also with overrides supplied (the case that was
   already covered).
2. A caller WITH "AI Provider" write permission can still successfully test
   a connection, with or without overrides — the fix must not regress the
   legitimate use case.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_local_runtime_provider_connection_permission.py -v
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Mirror test_test_provider.py's defensive frappe stub: only stub when the
# real package isn't importable, so this file behaves the same whether run
# standalone or collected under a real bench.
try:
    import frappe  # noqa: F401
except ImportError:
    frappe_mock = MagicMock()
    frappe_mock.utils = MagicMock()
    frappe_mock._ = lambda x: x
    # `@frappe.whitelist()` must stay a transparent identity decorator, not
    # the default auto-mocked callable — otherwise the imported
    # `test_provider_connection` is a bare MagicMock instead of the real
    # function, and every assertion below would silently test nothing.
    frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = frappe_mock.utils

try:
    import requests  # noqa: F401
except ImportError:
    sys.modules["requests"] = MagicMock()

from huf.ai import local_runtime  # noqa: E402


def _make_provider_doc(**overrides):
    fields = {
        "is_local_llm": 0,
        "api_base_url": None,
        "provider_brand": "openai",
    }
    fields.update(overrides)
    doc = SimpleNamespace(**fields)
    doc.get = lambda key, default=None: getattr(doc, key, default)
    doc.get_password = MagicMock(return_value="stored-secret-key")
    return doc


class TestProviderConnectionPermissionGate(unittest.TestCase):
    """Prove the permission check runs unconditionally — before any outbound,
    credentialed call — regardless of whether overrides are supplied."""

    def setUp(self):
        patcher_get_doc = patch.object(
            local_runtime.frappe, "get_doc", return_value=_make_provider_doc()
        )
        self.mock_get_doc = patcher_get_doc.start()
        self.addCleanup(patcher_get_doc.stop)

        patcher_probe = patch.object(
            local_runtime,
            "probe_cloud_provider",
            return_value={"ok": True, "error": None},
        )
        self.mock_probe = patcher_probe.start()
        self.addCleanup(patcher_probe.stop)

    def test_no_overrides_denies_and_never_calls_outbound_probe_without_permission(self):
        """The gap this fix closes: no override params supplied, caller
        lacks write permission -> must be denied, and the credentialed
        outbound probe must never fire."""
        with patch.object(local_runtime.frappe, "has_permission", return_value=False) as mock_perm:
            result = local_runtime.test_provider_connection("My Provider")

        mock_perm.assert_called_once_with("AI Provider", "write", "My Provider")
        self.mock_probe.assert_not_called()
        self.assertFalse(result["provider"]["ok"])
        self.assertIsNotNone(result["provider"]["error"])

    def test_overrides_supplied_still_denies_and_never_calls_outbound_probe_without_permission(self):
        """The previously-covered case must keep working: overrides supplied,
        caller lacks write permission -> denied, no outbound call."""
        with patch.object(local_runtime.frappe, "has_permission", return_value=False) as mock_perm:
            result = local_runtime.test_provider_connection(
                "My Provider", api_key="sk-fake", provider_brand="openai"
            )

        mock_perm.assert_called_once_with("AI Provider", "write", "My Provider")
        self.mock_probe.assert_not_called()
        self.assertFalse(result["provider"]["ok"])
        self.assertIsNotNone(result["provider"]["error"])

    def test_no_overrides_with_permission_still_succeeds(self):
        """Must not regress the legitimate use case: a user with write
        permission can test an already-saved provider with no overrides."""
        with patch.object(local_runtime.frappe, "has_permission", return_value=True) as mock_perm:
            result = local_runtime.test_provider_connection("My Provider")

        mock_perm.assert_called_once_with("AI Provider", "write", "My Provider")
        self.mock_probe.assert_called_once()
        self.assertTrue(result["provider"]["ok"])

    def test_overrides_with_permission_still_succeeds(self):
        """Must not regress the legitimate use case: a user with write
        permission can test unsaved (override) configuration too."""
        with patch.object(local_runtime.frappe, "has_permission", return_value=True) as mock_perm:
            result = local_runtime.test_provider_connection(
                "My Provider", api_key="sk-fake", provider_brand="openai"
            )

        mock_perm.assert_called_once_with("AI Provider", "write", "My Provider")
        self.mock_probe.assert_called_once()
        self.assertTrue(result["provider"]["ok"])


if __name__ == "__main__":
    unittest.main()
