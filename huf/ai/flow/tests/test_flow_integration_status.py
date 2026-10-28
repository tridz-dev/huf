"""get_flow_integration_status reports connection state per integration without leaking credentials."""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from huf.ai.flow import integrations
from huf.ai.flow.integrations import get_flow_integration_status, service_for_tool


class TestFlowIntegrationStatus(FrappeTestCase):
	def test_tool_to_service(self):
		self.assertEqual(service_for_tool("slack_send_message"), "slack")
		self.assertEqual(service_for_tool("gmail_send_email"), "gmail")
		self.assertEqual(service_for_tool("gdrive_list_files"), "google_drive")
		self.assertEqual(service_for_tool("gsheets_read"), "google_sheets")
		self.assertIsNone(service_for_tool("http_request"))

	def test_connected_requires_every_credential(self):
		def fake(service, key, default=None):
			return "x" if (service, key) in {("slack", "token"), ("gmail", "client_id")} else None

		with patch.object(integrations, "get_credential", fake):
			status = get_flow_integration_status()
		self.assertTrue(status["slack"]["connected"])
		self.assertFalse(status["gmail"]["connected"])  # only one of three keys
		self.assertFalse(status["google_sheets"]["connected"])
		self.assertEqual(status["slack"]["label"], "Slack")
