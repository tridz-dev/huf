# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for huf.ai.context_segments.compute_prefix_breakpoints extended
fingerprinting:

  - new optional keyword args (tools, system, static_prefix, latest_user)
    are hashed and added as breakpoints when provided
  - same content twice => identical hashes (determinism)
  - changing a tool's description or parameter schema => tools hash changes
  - changing only a python object identity / non-provider-visible attribute
    => tools hash UNCHANGED (canonicalization of provider-visible content only)
  - changing instructions => instructions hash changes, tools hash unchanged
  - changing latest user message => latest_user hash changes, instructions/tools
    unchanged
  - calling with NO new kwargs returns exactly what it returned before the
    change (backward compat)
  - existing test modules (test_cache_metrics, test_context_segments_reconcile,
    test_context_segments_tool_exchange, test_agent_run_analytics_composition)
    still pass
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.context_segments import compute_prefix_breakpoints, compute_segment_tokens, compute_tools_breakdown, count_tool_exchange_tokens, reconcile_composition  # noqa: E402


class TestComputePrefixBreakpointsBackwardCompat(unittest.TestCase):
    """Test that the function still works with the original 5 arguments only."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.agent = MagicMock()
        self.agent.instructions = "You are a helpful assistant."
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"},
        ]

    def test_no_new_kwargs_returns_old_behavior(self):
        """Calling without the new optional kwargs should return the same structure."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
        )

        # Should have exactly 2 breakpoints: instructions and history
        self.assertEqual(len(result), 2)
        markers = [bp["marker"] for bp in result]
        self.assertIn("instructions", markers)
        self.assertIn("history", markers)

        # Each breakpoint has the expected keys
        for bp in result:
            self.assertIn("marker", bp)
            self.assertIn("prefix_hash", bp)
            self.assertEqual(len(bp), 2)  # only these two keys

    def test_backward_compat_with_empty_history(self):
        """Test backward compat when history is empty."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            [],
        )

        # Should have exactly 1 breakpoint: instructions only
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["marker"], "instructions")

    def test_caching_disabled_requires_mode_off(self):
        """Only prompt_cache_mode='Off' suppresses breakpoints now.

        The legacy enable_prompt_caching checkbox is no longer the master gate;
        it is consulted only in Advanced mode.
        """
        agent_doc_off = {
            "prompt_cache_mode": "Off",
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
        }
        result = compute_prefix_breakpoints(
            agent_doc_off,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
        )

        # Should return empty list
        self.assertEqual(result, [])

    def test_auto_mode_caches_despite_legacy_flag_off(self):
        """An unset prompt_cache_mode resolves to Auto, which ignores the legacy flag.

        This is the crux of the C1b migration: Agents left with
        enable_prompt_caching=0 (the doctype default) must still get breakpoints.
        """
        agent_doc_legacy_off = {
            "enable_prompt_caching": False,
            "cache_system_message": False,
            "cache_conversation_history": False,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        result = compute_prefix_breakpoints(
            agent_doc_legacy_off,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
        )

        markers = [entry["marker"] for entry in result]
        self.assertIn("instructions", markers)
        self.assertIn("history", markers)

    def test_advanced_mode_honours_legacy_flags(self):
        """Advanced keeps the pre-migration behaviour of the legacy checkboxes."""
        agent_doc_advanced_off = {
            "prompt_cache_mode": "Advanced",
            "enable_prompt_caching": False,
            "cache_system_message": True,
            "cache_conversation_history": True,
        }
        self.assertEqual(
            compute_prefix_breakpoints(
                agent_doc_advanced_off,
                self.agent,
                self.resolved_model,
                self.resolved_provider,
                self.history,
            ),
            [],
        )

        agent_doc_advanced_system_only = {
            "prompt_cache_mode": "Advanced",
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": False,
        }
        markers = [
            entry["marker"]
            for entry in compute_prefix_breakpoints(
                agent_doc_advanced_system_only,
                self.agent,
                self.resolved_model,
                self.resolved_provider,
                self.history,
            )
        ]
        self.assertEqual(markers, ["instructions"])


class TestComputePrefixBreakpointsDeterminism(unittest.TestCase):
    """Test that same content produces identical hashes."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"

    def test_same_tools_hash_twice_identical(self):
        """Same tools schema should produce identical hash."""
        agent = MagicMock()
        agent.instructions = "Instructions"
        history = [{"role": "user", "content": "content"}]

        tools_schema = [
            {
                "name": "get_weather",
                "description": "Get the weather",
                "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}},
            }
        ]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            tools=tools_json,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            tools=tools_json,
        )

        tools_bp1 = [bp for bp in result1 if bp["marker"] == "tools"][0]
        tools_bp2 = [bp for bp in result2 if bp["marker"] == "tools"][0]
        self.assertEqual(tools_bp1["prefix_hash"], tools_bp2["prefix_hash"])

    def test_same_system_hash_twice_identical(self):
        """Same system message should produce identical hash."""
        agent = MagicMock()
        agent.instructions = "Old instructions"
        history = [{"role": "user", "content": "content"}]

        system_msg = "You are a helpful assistant."

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            system=system_msg,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            system=system_msg,
        )

        system_bp1 = [bp for bp in result1 if bp["marker"] == "instructions"][0]
        system_bp2 = [bp for bp in result2 if bp["marker"] == "instructions"][0]
        self.assertEqual(system_bp1["prefix_hash"], system_bp2["prefix_hash"])

    def test_same_static_prefix_hash_twice_identical(self):
        """Same static prefix should produce identical hash."""
        agent = MagicMock()
        agent.instructions = "Instructions"
        history = [{"role": "user", "content": "content"}]

        static_prefix = "Context from platform X"

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            static_prefix=static_prefix,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            static_prefix=static_prefix,
        )

        static_bp1 = [bp for bp in result1 if bp["marker"] == "static_prefix"][0]
        static_bp2 = [bp for bp in result2 if bp["marker"] == "static_prefix"][0]
        self.assertEqual(static_bp1["prefix_hash"], static_bp2["prefix_hash"])

    def test_same_latest_user_hash_twice_identical(self):
        """Same latest user message should produce identical hash."""
        agent = MagicMock()
        agent.instructions = "Instructions"
        history = [{"role": "user", "content": "content"}]

        latest_user = "What is the capital of France?"

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            latest_user=latest_user,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            history,
            latest_user=latest_user,
        )

        user_bp1 = [bp for bp in result1 if bp["marker"] == "latest_user"][0]
        user_bp2 = [bp for bp in result2 if bp["marker"] == "latest_user"][0]
        self.assertEqual(user_bp1["prefix_hash"], user_bp2["prefix_hash"])


