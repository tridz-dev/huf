# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) tests for pre-registered OAuth clients and the
per-server refresh lock.

Run standalone: PYTHONPATH=. python3 huf/ai/tests/test_mcp_oauth_preregistered.py -v
"""

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

import frappe as _frappe  # noqa: E402

if isinstance(_frappe, MagicMock):  # stubbed env: make @frappe.whitelist() a passthrough
    _frappe.whitelist = lambda *a, **k: a[0] if a and callable(a[0]) else (lambda f: f)

from huf.ai import mcp_connection_resolver as resolver  # noqa: E402
from huf.ai import mcp_oauth  # noqa: E402

META_URL = "https://mcp.facebook.com/whatsapp_business_tools"
META_AS = {
    "issuer": "https://www.facebook.com/whatsapp_business_tools",
    "authorization_endpoint": "https://www.facebook.com/oauth/authorize",
    "token_endpoint": "https://graph.facebook.com/oauth/token",
    "code_challenge_methods_supported": ["S256"],
    "token_endpoint_auth_methods_supported": ["none"],
    "scopes_supported": [
        "business_management",
        "whatsapp_business_management",
        "whatsapp_business_messaging",
    ],
}
META_PRM = {"resource": META_URL, "authorization_servers": ["https://www.facebook.com/whatsapp_business_tools"]}


def _resolve(client_id, as_metadata):
    with patch.object(resolver, "frappe", MagicMock()), patch.object(
        resolver, "_is_safe_url", return_value=True
    ), patch.object(
        resolver, "_probe_mcp_endpoint", return_value={"status_code": 401, "headers": {}, "challenges": []}
    ), patch.object(
        resolver, "_discover_resource_metadata", return_value=dict(META_PRM)
    ), patch.object(
        resolver, "_discover_authorization_server", return_value=as_metadata
    ), patch.object(resolver, "_register_client") as register, patch.object(
        resolver.frappe, "only_for", MagicMock()
    ):
        return resolver.resolve_mcp_connection(META_URL, "https://site/mcp-oauth-callback", client_id), register


class TestPreRegisteredClient(unittest.TestCase):
    def test_client_id_skips_registration_and_does_not_need_endpoint(self):
        result, register = _resolve("my-app-id", dict(META_AS))
        register.assert_not_called()
        self.assertEqual(result["discovery_status"], "Ready")
        self.assertEqual(result["client_id"], "my-app-id")
        self.assertEqual(result["client_registration_method"], "pre_registered")
        self.assertEqual(result["scopes_supported"], META_AS["scopes_supported"])

    def test_no_client_id_and_no_registration_endpoint_still_errors(self):
        result, register = _resolve(None, dict(META_AS))
        register.assert_not_called()
        self.assertEqual(result["discovery_status"], "Failed")
        self.assertIn("Client ID", result["discovery_error"])

    def test_no_client_id_uses_dcr_when_available(self):
        metadata = dict(META_AS, registration_endpoint="https://as/register")
        with patch.object(resolver, "frappe", MagicMock()), patch.object(
            resolver, "_is_safe_url", return_value=True
        ), patch.object(
            resolver, "_probe_mcp_endpoint", return_value={"status_code": 401, "headers": {}, "challenges": []}
        ), patch.object(resolver, "_discover_resource_metadata", return_value=dict(META_PRM)), patch.object(
            resolver, "_discover_authorization_server", return_value=metadata
        ), patch.object(resolver, "_register_client", return_value={"client_id": "dyn"}) as register:
            result = resolver.resolve_mcp_connection(META_URL, "https://site/cb")
        register.assert_called_once()
        self.assertEqual(result["client_id"], "dyn")
        self.assertEqual(result["client_registration_method"], "dynamic_registration")

    def test_discover_passes_server_client_id(self):
        server = SimpleNamespace(
            server_url=META_URL, oauth_client_id="my-app-id", oauth_redirect_uri="https://site/cb",
            oauth_authorization_endpoint=None, oauth_token_endpoint=None,
            oauth_registration_endpoint=None, oauth_scope=None, save=MagicMock(),
        )
        frappe = MagicMock()
        frappe.get_doc.return_value = server
        with patch.object(resolver, "frappe", frappe), patch.object(
            resolver, "resolve_mcp_connection", return_value={"discovery_status": "Failed"}
        ) as resolve:
            resolver.discover_mcp_server("S")
        self.assertEqual(resolve.call_args.kwargs["client_id"], "my-app-id")


class TestRefreshLock(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.local.site = "site1"
        self.held = {}

        def _get(key):  # the lock still holds whatever value this caller stored
            return self.held.get(key)

        self.frappe.cache().get.side_effect = _get
        patcher = patch.object(mcp_oauth, "frappe", self.frappe)
        self.addCleanup(patcher.stop)
        patcher.start()

    def _record_set(self, results):
        results = iter(results)

        def _set(key, value, **kwargs):
            ok = next(results)
            if ok:
                self.held[key] = value
            return ok

        self.frappe.cache().set.side_effect = _set

    def test_lock_taken_around_refresh_and_released(self):
        self._record_set([True])
        with patch.object(mcp_oauth, "_read_access_token", return_value="old"), patch.object(
            mcp_oauth, "_refresh_oauth_token_unlocked", return_value="new"
        ) as inner:
            self.assertEqual(mcp_oauth.refresh_oauth_token("S"), "new")
        inner.assert_called_once_with("S")
        key = self.frappe.cache().set.call_args.args[0]
        self.assertIn("S", key)
        self.assertTrue(self.frappe.cache().set.call_args.kwargs["nx"])
        self.frappe.cache().delete.assert_called_once_with(key)

    def test_waiter_reuses_token_refreshed_by_other_worker(self):
        self._record_set([False, True])
        with patch.object(mcp_oauth, "_read_access_token", side_effect=["old", "fresh"]), patch.object(
            mcp_oauth, "_refresh_oauth_token_unlocked"
        ) as inner, patch.object(mcp_oauth.time, "sleep"):
            self.assertEqual(mcp_oauth.refresh_oauth_token("S"), "fresh")
        inner.assert_not_called()
        self.frappe.cache().delete.assert_called_once()

    def test_lock_released_when_refresh_fails(self):
        self._record_set([True])
        with patch.object(mcp_oauth, "_read_access_token", return_value="old"), patch.object(
            mcp_oauth, "_refresh_oauth_token_unlocked", side_effect=ValueError("boom")
        ):
            with self.assertRaises(ValueError):
                mcp_oauth.refresh_oauth_token("S")
        self.frappe.cache().delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
