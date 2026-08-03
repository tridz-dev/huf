import json
import unittest
import asyncio
import frappe
from frappe.utils import now_datetime, add_to_date
from huf.huf.doctype.ai_provider_connection.ai_provider_connection import AIProviderConnection
from huf.ai.providers.adapters import get_adapter
from huf.ai.providers.adapters.mock import MockSubscriptionAdapter
from huf.ai.run import RunProvider


class TestSubscriptionAdapterMock(unittest.TestCase):
    def setUp(self):
        # Create test AI Provider if needed
        if not frappe.db.exists("AI Provider", "MockProvider"):
            provider_doc = frappe.get_doc({
                "doctype": "AI Provider",
                "provider_name": "MockProvider",
                "provider_brand": "other",
                "api_key": "mock-api-key"
            })
            provider_doc.insert(ignore_permissions=True)

        # Cleanup existing connection if any
        if frappe.db.exists("AI Provider Connection", "Test Mock Subscription"):
            frappe.delete_doc("AI Provider Connection", "Test Mock Subscription", force=True)

        # Create AI Provider Connection
        self.conn = frappe.get_doc({
            "doctype": "AI Provider Connection",
            "connection_name": "Test Mock Subscription",
            "user": "Administrator",
            "provider": "MockProvider",
            "adapter_type": "mock_subscription",
            "auth_status": "Unlinked",
            "auth_method": "OAuth PKCE",
            "is_active": 1,
            "eligible_models": json.dumps(["mock-sub-gpt-4o", "mock-sub-gemini-2"])
        })
        self.conn.insert(ignore_permissions=True)

    def tearDown(self):
        if frappe.db.exists("AI Provider Connection", "Test Mock Subscription"):
            frappe.delete_doc("AI Provider Connection", "Test Mock Subscription", force=True)

    def test_adapter_registry(self):
        adapter = get_adapter("mock_subscription")
        self.assertIsInstance(adapter, MockSubscriptionAdapter)

    def test_authorization_flow(self):
        adapter = get_adapter(self.conn.adapter_type)
        auth_data = adapter.start_authorization(self.conn, mode="OAuth PKCE")
        self.assertIn("auth_url", auth_data)

        res = adapter.complete_authorization(self.conn, {"code": "mock_auth_code_123"})
        self.assertEqual(res["status"], "success")
        self.assertEqual(self.conn.auth_status, "Active")
        self.assertEqual(self.conn.get_decrypted_access_token(), "mock_access_token_abc123")
        self.assertEqual(self.conn.get_decrypted_refresh_token(), "mock_refresh_token_xyz789")

    def test_token_expiry_and_refresh(self):
        adapter = get_adapter(self.conn.adapter_type)
        adapter.complete_authorization(self.conn, {"code": "mock_code"})
        self.conn.save(ignore_permissions=True)

        self.assertFalse(self.conn.is_expired(buffer_seconds=300))

        # Simulate near expiry
        self.conn.expires_at = add_to_date(now_datetime(), seconds=100)
        self.assertTrue(self.conn.is_expired(buffer_seconds=300))

        # Test refresh
        refreshed = self.conn.check_and_refresh()
        self.assertTrue(refreshed)
        self.assertEqual(self.conn.get_decrypted_access_token(), "refreshed_mock_access_token_999")
        self.assertEqual(self.conn.auth_status, "Active")

    def test_refresh_failure_invalid_token(self):
        adapter = get_adapter(self.conn.adapter_type)
        adapter.complete_authorization(self.conn, {"code": "mock_code"})
        self.conn.set_tokens("access", "invalid_refresh_token", expires_in_seconds=-10)
        self.conn.save(ignore_permissions=True)

        refreshed = self.conn.check_and_refresh()
        self.assertFalse(refreshed)
        self.assertEqual(self.conn.auth_status, "Expired")

    def test_run_provider_routing_subscription(self):
        adapter = get_adapter(self.conn.adapter_type)
        adapter.complete_authorization(self.conn, {"code": "mock_code"})
        self.conn.save(ignore_permissions=True)

        context = {"subscription_connection_name": self.conn.name}
        res = RunProvider.run(
            agent=None,
            enhanced_prompt="Hello agent",
            provider="MockProvider",
            model="mock-sub-gpt-4o",
            context=context
        )

        self.assertIn("Mock Subscription Output", res.final_output)
        self.assertEqual(res.metadata.get("adapter_type"), "mock_subscription")

    def test_run_provider_routing_streaming_subscription(self):
        adapter = get_adapter(self.conn.adapter_type)
        adapter.complete_authorization(self.conn, {"code": "mock_code"})
        self.conn.save(ignore_permissions=True)

        context = {"subscription_connection_name": self.conn.name}

        async def _consume_stream():
            stream = RunProvider.run_stream(
                agent=None,
                enhanced_prompt="Hello agent streaming",
                provider="MockProvider",
                model="mock-sub-gpt-4o",
                context=context
            )
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_consume_stream())
        self.assertGreater(len(chunks), 1)
        full_text = "".join([c["content"] for c in chunks if c.get("type") == "delta"])
        self.assertIn("[Mock Subscription Stream Chunk]", full_text)

    def test_revoke_connection(self):
        adapter = get_adapter(self.conn.adapter_type)
        adapter.complete_authorization(self.conn, {"code": "mock_code"})

        success = adapter.revoke_connection(self.conn)
        self.assertTrue(success)
        self.assertEqual(self.conn.auth_status, "Revoked")
        self.assertEqual(self.conn.get_decrypted_access_token(), "")