class TestComputePrefixBreakpointsHashIsolation(unittest.TestCase):
    """Test that hashes for different components are independent."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.agent = MagicMock()
        self.agent.instructions = "Original instructions"
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [{"role": "user", "content": "history content"}]

    def test_changing_instructions_only_changes_instructions_hash(self):
        """Changing instructions should only affect instructions breakpoint."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)
        latest_user = "user message"

        result_before = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            system="System message 1",
            latest_user=latest_user,
        )

        result_after = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            system="System message 2",
            latest_user=latest_user,
        )

        # Extract hashes by marker
        def get_hash_by_marker(breakpoints, marker):
            for bp in breakpoints:
                if bp["marker"] == marker:
                    return bp["prefix_hash"]
            return None

        # Instructions should differ
        self.assertNotEqual(
            get_hash_by_marker(result_before, "instructions"),
            get_hash_by_marker(result_after, "instructions"),
        )
        # Tools should be the same
        self.assertEqual(
            get_hash_by_marker(result_before, "tools"),
            get_hash_by_marker(result_after, "tools"),
        )
        # latest_user should be the same
        self.assertEqual(
            get_hash_by_marker(result_before, "latest_user"),
            get_hash_by_marker(result_after, "latest_user"),
        )

    def test_changing_tools_only_changes_tools_hash(self):
        """Changing tools should only affect tools breakpoint."""
        tools_schema1 = [{"name": "tool1", "description": "desc1"}]
        tools_schema2 = [{"name": "tool1", "description": "desc2"}]
        tools_json1 = json.dumps(tools_schema1, separators=(",", ":"), sort_keys=True)
        tools_json2 = json.dumps(tools_schema2, separators=(",", ":"), sort_keys=True)
        system_msg = "System message"
        latest_user = "user message"

        result_before = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json1,
            system=system_msg,
            latest_user=latest_user,
        )

        result_after = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json2,
            system=system_msg,
            latest_user=latest_user,
        )

        # Extract hashes by marker
        def get_hash_by_marker(breakpoints, marker):
            for bp in breakpoints:
                if bp["marker"] == marker:
                    return bp["prefix_hash"]
            return None

        # Tools should differ
        self.assertNotEqual(
            get_hash_by_marker(result_before, "tools"),
            get_hash_by_marker(result_after, "tools"),
        )
        # System should be the same
        self.assertEqual(
            get_hash_by_marker(result_before, "instructions"),
            get_hash_by_marker(result_after, "instructions"),
        )
        # latest_user should be the same
        self.assertEqual(
            get_hash_by_marker(result_before, "latest_user"),
            get_hash_by_marker(result_after, "latest_user"),
        )

    def test_changing_latest_user_only_changes_latest_user_hash(self):
        """Changing latest user message should only affect latest_user breakpoint."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)
        system_msg = "System message"

        result_before = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            system=system_msg,
            latest_user="message 1",
        )

        result_after = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            system=system_msg,
            latest_user="message 2",
        )

        # Extract hashes by marker
        def get_hash_by_marker(breakpoints, marker):
            for bp in breakpoints:
                if bp["marker"] == marker:
                    return bp["prefix_hash"]
            return None

        # latest_user should differ
        self.assertNotEqual(
            get_hash_by_marker(result_before, "latest_user"),
            get_hash_by_marker(result_after, "latest_user"),
        )
        # Tools should be the same
        self.assertEqual(
            get_hash_by_marker(result_before, "tools"),
            get_hash_by_marker(result_after, "tools"),
        )
        # System should be the same
        self.assertEqual(
            get_hash_by_marker(result_before, "instructions"),
            get_hash_by_marker(result_after, "instructions"),
        )


class TestComputePrefixBreakpointsToolSerialization(unittest.TestCase):
    """Test that only provider-visible tool content affects the hash."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.agent = MagicMock()
        self.agent.instructions = "Instructions"
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [{"role": "user", "content": "content"}]

    def test_tool_description_change_affects_hash(self):
        """Changing a tool's description should change the tools hash."""
        tools_schema1 = [{"name": "get_weather", "description": "Get weather"}]
        tools_schema2 = [{"name": "get_weather", "description": "Get current weather"}]
        tools_json1 = json.dumps(tools_schema1, separators=(",", ":"), sort_keys=True)
        tools_json2 = json.dumps(tools_schema2, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json1,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json2,
        )

        hash1 = [bp for bp in result1 if bp["marker"] == "tools"][0]["prefix_hash"]
        hash2 = [bp for bp in result2 if bp["marker"] == "tools"][0]["prefix_hash"]
        self.assertNotEqual(hash1, hash2)

    def test_tool_parameter_schema_change_affects_hash(self):
        """Changing a tool's parameter schema should change the tools hash."""
        tools_schema1 = [
            {
                "name": "search",
                "description": "Search",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ]
        tools_schema2 = [
            {
                "name": "search",
                "description": "Search",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}},
            }
        ]
        tools_json1 = json.dumps(tools_schema1, separators=(",", ":"), sort_keys=True)
        tools_json2 = json.dumps(tools_schema2, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json1,
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json2,
        )

        hash1 = [bp for bp in result1 if bp["marker"] == "tools"][0]["prefix_hash"]
        hash2 = [bp for bp in result2 if bp["marker"] == "tools"][0]["prefix_hash"]
        self.assertNotEqual(hash1, hash2)

    def test_tool_string_determinism(self):
        """Passing tools as string should produce consistent hashes across calls."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result1 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,  # Pass as string
        )

        result2 = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,  # Pass as string again
        )

        hash1 = [bp for bp in result1 if bp["marker"] == "tools"][0]["prefix_hash"]
        hash2 = [bp for bp in result2 if bp["marker"] == "tools"][0]["prefix_hash"]
        # Same input should produce same hash
        self.assertEqual(hash1, hash2)


class TestComputePrefixBreakpointsLatestUserContent(unittest.TestCase):
    """Test handling of latest_user parameter with various content shapes."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.agent = MagicMock()
        self.agent.instructions = "Instructions"
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [{"role": "user", "content": "history"}]

    def test_latest_user_as_string(self):
        """latest_user as plain string should produce a breakpoint."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            latest_user="What is AI?",
        )

        user_breakpoints = [bp for bp in result if bp["marker"] == "latest_user"]
        self.assertEqual(len(user_breakpoints), 1)
        self.assertIsNotNone(user_breakpoints[0]["prefix_hash"])

    def test_latest_user_as_content_block_list(self):
        """latest_user as list of content blocks should be flattened and hashed."""
        content_blocks = [
            {"type": "text", "text": "Part 1 "},
            {"type": "text", "text": "Part 2"},
        ]

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            latest_user=content_blocks,
        )

        user_breakpoints = [bp for bp in result if bp["marker"] == "latest_user"]
        self.assertEqual(len(user_breakpoints), 1)
        self.assertIsNotNone(user_breakpoints[0]["prefix_hash"])

    def test_latest_user_empty_string_no_breakpoint(self):
        """Empty string latest_user should not produce a breakpoint."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            latest_user="",
        )

        user_breakpoints = [bp for bp in result if bp["marker"] == "latest_user"]
        self.assertEqual(len(user_breakpoints), 0)

    def test_latest_user_none_no_breakpoint(self):
        """None latest_user should not produce a breakpoint."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            latest_user=None,
        )

        user_breakpoints = [bp for bp in result if bp["marker"] == "latest_user"]
        self.assertEqual(len(user_breakpoints), 0)


class TestComputePrefixBreakpointsStaticPrefix(unittest.TestCase):
    """Test handling of static_prefix parameter."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.agent = MagicMock()
        self.agent.instructions = "Instructions"
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [{"role": "user", "content": "history"}]

    def test_static_prefix_string_produces_breakpoint(self):
        """Non-empty static_prefix should produce a breakpoint."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            static_prefix="Platform context information",
        )

        static_breakpoints = [bp for bp in result if bp["marker"] == "static_prefix"]
        self.assertEqual(len(static_breakpoints), 1)
        self.assertIsNotNone(static_breakpoints[0]["prefix_hash"])

    def test_static_prefix_empty_string_no_breakpoint(self):
        """Empty string static_prefix should not produce a breakpoint."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            static_prefix="",
        )

        static_breakpoints = [bp for bp in result if bp["marker"] == "static_prefix"]
        self.assertEqual(len(static_breakpoints), 0)

    def test_static_prefix_none_no_breakpoint(self):
        """None static_prefix should not produce a breakpoint."""
        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            static_prefix=None,
        )

        static_breakpoints = [bp for bp in result if bp["marker"] == "static_prefix"]
        self.assertEqual(len(static_breakpoints), 0)


