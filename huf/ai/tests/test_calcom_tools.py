# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Cal.com integration tools. All HTTP calls are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import calcom
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, CALCOM_TOOLS

MODULE = "huf.ai.tools.calcom"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.text = json.dumps(payload)
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


class TestListBookings(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="cal_live_key")
	@patch(f"{MODULE}.requests.request")
	def test_lists_bookings(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"bookings": [
					{
						"uid": "b1",
						"title": "1:1",
						"startTime": "2026-08-10T15:00:00Z",
						"endTime": "2026-08-10T15:30:00Z",
						"status": "accepted",
						"attendees": [{"email": "a@example.com"}],
					}
				]
			}
		)

		out = _result(calcom.handle_list_bookings(status="upcoming"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["uid"], "b1")

		params = mock_request.call_args.kwargs["params"]
		self.assertEqual(params["apiKey"], "cal_live_key")
		self.assertEqual(params["status"], "upcoming")


class TestGetBooking(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="cal_live_key")
	@patch(f"{MODULE}.requests.request")
	def test_get_booking(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"booking": {
					"uid": "b1",
					"title": "1:1",
					"description": "sync",
					"startTime": "2026-08-10T15:00:00Z",
					"endTime": "2026-08-10T15:30:00Z",
					"status": "accepted",
					"attendees": [{"email": "a@example.com"}],
				}
			}
		)

		out = _result(calcom.handle_get_booking(booking_uid="b1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["attendees"], ["a@example.com"])

	def test_requires_booking_uid(self):
		out = _result(calcom.handle_get_booking())
		self.assertFalse(out["success"])
		self.assertIn("booking_uid", out["error"])


class TestCreateBooking(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="cal_live_key")
	@patch(f"{MODULE}.requests.request")
	def test_creates_booking(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{"booking": {"uid": "b2", "title": "New", "startTime": "2026-08-10T15:00:00Z", "status": "accepted"}}
		)

		out = _result(
			calcom.handle_create_booking(
				event_type_id=42,
				start="2026-08-10T15:00:00Z",
				attendee_name="Jane",
				attendee_email="jane@example.com",
			)
		)

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["uid"], "b2")

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["eventTypeId"], 42)
		self.assertEqual(body["responses"], {"name": "Jane", "email": "jane@example.com"})
		self.assertEqual(body["timeZone"], "UTC")

	def test_requires_all_fields(self):
		out = _result(calcom.handle_create_booking(event_type_id=42))
		self.assertFalse(out["success"])
		self.assertIn("start", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"calcom_list_bookings": "handle_list_bookings",
			"calcom_get_booking": "handle_get_booking",
			"calcom_create_booking": "handle_create_booking",
		}
		by_name = {t["tool_name"]: t for t in CALCOM_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.calcom.{handler}")
			self.assertTrue(callable(getattr(calcom, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in CALCOM_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "calcom")


if __name__ == "__main__":
	unittest.main()
