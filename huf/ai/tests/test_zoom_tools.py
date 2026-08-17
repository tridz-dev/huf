# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Zoom integration tools (Server-to-Server OAuth). All HTTP calls
and Frappe cache access are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import zoom
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, ZOOM_TOOLS

MODULE = "huf.ai.tools.zoom"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.text = json.dumps(payload)
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


def _fake_credential(service, key):
	return {"account_id": "acct-1", "client_id": "cid", "client_secret": "csecret"}[key]


class TestAccessTokenCaching(unittest.TestCase):
	@patch(f"{MODULE}.frappe")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.post")
	def test_fetches_and_caches_token_on_miss(self, mock_post, _cred, mock_frappe):
		cache = MagicMock()
		cache.get_value.return_value = None
		mock_frappe.cache.return_value = cache
		mock_post.return_value = _mock_response({"access_token": "tok-1", "expires_in": 3600})

		token = zoom._get_access_token()

		self.assertEqual(token, "tok-1")
		mock_post.assert_called_once()
		self.assertEqual(mock_post.call_args.kwargs["auth"], ("cid", "csecret"))
		cache.set_value.assert_called_once_with("zoom_s2s_access_token", "tok-1", expires_in_sec=3540)

	@patch(f"{MODULE}.frappe")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.post")
	def test_cache_hit_skips_oauth_call(self, mock_post, _cred, mock_frappe):
		cache = MagicMock()
		cache.get_value.return_value = "cached-tok"
		mock_frappe.cache.return_value = cache

		token = zoom._get_access_token()

		self.assertEqual(token, "cached-tok")
		mock_post.assert_not_called()


class TestListMeetings(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}._get_access_token", return_value="tok-1")
	@patch(f"{MODULE}.requests.request")
	def test_lists_meetings(self, mock_request, _token, _err):
		mock_request.return_value = _mock_response(
			{
				"meetings": [
					{
						"id": 123,
						"topic": "Weekly sync",
						"start_time": "2026-08-10T15:00:00Z",
						"duration": 30,
						"join_url": "https://zoom.us/j/123",
					}
				]
			}
		)

		out = _result(zoom.handle_list_meetings())

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["id"], 123)

		headers = mock_request.call_args.kwargs["headers"]
		self.assertEqual(headers["Authorization"], "Bearer tok-1")


class TestGetMeeting(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}._get_access_token", return_value="tok-1")
	@patch(f"{MODULE}.requests.request")
	def test_get_meeting(self, mock_request, _token, _err):
		mock_request.return_value = _mock_response(
			{
				"id": 123,
				"topic": "Weekly sync",
				"agenda": "",
				"start_time": "2026-08-10T15:00:00Z",
				"duration": 30,
				"timezone": "UTC",
				"join_url": "https://zoom.us/j/123",
				"host_email": "host@example.com",
			}
		)

		out = _result(zoom.handle_get_meeting(meeting_id=123))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["host_email"], "host@example.com")

	def test_requires_meeting_id(self):
		out = _result(zoom.handle_get_meeting())
		self.assertFalse(out["success"])
		self.assertIn("meeting_id", out["error"])


class TestCreateMeeting(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}._get_access_token", return_value="tok-1")
	@patch(f"{MODULE}.requests.request")
	def test_creates_scheduled_meeting(self, mock_request, _token, _err):
		mock_request.return_value = _mock_response(
			{"id": 456, "topic": "Kickoff", "join_url": "https://zoom.us/j/456", "start_url": "https://zoom.us/s/456"}
		)

		out = _result(zoom.handle_create_meeting(topic="Kickoff", start_time="2026-08-10T15:00:00Z", duration=45))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["id"], 456)

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["type"], 2)
		self.assertEqual(body["duration"], 45)

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}._get_access_token", return_value="tok-1")
	@patch(f"{MODULE}.requests.request")
	def test_instant_meeting_when_no_start_time(self, mock_request, _token, _err):
		mock_request.return_value = _mock_response({"id": 789, "topic": "Now", "join_url": "x", "start_url": "y"})

		zoom.handle_create_meeting(topic="Now")

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["type"], 1)
		self.assertNotIn("start_time", body)

	def test_requires_topic(self):
		out = _result(zoom.handle_create_meeting())
		self.assertFalse(out["success"])
		self.assertIn("topic", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"zoom_list_meetings": "handle_list_meetings",
			"zoom_get_meeting": "handle_get_meeting",
			"zoom_create_meeting": "handle_create_meeting",
		}
		by_name = {t["tool_name"]: t for t in ZOOM_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.zoom.{handler}")
			self.assertTrue(callable(getattr(zoom, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in ZOOM_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "zoom")


if __name__ == "__main__":
	unittest.main()