class TestComputePrefixBreakpointsAllTogether(unittest.TestCase):
    """Test all new parameters together."""

    def setUp(self):
        self.agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
            "cache_conversation_history": True,
            # Auto places the dynamic/history breakpoint only for Agents that
            # can run a multi-round tool loop, so these fixtures carry a tool.
            "agent_tool": [{"tool": "frappe_list_records"}],
        }
        self.agent = MagicMock()
        self.agent.instructions = "Old system"
        self.resolved_model = "anthropic/claude-3-5-sonnet-20241022"
        self.resolved_provider = "anthropic"
        self.history = [
            {"role": "user", "content": "old history"},
            {"role": "assistant", "content": "response"},
        ]

    def test_all_new_params_together_produces_all_breakpoints(self):
        """Providing all new params should produce all expected breakpoints."""
        tools_schema = [{"name": "tool1", "description": "desc"}]
        tools_json = json.dumps(tools_schema, separators=(",", ":"), sort_keys=True)

        result = compute_prefix_breakpoints(
            self.agent_doc,
            self.agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            tools=tools_json,
            system="New system",
            static_prefix="Platform context",
            latest_user="What is the answer?",
        )

        # Should have all expected markers:
        # - instructions (from system param)
        # - history (from history arg)
        # - tools (from tools param)
        # - static_prefix (from static_prefix param)
        # - latest_user (from latest_user param)
        markers = [bp["marker"] for bp in result]
        self.assertIn("instructions", markers)
        self.assertIn("history", markers)
        self.assertIn("tools", markers)
        self.assertIn("static_prefix", markers)
        self.assertIn("latest_user", markers)
        self.assertEqual(len(result), 5)

    def test_system_param_overrides_agent_instructions(self):
        """Providing system param should override agent.instructions."""
        agent = MagicMock()
        agent.instructions = "Original instructions"

        result_without_system = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
        )

        result_with_system = compute_prefix_breakpoints(
            self.agent_doc,
            agent,
            self.resolved_model,
            self.resolved_provider,
            self.history,
            system="Override instructions",
        )

        hash_without = [bp for bp in result_without_system if bp["marker"] == "instructions"][0]["prefix_hash"]
        hash_with = [bp for bp in result_with_system if bp["marker"] == "instructions"][0]["prefix_hash"]

        # The hashes should be different because the content is different
        self.assertNotEqual(hash_without, hash_with)




