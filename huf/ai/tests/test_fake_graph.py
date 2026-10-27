# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Unit tests for the in-process fake Graph API (no network, no frappe site needed)."""

from __future__ import annotations

import unittest

import requests

from huf.testing.fake_graph import FakeGraph

MESSAGES_URL = "https://graph.facebook.com/v21.0/1234567890/messages"


class FakeGraphTest(unittest.TestCase):
	def test_post_messages_records_call_and_numbers_wamids(self):
		graph = FakeGraph()
		first = graph.post(
			MESSAGES_URL,
			json={"to": "15551234567", "type": "text"},
			headers={"Authorization": "Bearer test"},
			timeout=15,
		)
		second = graph.post(f"{MESSAGES_URL}?access_token=redacted", json={"to": "15557654321"})

		self.assertEqual(first.status_code, 200)
		self.assertEqual(first.json(), {"messages": [{"id": "wamid.FAKE1"}]})
		self.assertEqual(second.json()["messages"][0]["id"], "wamid.FAKE2")

		self.assertEqual(len(graph.calls), 2)
		self.assertEqual(graph.calls[0]["method"], "POST")
		self.assertEqual(graph.calls[0]["url"], MESSAGES_URL)
		self.assertEqual(graph.calls[0]["body"]["to"], "15551234567")
		self.assertEqual(graph.calls[0]["timeout"], 15)
		self.assertEqual(len(graph.sent_messages()), 2)

	def test_window_closed_returns_meta_error_131047(self):
		graph = FakeGraph(window_closed=True)
		response = graph.post(MESSAGES_URL, json={"to": "15551234567"})

		self.assertEqual(response.status_code, 400)
		error = response.json()["error"]
		self.assertEqual(error["code"], 131047)
		self.assertIn("Re-engagement", error["message"])
		with self.assertRaises(requests.HTTPError):
			response.raise_for_status()

	def test_rate_limited_returns_meta_error_131056(self):
		graph = FakeGraph(rate_limited=True)
		response = graph.post(MESSAGES_URL, json={"to": "15551234567"})

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["error"]["code"], 131056)
		self.assertEqual(len(graph.sent_messages()), 1)

	def test_non_message_requests_always_succeed(self):
		graph = FakeGraph(window_closed=True, rate_limited=True)
		upload = graph.post(
			"https://graph.facebook.com/v21.0/1234567890/media", json={"messaging_product": "whatsapp"}
		)
		templates = graph.get("https://graph.facebook.com/v21.0/9876543210/message_templates")

		self.assertEqual(upload.json(), {"success": True})
		self.assertEqual(templates.json(), {"success": True})
		self.assertEqual(graph.sent_messages(), [])

		not_a_send = graph.post(f"{MESSAGES_URL}_status", json={})
		self.assertEqual(not_a_send.status_code, 200)

	def test_window_closed_wins_and_reset_clears_state(self):
		graph = FakeGraph(window_closed=True, rate_limited=True)
		self.assertEqual(graph.post(MESSAGES_URL, json={}).json()["error"]["code"], 131047)

		graph.window_closed = False
		self.assertEqual(graph.post(MESSAGES_URL, json={}).json()["error"]["code"], 131056)

		graph.rate_limited = False
		graph.reset()
		self.assertEqual(graph.calls, [])
		self.assertEqual(graph.post(MESSAGES_URL, json={}).json()["messages"][0]["id"], "wamid.FAKE1")

	def test_subscribed_apps_get_then_post_subscribe(self):
		graph = FakeGraph(app_id="fake-app-1")
		url = "https://graph.facebook.com/v21.0/200000000000002/subscribed_apps"

		empty = graph.get(url)
		subscribed = graph.post(url)
		listed = graph.get(url)

		self.assertEqual(empty.json(), {"data": [], "paging": {}})
		self.assertEqual(subscribed.json(), {"success": True})
		entries = listed.json()["data"]
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0]["whatsapp_business_api_data"]["id"], "fake-app-1")
		self.assertEqual(entries[0]["subscribed_fields"], ["messages"])
		self.assertEqual([c["method"] for c in graph.calls], ["GET", "POST", "GET"])

	def test_register_phone_number_records_call(self):
		graph = FakeGraph()
		url = "https://graph.facebook.com/v21.0/1234567890/register"

		response = graph.post(url, json={"messaging_product": "whatsapp"})

		self.assertEqual(response.json(), {"success": True})
		self.assertEqual(graph.calls[0]["method"], "POST")
		self.assertEqual(graph.calls[0]["url"], url)
		self.assertEqual(graph.calls[0]["body"], {"messaging_product": "whatsapp"})

	def test_debug_token_reports_configured_validity_and_expiry(self):
		graph = FakeGraph(token_valid=True, token_expires_at=1_900_000_000)

		response = graph.get(
			"https://graph.facebook.com/v21.0/debug_token",
			params={"input_token": "fake-input-token", "access_token": "fake-app|fake-secret"},
		)

		data = response.json()["data"]
		self.assertTrue(data["is_valid"])
		self.assertEqual(data["expires_at"], 1_900_000_000)
		self.assertNotIn("error", data)

	def test_debug_token_invalid_reports_meta_error(self):
		graph = FakeGraph(token_valid=False)

		data = graph.get(
			"https://graph.facebook.com/v21.0/debug_token", params={"input_token": "fake-input-token"}
		).json()["data"]

		self.assertFalse(data["is_valid"])
		self.assertEqual(data["error"]["code"], 190)

	def test_rate_limited_can_emit_cloud_api_code_130429(self):
		graph = FakeGraph(rate_limited=True, rate_limit_code=130429)

		response = graph.post(MESSAGES_URL, json={"to": "15551234567"})

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()["error"]["code"], 130429)
		self.assertIn("Cloud API", response.json()["error"]["message"])

	def test_phone_details_expose_configurable_health_status(self):
		graph = FakeGraph(health_status="LIMITED")
		url = "https://graph.facebook.com/v21.0/1234567890"

		self.assertEqual(graph.get(url).json(), {"id": "1234567890", "health_status": "LIMITED"})

		graph.health_status = "AVAILABLE"
		self.assertEqual(graph.get(url).json()["health_status"], "AVAILABLE")


if __name__ == "__main__":
	unittest.main()
