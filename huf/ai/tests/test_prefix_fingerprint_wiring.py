# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for prefix fingerprint wiring verification:

  - compute_prefix_breakpoints is called with the new optional kwargs
  - the kwargs produce the expected breakpoints and hashes
  - hashes remain stable across identical inputs
  - nothing breaks when optional values are unavailable
  - all four markers (tools, system, static_prefix, latest_user) can be present
"""

import sys
import os
import unittest
from unittest.mock import MagicMock
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.context_segments import compute_prefix_breakpoints  # noqa: E402


class TestPrefixFingerprintWiringFunctionality(unittest.TestCase):
    """Test that the new kwargs to compute_prefix_breakpoints work correctly."""

    def setUp(self):
        """Set up common test data."""
        self.agent_doc = {
            "name": "Test Agent",
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            "model": "claude-3-5-sonnet-20241022",
            "provider": "anthropic",
            # Auto places the dynamic/history breakpoint only for Agents that can
            # run a multi-round tool loop, so this fixture carries a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }

        self.agent = MagicMock()
        self.agent.name = "Test Agent"
        self.agent.instructions = "You are a helpful assistant."
        self.agent.tools = [
            MagicMock(
                name="get_weather",
                description="Get the weather",
                parameters={"type": "object", "properties": {"location": {"type": "string"}}},
            )
        ]

        self.resolved_model_name = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        self.prompt = "What is the weather in Paris?"

    def test_breakpoints_with_all_new_kwargs(self):
        """Test that breakpoints include tools, static_prefix, and latest_user markers."""
        tools_schema = [
            {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {"type": "object"},
            }
        ]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            static_prefix="Platform context",
            latest_user=self.prompt,
        )

        markers = [bp["marker"] for bp in result]

        # Should have all expected markers
        self.assertIn("instructions", markers)
        self.assertIn("history", markers)
        self.assertIn("tools", markers)
        self.assertIn("static_prefix", markers)
        self.assertIn("latest_user", markers)

        # Should have exactly 5 breakpoints
        self.assertEqual(len(result), 5)

        # Each breakpoint should have required keys
        for bp in result:
            self.assertIn("marker", bp)
            self.assertIn("prefix_hash", bp)
            self.assertIsNotNone(bp["prefix_hash"])

    def test_breakpoint_hashes_stable_across_runs(self):
        """Test that identical inputs produce identical hashes."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            static_prefix="Static context",
            latest_user="User query",
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            static_prefix="Static context",
            latest_user="User query",
        )

        # Extract hashes
        def get_hash_by_marker(breakpoints, marker):
            for bp in breakpoints:
                if bp["marker"] == marker:
                    return bp["prefix_hash"]
            return None

        # All hashes should be identical across runs
        for marker in ["instructions", "history", "tools", "static_prefix", "latest_user"]:
            hash1 = get_hash_by_marker(result1, marker)
            hash2 = get_hash_by_marker(result2, marker)
            if hash1 is not None and hash2 is not None:
                self.assertEqual(hash1, hash2, f"Hash for {marker} should be stable")

    def test_changing_tool_schema_changes_hash(self):
        """Test that changing tools schema changes the tools marker hash."""
        tools_schema1 = [{"name": "tool1", "description": "desc1"}]
        tools_schema2 = [{"name": "tool1", "description": "desc2"}]
        tools_json1 = json.dumps(tools_schema1, separators=(",", ":"), sort_keys=True)
        tools_json2 = json.dumps(tools_schema2, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json1,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json2,
        )

        hash1 = [bp for bp in result1 if bp["marker"] == "tools"][0]["prefix_hash"]
        hash2 = [bp for bp in result2 if bp["marker"] == "tools"][0]["prefix_hash"]

        # Tool schema change should produce different hash
        self.assertNotEqual(hash1, hash2)

    def test_instructions_unchanged_when_tools_change(self):
        """Test that instructions marker is unaffected when tools change."""
        tools_schema1 = [{"name": "tool1", "description": "desc1"}]
        tools_schema2 = [{"name": "tool1", "description": "desc2"}]
        tools_json1 = json.dumps(tools_schema1, separators=(",", ":"), sort_keys=True)
        tools_json2 = json.dumps(tools_schema2, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json1,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json2,
        )

        instructions_hash1 = [bp for bp in result1 if bp["marker"] == "instructions"][0]["prefix_hash"]
        instructions_hash2 = [bp for bp in result2 if bp["marker"] == "instructions"][0]["prefix_hash"]

        # Instructions should be unchanged
        self.assertEqual(instructions_hash1, instructions_hash2)

    def test_no_raise_with_missing_optional_values(self):
        """Test that the function doesn't raise when optional values are missing."""
        agent_no_tools = MagicMock()
        agent_no_tools.instructions = "Instructions"
        agent_no_tools.tools = None

        # Should not raise
        try:
            result = compute_prefix_breakpoints(
                self.agent_doc,
                agent_no_tools,
                self.resolved_model_name,
                self.resolved_provider,
                self.history,
                tools=None,
                static_prefix=None,
                latest_user=None,
            )
            # Should return at least the instructions breakpoint
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
        except Exception as e:
            self.fail(f"compute_prefix_breakpoints raised {type(e).__name__}: {e}")

    def test_agent_without_tools_still_produces_breakpoints(self):
        """An agent with no tools still produces the non-dynamic breakpoints."""
        agent_no_tools = MagicMock()
        agent_no_tools.instructions = "You are helpful"
        agent_no_tools.tools = None

        # The Auto gate reads the Agent doc, not the runtime tool list: HUF
        # attaches an internal-capability tool to every agent, so agent.tools is
        # never empty in production.
        agent_doc_no_tools = {
            k: v for k, v in self.agent_doc.items() if k != "agent_tool"
        }

        result = compute_prefix_breakpoints(
            agent_doc_no_tools,
            agent_no_tools,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=None,
            static_prefix="Platform context",
            latest_user="Query",
        )

        markers = [bp["marker"] for bp in result]

        # Should have instructions, static_prefix, and latest_user
        self.assertIn("instructions", markers)
        self.assertIn("static_prefix", markers)
        self.assertIn("latest_user", markers)

        # Should NOT have tools
        self.assertNotIn("tools", markers)

        # No history/dynamic breakpoint: Auto only places the moving boundary for
        # Agents that can run a multi-round tool loop. For a tool-less Agent the
        # entry is written every call and read back never (measured: cache_read
        # pinned at the system prefix across four consecutive calls).
        self.assertNotIn("history", markers)

    def test_empty_static_prefix_no_breakpoint(self):
        """Test that empty static_prefix doesn't produce a breakpoint."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            static_prefix="",
            latest_user="Query",
        )

        markers = [bp["marker"] for bp in result]

        # Should NOT have static_prefix when empty
        self.assertNotIn("static_prefix", markers)

    def test_none_latest_user_no_breakpoint(self):
        """Test that None latest_user doesn't produce a breakpoint."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            static_prefix="Platform context",
            latest_user=None,
        )

        markers = [bp["marker"] for bp in result]

        # Should NOT have latest_user when None
        self.assertNotIn("latest_user", markers)

    def test_tools_as_dict_also_works(self):
        """Test that tools can be passed as dict (not just JSON string)."""
        tools_dict = [{"name": "tool1", "description": "desc"}]

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            tools=tools_dict,
        )

        markers = [bp["marker"] for bp in result]

        # Should still produce tools marker
        self.assertIn("tools", markers)

    def test_latest_user_as_content_blocks(self):
        """Test that latest_user can be passed as content blocks (not just string)."""
        content_blocks = [
            {"type": "text", "text": "Part 1 "},
            {"type": "text", "text": "Part 2"},
        ]

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model_name,
            self.resolved_provider,
            self.history,
            latest_user=content_blocks,
        )

        markers = [bp["marker"] for bp in result]

        # Should produce latest_user marker
        self.assertIn("latest_user", markers)


if __name__ == "__main__":
    unittest.main()
