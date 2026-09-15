"""
Unit tests for Remote Agent Adapter Service (Phase 3).
"""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import requests

from huf.ai.remote_agents.adapter import (
    AgentClientProtocolAdapter,
    AgentCommunicationProtocolAdapter,
    HufNativeAdapter,
    RemoteAgentAdapter,
    RemoteAgentAdapterError,
    RemoteAgentAuthError,
    RemoteAgentConnectionError,
    RemoteAgentNotImplementedError,
    RemoteAgentResponseError,
    RemoteAgentTimeoutError,
    get_adapter,
    validate_remote_url,
)


class TestRemoteUrlValidation(unittest.TestCase):
    @patch("huf.ai.remote_agents.adapter.socket.getaddrinfo")
    def test_valid_http_and_https(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("93.184.216.34", 80))]
        is_valid, err = validate_remote_url("https://example.com/api", allow_local_network=False)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_invalid_scheme(self):
        is_valid, err = validate_remote_url("ftp://example.com/api", allow_local_network=False)
        self.assertFalse(is_valid)
        self.assertIn("HTTP and HTTPS", err)

    def test_missing_hostname(self):
        is_valid, err = validate_remote_url("http://", allow_local_network=False)
        self.assertFalse(is_valid)
        self.assertIn("missing hostname", err)

    @patch("huf.ai.remote_agents.adapter.socket.getaddrinfo")
    def test_ssrf_blocks_private_ips(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("127.0.0.1", 80))
        ]
        is_valid, err = validate_remote_url("http://localhost/api", allow_local_network=False)
        self.assertFalse(is_valid)
        self.assertIn("private/internal addresses are not allowed", err)

    @patch("huf.ai.remote_agents.adapter.socket.getaddrinfo")
    def test_ssrf_allows_private_ips_when_configured(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("127.0.0.1", 80))
        ]
        is_valid, err = validate_remote_url("http://localhost/api", allow_local_network=True)
        self.assertTrue(is_valid)
        self.assertIsNone(err)


class TestHufNativeAdapterAuth(unittest.TestCase):
    def test_bearer_token_header(self):
        adapter = HufNativeAdapter(
            base_url="https://remote.example.com",
            auth_type="bearer_token",
            auth_secret="my-token",
        )
        headers = adapter._get_headers()
        self.assertEqual(headers.get("Authorization"), "Bearer my-token")

    def test_site_token_header(self):
        adapter = HufNativeAdapter(
            base_url="https://remote.example.com",
            auth_type="site_token",
            auth_secret="site-secret-123",
        )
        headers = adapter._get_headers()
        self.assertEqual(headers.get("X-Site-Token"), "site-secret-123")

    def test_api_key_header(self):
        adapter = HufNativeAdapter(
            base_url="https://remote.example.com",
            auth_type="api_key",
            auth_secret="key:secret",
        )
        headers = adapter._get_headers()
        self.assertEqual(headers.get("Authorization"), "token key:secret")

    def test_custom_headers_merged(self):
        adapter = HufNativeAdapter(
            base_url="https://remote.example.com",
            auth_type="bearer_token",
            auth_secret="token",
            headers={"X-Custom-Header": "custom-val"},
        )
        headers = adapter._get_headers()
        self.assertEqual(headers.get("Authorization"), "Bearer token")
        self.assertEqual(headers.get("X-Custom-Header"), "custom-val")


class TestHufNativeAdapterFromConfig(unittest.TestCase):
    def test_from_dict_config(self):
        cfg = {
            "base_url": "https://remote.example.com",
            "auth_type": "bearer_token",
            "auth_secret": "sec123",
            "timeout": 45,
            "allow_local_network": True,
        }
        adapter = HufNativeAdapter.from_config(cfg)
        self.assertEqual(adapter.base_url, "https://remote.example.com")
        self.assertEqual(adapter.auth_type, "bearer_token")
        self.assertEqual(adapter.auth_secret, "sec123")
        self.assertEqual(adapter.timeout, 45)
        self.assertTrue(adapter.allow_local_network)

    def test_from_object_config(self):
        cfg = SimpleNamespace(
            base_url="https://remote.example.com",
            auth_type="api_key",
            api_key="key:sec",
            timeout=15,
            allow_local_ips=True,
        )
        adapter = HufNativeAdapter.from_config(cfg)
        self.assertEqual(adapter.base_url, "https://remote.example.com")
        self.assertEqual(adapter.auth_type, "api_key")
        self.assertEqual(adapter.auth_secret, "key:sec")
        self.assertEqual(adapter.timeout, 15)
        self.assertTrue(adapter.allow_local_network)


