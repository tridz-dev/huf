# Copyright (c) 2026, Huf and Contributors
# See license.txt

import sys
import types
import unittest
from unittest.mock import MagicMock

# Mock frappe before importing the resolver so pure helpers can be tested
# without a full Frappe bench.
frappe_mock = types.ModuleType("frappe")
frappe_mock.utils = MagicMock()
frappe_mock.utils.get_url = MagicMock(return_value="https://huf.example.com")
frappe_mock.has_permission = MagicMock(return_value=True)
frappe_mock.get_doc = MagicMock()
frappe_mock.session = MagicMock()
frappe_mock.session.user = "Administrator"
frappe_mock.local = MagicMock()
frappe_mock.local.site = "huf.example.com"
frappe_mock.cache = MagicMock()
frappe_mock.db = MagicMock()
frappe_mock.log_error = MagicMock()
frappe_mock.throw = MagicMock(side_effect=Exception("Permission denied"))
frappe_mock._ = lambda x: x
frappe_mock.whitelist = MagicMock(return_value=lambda fn: fn)
if "frappe" not in sys.modules:
    sys.modules["frappe"] = frappe_mock

from huf.ai.mcp_connection_resolver import (
    _canonical_resource,
    _is_safe_url,
    _normalize_url,
    _parse_www_authenticate,
    _resources_match,
)


class TestMCPConnectionResolver(unittest.TestCase):
    def test_normalize_url_adds_https(self):
        self.assertEqual(_normalize_url("mcp.example.com/mcp"), "https://mcp.example.com/mcp")

    def test_normalize_url_preserves_https(self):
        self.assertEqual(
            _normalize_url("https://mcp.example.com/mcp"),
            "https://mcp.example.com/mcp",
        )

    def test_is_safe_url_rejects_private_ips(self):
        self.assertFalse(_is_safe_url("http://192.168.1.1/mcp"))
        self.assertFalse(_is_safe_url("http://10.0.0.1/mcp"))

    def test_is_safe_url_allows_localhost_for_development(self):
        self.assertTrue(_is_safe_url("http://localhost/mcp"))
        self.assertTrue(_is_safe_url("http://127.0.0.1/mcp"))

    def test_is_safe_url_allows_public_https(self):
        self.assertTrue(_is_safe_url("https://mcp.higgsfield.ai/mcp"))

    def test_is_safe_url_rejects_non_http(self):
        self.assertFalse(_is_safe_url("ftp://example.com/mcp"))

    def test_parse_www_authenticate_bearer_with_resource_metadata(self):
        header = 'Bearer resource_metadata="https://example.com/.well-known/oauth-protected-resource"'
        challenges = _parse_www_authenticate(header)
        self.assertEqual(len(challenges), 1)
        self.assertEqual(challenges[0]["scheme"], "Bearer")
        self.assertEqual(
            challenges[0]["resource_metadata"],
            "https://example.com/.well-known/oauth-protected-resource",
        )

    def test_parse_www_authenticate_multiple_challenges(self):
        header = 'Bearer realm="api", Basic realm="mcp"'
        challenges = _parse_www_authenticate(header)
        self.assertEqual(len(challenges), 2)
        self.assertEqual(challenges[0]["scheme"], "Bearer")
        self.assertEqual(challenges[0]["realm"], "api")
        self.assertEqual(challenges[1]["scheme"], "Basic")
        self.assertEqual(challenges[1]["realm"], "mcp")

    def test_resources_match_tolerates_trailing_slash(self):
        self.assertTrue(_resources_match("https://example.com/mcp", "https://example.com/mcp/"))

    def test_canonical_resource_lowercases(self):
        self.assertEqual(_canonical_resource("HTTPS://Example.COM/MCP"), "https://example.com/mcp")


if __name__ == "__main__":
    unittest.main()
