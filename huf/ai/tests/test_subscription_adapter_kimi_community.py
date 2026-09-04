import json
import unittest
from unittest.mock import patch, MagicMock

import frappe

from huf.ai.providers.adapters import get_adapter
from huf.ai.providers.adapters.kimi_community import KimiCommunitySubscriptionAdapter


class TestKimiCommunitySubscriptionAdapter(unittest.TestCase):
    def setUp(self):
        frappe.conf["enable_kimi_community_subscription_adapter"] = 1

        if not frappe.db.exists("AI Provider", "KimiCommunityTest"):
            provider_doc = frappe.get_doc({
                "doctype": "AI Provider",
                "provider_name": "KimiCommunityTest",
                "provider_brand": "kimi_community",
                "api_key": "",
            })
            provider_doc.insert(ignore_permissions=True)

        if frappe.db.exists("AI Provider Connection", "Test Kimi Community"):
            frappe.delete_doc("AI Provider Connection", "Test Kimi Community", force=True)

        self.conn = frappe.get_doc({
            "doctype": "AI Provider Connection",
            "connection_name": "Test Kimi Community",
            "user": "Administrator",
            "provider": "KimiCommunityTest",
            "adapter_type": "kimi_community_subscription",
            "auth_status": "Unlinked",
            "auth_method": "Device Code",
            "is_active": 1,
            "eligible_models": json.dumps(["kimi-for-coding"]),
        })
        self.conn.insert(ignore_permissions=True)

    def tearDown(self):
        if frappe.db.exists("AI Provider Connection", "Test Kimi Community"):
            frappe.delete_doc("AI Provider Connection", "Test Kimi Community", force=True)
        frappe.conf.pop("enable_kimi_community_subscription_adapter", None)

    def test_adapter_registry(self):
        adapter = get_adapter("kimi_community_subscription")
        self.assertIsInstance(adapter, KimiCommunitySubscriptionAdapter)

    def test_adapter_disabled_without_flag(self):
        frappe.conf.pop("enable_kimi_community_subscription_adapter", None)
        with self.assertRaises(frappe.PermissionError):
            KimiCommunitySubscriptionAdapter()

    def test_start_authorization_requests_device_code(self):
        adapter = get_adapter(self.conn.adapter_type)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "device_code": "dev_123",
            "user_code": "USER123",
            "verification_uri": "https://auth.kimi.com/activate",
            "verification_uri_complete": "https://auth.kimi.com/activate?user_code=USER123",
            "expires_in": 1800,
            "interval": 5,
        }

        with patch("huf.ai.providers.adapters.kimi_community.requests.post", return_value=mock_response) as mock_post:
            auth_data = adapter.start_authorization(self.conn, mode="Device Code")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        url = call_args.kwargs.get("url") or call_args.args[0]
        self.assertEqual(url, "https://auth.kimi.com/api/oauth/device_authorization")
        call_kwargs = call_args.kwargs
        self.assertEqual(call_kwargs["data"]["client_id"], "17e5f671-d194-4dfb-9706-5516cb48c098")

        self.assertEqual(auth_data["user_code"], "USER123")
        self.assertEqual(auth_data["device_code"], "dev_123")
        self.assertEqual(self.conn.auth_status, "Pending Authorization")

    @patch("huf.ai.providers.adapters.kimi_community.time.sleep")
    def test_complete_authorization_polls_and_stores_tokens(self, mock_sleep):
        adapter = get_adapter(self.conn.adapter_type)
        adapter.start_authorization(self.conn, mode="Device Code")

        pending_response = MagicMock()
        pending_response.status_code = 400
        pending_response.json.return_value = {"error": "authorization_pending"}
        pending_response.text = '{"error": "authorization_pending"}'

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "access_token": "access_123",
            "refresh_token": "refresh_123",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch(
            "huf.ai.providers.adapters.kimi_community.requests.post",
            side_effect=[pending_response, success_response],
        ) as mock_post:
            result = adapter.complete_authorization(self.conn, {"device_code": "dev_123", "interval": 5, "expires_in": 1800})

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.conn.auth_status, "Active")
        self.assertEqual(self.conn.get_decrypted_access_token(), "access_123")
        self.assertEqual(self.conn.get_decrypted_refresh_token(), "refresh_123")

    @patch("huf.ai.providers.adapters.kimi_community.time.sleep")
    def test_refresh_connection(self, mock_sleep):
        adapter = get_adapter(self.conn.adapter_type)
        self.conn.set_tokens("access_123", "refresh_123", expires_in_seconds=3600)
        self.conn.auth_status = "Active"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "access_token": "access_789",
            "refresh_token": "refresh_789",
            "expires_in": 3600,
            "token_type": "Bearer",
        })
        mock_response.json.return_value = {
            "access_token": "access_789",
            "refresh_token": "refresh_789",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("huf.ai.providers.adapters.kimi_community.requests.post", return_value=mock_response) as mock_post:
            success = adapter.refresh_connection(self.conn)

        self.assertTrue(success)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(call_kwargs["data"]["client_id"], "17e5f671-d194-4dfb-9706-5516cb48c098")
        self.assertEqual(self.conn.get_decrypted_refresh_token(), "refresh_789")

    def test_kimi_headers_match_cli_fingerprint(self):
        adapter = get_adapter(self.conn.adapter_type)
        headers = adapter._get_headers(self.conn)
        self.assertTrue(headers["User-Agent"].startswith("KimiCLI/"))
        self.assertEqual(headers["X-Msh-Platform"], "kimi_cli")
        self.assertEqual(headers["X-Msh-Version"], "1.41.0")
        self.assertIn("X-Msh-Device-Id", headers)
        self.assertIn("X-Msh-Device-Model", headers)

    def test_run_builds_chat_completions_request(self):
        adapter = get_adapter(self.conn.adapter_type)
        self.conn.set_tokens("access_123", "refresh_123", expires_in_seconds=3600)
        self.conn.auth_status = "Active"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from Kimi"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("huf.ai.providers.adapters.kimi_community.requests.post", return_value=mock_response) as mock_post:
            result = adapter.run(
                connection_doc=self.conn,
                agent=None,
                enhanced_prompt="Hi",
                model="kimi-for-coding",
                context={"session_id": "sess_abc"},
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        url = call_args.kwargs.get("url") or call_args.args[0]
        self.assertEqual(url, "https://api.kimi.com/coding/v1/chat/completions")
        call_kwargs = call_args.kwargs
        self.assertEqual(call_kwargs["json"]["model"], "kimi-for-coding")
        self.assertEqual(call_kwargs["json"]["prompt_cache_key"], "sess_abc")
        self.assertEqual(call_kwargs["headers"]["User-Agent"], "KimiCLI/1.41.0")
        self.assertEqual(result["response"], "Hello from Kimi")

    def test_discover_models_falls_back_to_default(self):
        adapter = get_adapter(self.conn.adapter_type)
        models = adapter.discover_models(self.conn)
        self.assertTrue(any(m["id"] == "kimi-for-coding" for m in models))

    def test_revoke_connection(self):
        adapter = get_adapter(self.conn.adapter_type)
        self.conn.set_tokens("access", "refresh", expires_in_seconds=3600)
        success = adapter.revoke_connection(self.conn)
        self.assertTrue(success)
        self.assertEqual(self.conn.auth_status, "Revoked")
        self.assertEqual(self.conn.get_decrypted_access_token(), "")
