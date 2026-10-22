"""Unit tests: flow approval flag, OAuth refresh lock ownership, unique MCP server lookup."""

import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai import mcp_oauth  # noqa: E402


class FakeCache:
	def __init__(self):
		self.store = {}

	def set(self, key, value, ex=None, nx=False):
		if nx and key in self.store:
			return False
		self.store[key] = value
		return True

	def get(self, key):
		return self.store.get(key)

	def delete(self, key):
		self.store.pop(key, None)


class TestRefreshLock(unittest.TestCase):
	def test_lock_value_is_unique_and_not_deleted_if_taken_over(self):
		cache = FakeCache()
		key = mcp_oauth._refresh_lock_key("S")
		seen = {}

		def steal_lock(name):
			seen["value"] = cache.store[key]
			cache.store[key] = "someone-else"  # TTL expired, another caller acquired it
			return "new"

		with patch.object(mcp_oauth.frappe, "cache", return_value=cache), \
				patch.object(mcp_oauth, "_read_access_token", side_effect=["old", "old"]), \
				patch.object(mcp_oauth, "_refresh_oauth_token_unlocked", side_effect=steal_lock):
			self.assertEqual(mcp_oauth.refresh_oauth_token("S"), "new")
		self.assertNotEqual(seen["value"], 1)
		self.assertEqual(cache.store[key], "someone-else")

	def test_lock_released_when_still_owned(self):
		cache = FakeCache()
		with patch.object(mcp_oauth.frappe, "cache", return_value=cache), \
				patch.object(mcp_oauth, "_read_access_token", side_effect=["old", "old"]), \
				patch.object(mcp_oauth, "_refresh_oauth_token_unlocked", return_value="new"):
			mcp_oauth.refresh_oauth_token("S")
		self.assertEqual(cache.store, {})


class TestFlowAndInvocation(unittest.TestCase):
	def test_schema_allows_approved_on_tool_call(self):
		import json
		schema = json.loads((pathlib.Path(mcp_oauth.__file__).parent / "graph" / "graph_ir.schema.json").read_text())
		found = []

		def walk(n):
			if isinstance(n, dict):
				props = n.get("properties", {})
				if "tool_id" in props:
					found.append(props)
				for v in n.values():
					walk(v)
			elif isinstance(n, list):
				for v in n:
					walk(v)

		walk(schema)
		self.assertTrue(any("approved" in p for p in found))

	def test_telemetry_uses_unique_server_lookup(self):
		from huf.ai import tool_invocation
		ctx = MagicMock(call_id=None)
		with patch("huf.ai.mcp_client.find_unique_mcp_server_for_tool", return_value="SRV") as f, \
				patch.object(tool_invocation.frappe, "get_doc") as gd:
			tool_invocation._start_tool_call_telemetry("t", {}, ctx)
		f.assert_called_once_with("t")
		self.assertEqual(gd.call_args.args[0]["mcp_server"], "SRV")


if __name__ == "__main__":
	unittest.main()