class TestHufNativeAdapterOperations(unittest.TestCase):
    def setUp(self):
        self.adapter = HufNativeAdapter(
            base_url="https://remote.example.com",
            auth_type="bearer_token",
            auth_secret="test-secret",
            allow_local_network=True,
        )

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_fetch_manifest_success(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"message": {"server_name": "Test Server", "agents": [{"id": "agent_1"}]}}'
        mock_resp.json.return_value = {
            "message": {
                "server_name": "Test Server",
                "agents": [{"id": "agent_1"}],
            }
        }
        mock_request.return_value = mock_resp

        manifest = self.adapter.fetch_manifest()

        self.assertEqual(manifest["server_name"], "Test Server")
        self.assertEqual(manifest["protocol_version"], "huf-native-v1")
        self.assertEqual(len(manifest["agents"]), 1)
        self.assertEqual(manifest["agents"][0]["id"], "agent_1")

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_fetch_manifest_fallback_to_well_known(self, mock_request, mock_val):
        resp_404 = MagicMock()
        resp_404.status_code = 404

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.content = b'{"server_name": "Fallback Server", "agents": []}'
        resp_200.json.return_value = {"server_name": "Fallback Server", "agents": []}

        mock_request.side_effect = [resp_404, resp_200]

        manifest = self.adapter.fetch_manifest()

        self.assertEqual(manifest["server_name"], "Fallback Server")
        self.assertEqual(mock_request.call_count, 2)
        self.assertIn(".well-known/huf-agent.json", mock_request.call_args_list[1].kwargs["url"])

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_create_run_success(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"message": {"run_id": "run_001", "status": "completed", "response": "Done"}}'
        mock_resp.json.return_value = {
            "message": {"run_id": "run_001", "status": "completed", "response": "Done"}
        }
        mock_request.return_value = mock_resp

        res = self.adapter.create_run("agent_1", {"prompt": "Hello"})

        self.assertEqual(res["run_id"], "run_001")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["response"], "Done")

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_get_run_success(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"message": {"status": "running", "response": "In progress"}}'
        mock_resp.json.return_value = {
            "message": {"status": "running", "response": "In progress"}
        }
        mock_request.return_value = mock_resp

        res = self.adapter.get_run("run_001")

        self.assertEqual(res["run_id"], "run_001")
        self.assertEqual(res["status"], "running")
        self.assertEqual(res["response"], "In progress")

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_get_events_success(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"message": {"events": [{"type": "message.delta"}], "cursor": "c2", "has_more": true}}'
        mock_resp.json.return_value = {
            "message": {
                "events": [{"type": "message.delta"}],
                "cursor": "c2",
                "has_more": True,
            }
        }
        mock_request.return_value = mock_resp

        res = self.adapter.get_events("run_001", cursor="c1")

        self.assertEqual(res["run_id"], "run_001")
        self.assertEqual(len(res["events"]), 1)
        self.assertEqual(res["cursor"], "c2")
        self.assertTrue(res["has_more"])

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_cancel_run_success(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"message": {"status": "cancelled", "message": "Stopped"}}'
        mock_resp.json.return_value = {
            "message": {"status": "cancelled", "message": "Stopped"}
        }
        mock_request.return_value = mock_resp

        res = self.adapter.cancel_run("run_001")

        self.assertEqual(res["run_id"], "run_001")
        self.assertEqual(res["status"], "cancelled")
        self.assertEqual(res["message"], "Stopped")


class TestHufNativeAdapterErrors(unittest.TestCase):
    def setUp(self):
        self.adapter = HufNativeAdapter(
            base_url="https://remote.example.com",
            auth_type="bearer_token",
            auth_secret="test-secret",
            allow_local_network=True,
        )

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request", side_effect=requests.exceptions.Timeout("Connection timed out"))
    def test_timeout_raises_remote_agent_timeout_error(self, mock_request, mock_val):
        with self.assertRaises(RemoteAgentTimeoutError):
            self.adapter.get_run("run_001")

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request", side_effect=requests.exceptions.ConnectionError("DNS failure"))
    def test_connection_failure_raises_remote_agent_connection_error(self, mock_request, mock_val):
        with self.assertRaises(RemoteAgentConnectionError):
            self.adapter.get_run("run_001")

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_401_raises_remote_agent_auth_error(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_request.return_value = mock_resp

        with self.assertRaises(RemoteAgentAuthError):
            self.adapter.get_run("run_001")

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_500_raises_remote_agent_response_error(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_request.return_value = mock_resp

        with self.assertRaises(RemoteAgentResponseError) as ctx:
            self.adapter.get_run("run_001")
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("huf.ai.remote_agents.adapter.validate_remote_url", return_value=(True, None))
    @patch("requests.request")
    def test_invalid_json_raises_remote_agent_response_error(self, mock_request, mock_val):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"Not JSON content"
        mock_resp.text = "Not JSON content"
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_request.return_value = mock_resp

        with self.assertRaises(RemoteAgentResponseError):
            self.adapter.get_run("run_001")


class TestPlaceholderAdaptersAndFactory(unittest.TestCase):
    def test_acp_adapter_raises_not_implemented(self):
        adapter = AgentCommunicationProtocolAdapter("https://acp.example.com")
        self.assertIsInstance(adapter, RemoteAgentAdapter)
        with self.assertRaises(RemoteAgentNotImplementedError):
            adapter.fetch_manifest()

    def test_agent_client_protocol_adapter_raises_not_implemented(self):
        adapter = AgentClientProtocolAdapter("https://client.example.com")
        self.assertIsInstance(adapter, RemoteAgentAdapter)
        with self.assertRaises(RemoteAgentNotImplementedError):
            adapter.fetch_manifest()

    def test_get_adapter_huf_native(self):
        adapter = get_adapter("huf_native", base_url="https://remote.example.com")
        self.assertIsInstance(adapter, HufNativeAdapter)

    def test_get_adapter_acp(self):
        adapter = get_adapter("agent_communication_protocol", base_url="https://acp.example.com")
        self.assertIsInstance(adapter, AgentCommunicationProtocolAdapter)

    def test_get_adapter_client_protocol(self):
        adapter = get_adapter("agent_client_protocol", base_url="https://acp.example.com")
        self.assertIsInstance(adapter, AgentClientProtocolAdapter)

    def test_get_adapter_unknown_protocol(self):
        with self.assertRaises(ValueError):
            get_adapter("unknown_protocol", base_url="https://example.com")


if __name__ == "__main__":
    unittest.main()