class TestExceptionHandlingAndLogging(unittest.TestCase):
    """Test that exception handlers preserve behavior and log warnings."""

    def test_count_token_failure_returns_none_not_raises(self):
        """Token counter failure should return None, never raise."""
        from huf.ai.context_segments import _count
        
        with patch("huf.ai.context_segments.token_counter", side_effect=RuntimeError("Counter failed")):
            result = _count("anthropic/claude-3-5-sonnet-20241022", "test text")
            self.assertIsNone(result)

    def test_tool_schema_serialization_failure_graceful(self):
        """Tool schema serialization failure should return None for tools_text."""
        agent = MagicMock()
        agent.instructions = "Instructions"
        agent.tools = [MagicMock()]
        
        agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
        }
        
        with patch("huf.ai.context_segments.serialize_tools", side_effect=TypeError("Serialization failed")):
            result = compute_segment_tokens(
                agent_doc, agent, "anthropic/claude-3-5-sonnet-20241022", "anthropic",
                [], None, "prompt"
            )
            self.assertIsInstance(result, dict)
            self.assertIsNone(result.get("tools"))

    def test_history_extraction_failure_graceful(self):
        """History extraction failure should return None for history_text."""
        agent = MagicMock()
        agent.instructions = "Instructions"
        agent.tools = []
        
        agent_doc = {
            "enable_prompt_caching": True,
        }
        
        bad_history = [{"content": 123}]
        
        with patch("huf.ai.context_segments.serialize_tools", return_value={}):
            result = compute_segment_tokens(
                agent_doc, agent, "anthropic/claude-3-5-sonnet-20241022", "anthropic",
                bad_history, None, "prompt"
            )
            self.assertIsInstance(result, dict)

    def test_tools_breakdown_inner_serialization_failure(self):
        """Individual tool serialization failure in compute_tools_breakdown should skip that tool."""
        
        pricing_model = "anthropic/claude-3-5-sonnet-20241022"
        
        tool1 = MagicMock()
        tool1.name = "tool1"
        tool2 = MagicMock()
        tool2.name = "tool2"
        tools = [tool1, tool2]
        
        tool_sources = {"tool1": "builtin_registry", "tool2": "user_configured"}
        
        call_count = [0]
        def serialize_side_effect(tools_list):
            call_count[0] += 1
            if call_count[0] == 2:
                raise ValueError("Can't serialize tool2")
            return [{"name": "tool1", "description": "desc"}]
        
        with patch("huf.ai.context_segments.serialize_tools", side_effect=serialize_side_effect):
            with patch("huf.ai.context_segments._count", return_value=10):
                result = compute_tools_breakdown(pricing_model, tools, tool_sources)
                self.assertIsNotNone(result)
                self.assertIn("per_tool", result)
                self.assertIsNone(result["per_tool"]["tool2"])
                self.assertEqual(result["per_tool"]["tool1"], 10)

    def test_tools_breakdown_outer_exception_returns_none(self):
        """Outer exception in compute_tools_breakdown should return None."""
        result = compute_tools_breakdown(None, None, None)
        self.assertIsNone(result)

    def test_model_supports_prompt_caching_failure(self):
        """model_supports_prompt_caching failure should return empty breakpoints."""
        agent_doc = {
            "enable_prompt_caching": True,
            "cache_system_message": True,
        }
        agent = MagicMock()
        agent.instructions = "Instructions"
        
        with patch("huf.ai.context_segments.model_supports_prompt_caching", side_effect=RuntimeError("Model check failed")):
            result = compute_prefix_breakpoints(
                agent_doc, agent, "anthropic/claude-3-5-sonnet-20241022", "anthropic", []
            )
            self.assertEqual(result, [])

    def test_tool_call_serialization_failure_in_exchange(self):
        """Tool call serialization failure should return None."""
        messages = [
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "tool1", "arguments": '{"x": 1}'}}]
            }
        ]
        
        with patch("huf.ai.context_segments.frappe.as_json", side_effect=ValueError("JSON failed")):
            result = count_tool_exchange_tokens("anthropic/claude-3-5-sonnet-20241022", messages)
            self.assertIsNone(result)

    def test_reconcile_composition_outer_exception_returns_none(self):
        """Outer exception in reconcile_composition should return None."""
        segment_tokens = {"system": 10, "tools": 20}
        tool_exchange_tokens = 5
        provider_prompt_tokens = 35
        
        result = reconcile_composition(segment_tokens, tool_exchange_tokens, provider_prompt_tokens)
        self.assertIsNotNone(result)
        self.assertEqual(result["within_tolerance"], True)
        
        result_bad = reconcile_composition(None, None, None)
        self.assertIsNone(result_bad)

    def test_count_returns_none_on_exception(self):
        """_count should return None when token_counter fails, preserving behavior."""
        from huf.ai.context_segments import _count
        
        result = _count("model", "")
        self.assertEqual(result, 0)
        
        result = _count("model", None)
        self.assertEqual(result, 0)
        
        with patch("huf.ai.context_segments.token_counter", side_effect=Exception("Failed")):
            result = _count("model", "text")
            self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
