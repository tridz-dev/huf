"""Tests for Gateway Guided Setup and Pairing Tools."""

import unittest
import frappe
from huf.ai.tools.gateway_pairing_tools import (
    setup_gateway,
    list_pairing_requests,
    approve_pairing_code,
    test_gateway_health,
)


class TestGatewayPairingTools(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")

    def test_setup_gateway_validation_failure(self):
        res = setup_gateway("Telegram", "Invalid Bot", {})
        self.assertFalse(res["success"])
        self.assertIn("required", res["error"])

    def test_setup_gateway_success(self):
        test_gw = "Test Telegram Bot"
        res = setup_gateway(
            provider="Telegram",
            gateway_name=test_gw,
            credentials={"bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"},
            direct_policy="Pairing",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["gateway_name"], test_gw)
        self.assertIn("handle_gateway_webhook", res["webhook_url"])

        # Clean up
        frappe.db.delete("Gateway", {"name": test_gw})
        frappe.db.delete("Integration Settings", {"integration_name": f"Integration-{test_gw}"})

    def test_pairing_request_lifecycle(self):
        gw_name = "Test Pairing Gateway"
        setup_gateway(
            provider="Telegram",
            gateway_name=gw_name,
            credentials={"bot_token": "987654321:ABCdefGHIjklMNOpqrsTUVwxyz"},
            direct_policy="Pairing",
        )

        from huf.ai.gateway_service import _create_pairing_request

        gw_doc = frappe.get_doc("Gateway", gw_name)
        code = _create_pairing_request(gw_doc, sender_id="user_12345")
        self.assertTrue(code.startswith("PAIR-"))

        pending = list_pairing_requests(gw_name)
        self.assertTrue(any(p["pairing_code"] == code for p in pending))

        approval = approve_pairing_code(code, notes="Approved during automated test")
        self.assertTrue(approval["success"])
        self.assertEqual(approval["state"], "Approved")

        # Cleanup
        frappe.db.delete("Gateway Access Entry", {"gateway": gw_name})
        frappe.db.delete("Gateway", {"name": gw_name})
        frappe.db.delete("Integration Settings", {"integration_name": f"Integration-{gw_name}"})

    def test_gateway_health_check(self):
        gw_name = "Health Check Bot"
        setup_gateway(
            provider="Telegram",
            gateway_name=gw_name,
            credentials={"bot_token": "111222333:ABCdefGHIjklMNOpqrsTUVwxyz"},
        )

        health = test_gateway_health(gw_name)
        self.assertTrue(health["success"])
        self.assertEqual(health["report"]["provider"], "Telegram")

        # Cleanup
        frappe.db.delete("Gateway", {"name": gw_name})
        frappe.db.delete("Integration Settings", {"integration_name": f"Integration-{gw_name}"})


if __name__ == "__main__":
    unittest.main()
