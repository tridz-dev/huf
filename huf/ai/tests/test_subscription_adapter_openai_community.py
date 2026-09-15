import json
import unittest
from unittest.mock import patch, MagicMock

import frappe

from huf.ai.providers.adapters import get_adapter
from huf.ai.providers.adapters.openai_community import OpenAICommunitySubscriptionAdapter


class TestOpenAICommunitySubscriptionAdapter(unittest.TestCase):
    def setUp(self):
        # Enable community adapter for tests.
        frappe.conf["enable_openai_community_subscription_adapter"] = 1

        if not frappe.db.exists("AI Provider", "OpenAICommunityTest"):
            provider_doc = frappe.get_doc({
                "doctype": "AI Provider",
                "provider_name": "OpenAICommunityTest",
                "provider_brand": "openai_community",
                "api_key": "",
            })
            provider_doc.insert(ignore_permissions=True)

        if frappe.db.exists("AI Provider Connection", "Test OpenAI Community"):
            frappe.delete_doc("AI Provider Connection", "Test OpenAI Community", force=True)

        self.conn = frappe.get_doc({
            "doctype": "AI Provider Connection",
            "connection_name": "Test OpenAI Community",
            "user": "Administrator",
            "provider": "OpenAICommunityTest",
            "adapter_type": "openai_community_subscription",
            "auth_status": "Unlinked",
            "auth_method": "OAuth PKCE (Manual Paste)",
            "is_active": 1,
            "eligible_models": json.dumps(["gpt-4o", "gpt-5.2"]),
        })
        self.conn.insert(ignore_permissions=True)

    def tearDown(self):
        if frappe.db.exists("AI Provider Connection", "Test OpenAI Community"):
            frappe.delete_doc("AI Provider Connection", "Test OpenAI Community", force=True)
        frappe.conf.pop("enable_openai_community_subscription_adapter", None)

    def test_adapter_registry(self):
        adapter = get_adapter("openai_community_subscription")
        self.assertIsInstance(adapter, OpenAICommunitySubscriptionAdapter)

    def test_adapter_disabled_without_flag(self):
        frappe.conf.pop("enable_openai_community_subscription_adapter", None)
        with self.assertRaises(frappe.PermissionError):
            OpenAICommunitySubscriptionAdapter()

    def test_authorization_url_uses_community_client_id(self):
        adapter = get_adapter(self.conn.adapter_type)
        auth_data = adapter.start_authorization(self.conn, mode="OAuth PKCE (Manual Paste)")

        self.assertIn("auth_url", auth_data)
        auth_url = auth_data["auth_url"]
        self.assertIn("client_id=app_EMoamEEZ73f0CkXaXp7hrann", auth_url)
        self.assertIn("originator=codex_cli_rs", auth_url)
        self.assertIn("codex_cli_simplified_flow=true", auth_url)
        self.assertIn("code_challenge_method=S256", auth_url)
        self.assertEqual(self.conn.auth_status, "Pending Authorization")

    def test_complete_authorization_exchanges_code_without_secret(self):
        adapter = get_adapter(self.conn.adapter_type)
        auth_data = adapter.start_authorization(self.conn, mode="OAuth PKCE (Manual Paste)")
        state = auth_data["state"]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": _fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acc_123"}}),
            "refresh_token": "refresh_123",
            "expires_in": 3600,
            "token_type": "Bearer",
            "id_token": _fake_jwt({"email": "test@example.com"}),
        }

        with patch("huf.ai.providers.adapters.openai_community.requests.post", return_value=mock_response) as mock_post:
            result = adapter.complete_authorization(
                self.conn,
                {"code": "auth_code_123", "state": state},
            )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(call_kwargs["data"]["client_id"], "app_EMoamEEZ73f0CkXaXp7hrann")
        self.assertNotIn("client_secret", call_kwargs["data"])

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.conn.auth_status, "Active")
        self.assertEqual(self.conn.account_id, "acc_123")
        self.assertEqual(self.conn.account_email, "test@example.com")
        self.assertEqual(self.conn.get_decrypted_refresh_token(), "refresh_123")

    def test_complete_authorization_from_pasted_url(self):
        adapter = get_adapter(self.conn.adapter_type)
        auth_data = adapter.start_authorization(self.conn, mode="OAuth PKCE (Manual Paste)")
        state = auth_data["state"]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": _fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acc_456"}}),
            "refresh_token": "refresh_456",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        pasted_url = f"http://localhost:1455/auth/callback?code=pasted_code&state={state}"
        with patch("huf.ai.providers.adapters.openai_community.requests.post", return_value=mock_response):
            result = adapter.complete_authorization(
                self.conn,
                {"pasted_url": pasted_url},
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.conn.account_id, "acc_456")

    def test_refresh_connection_is_secretless(self):
        adapter = get_adapter(self.conn.adapter_type)
        self.conn.set_tokens("access_123", "refresh_123", expires_in_seconds=3600)
        self.conn.auth_status = "Active"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": _fake_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acc_789"}}),
            "refresh_token": "refresh_789",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("huf.ai.providers.adapters.openai_community.requests.post", return_value=mock_response) as mock_post:
            success = adapter.refresh_connection(self.conn)

        self.assertTrue(success)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(call_kwargs["data"]["client_id"], "app_EMoamEEZ73f0CkXaXp7hrann")
        self.assertNotIn("client_secret", call_kwargs["data"])
        self.assertEqual(self.conn.get_decrypted_refresh_token(), "refresh_789")

    def test_discover_models_returns_allowlist(self):
        adapter = get_adapter(self.conn.adapter_type)
        models = adapter.discover_models(self.conn)
        self.assertTrue(any(m["id"] == "gpt-5.2" for m in models))
        self.assertTrue(any(m["id"] == "gpt-4o" for m in models))

    def test_revoke_connection(self):
        adapter = get_adapter(self.conn.adapter_type)
        self.conn.set_tokens("access", "refresh", expires_in_seconds=3600)
        success = adapter.revoke_connection(self.conn)
        self.assertTrue(success)
        self.assertEqual(self.conn.auth_status, "Revoked")
        self.assertEqual(self.conn.get_decrypted_access_token(), "")


def _fake_jwt(payload: dict) -> str:
    """Build a fake JWT string for tests (no signature validation)."""
    import base64
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.signature"
