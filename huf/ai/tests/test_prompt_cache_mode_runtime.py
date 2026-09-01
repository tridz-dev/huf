# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Runtime tests for Agent.prompt_cache_mode as the authoritative cache gate.

Covers:
1. Mode resolution — Auto caches even when the legacy enable_prompt_caching
   checkbox is 0; Off bypasses even when the legacy checkbox is 1; Advanced
   preserves the pre-migration legacy-flag behaviour; a missing/blank/unknown
   mode resolves to Auto and never to Off.
2. Sync/stream parity — run() and run_stream() are driven with the identical
   agent_doc and conversation and must produce byte-identical message payloads
   (and therefore identical cache_control marker placement) in every mode.
"""

import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from huf.ai.providers.litellm import (
    PROMPT_CACHE_MODE_ADVANCED,
    PROMPT_CACHE_MODE_AUTO,
    PROMPT_CACHE_MODE_OFF,
    _resolve_cache_settings,
    resolve_prompt_cache_mode,
)


def _agent_doc(mode=None, **legacy):
    doc = {
        "enable_prompt_caching": 0,
        "cache_control_type": "ephemeral",
        "cache_system_message": 0,
        "cache_conversation_history": 0,
    }
    doc.update(legacy)
    if mode is not None:
        doc["prompt_cache_mode"] = mode
    return doc


class TestResolvePromptCacheMode(unittest.TestCase):
    """Normalisation of the raw Select value."""

    def test_known_values(self):
        self.assertEqual(resolve_prompt_cache_mode({"prompt_cache_mode": "Auto"}), PROMPT_CACHE_MODE_AUTO)
        self.assertEqual(resolve_prompt_cache_mode({"prompt_cache_mode": "Off"}), PROMPT_CACHE_MODE_OFF)
        self.assertEqual(
            resolve_prompt_cache_mode({"prompt_cache_mode": "Advanced"}), PROMPT_CACHE_MODE_ADVANCED
        )

    def test_case_and_whitespace_insensitive(self):
        for raw in ("off", " OFF ", "Off"):
            self.assertEqual(resolve_prompt_cache_mode({"prompt_cache_mode": raw}), PROMPT_CACHE_MODE_OFF)
        self.assertEqual(
            resolve_prompt_cache_mode({"prompt_cache_mode": "advanced"}), PROMPT_CACHE_MODE_ADVANCED
        )

    def test_missing_blank_and_unknown_resolve_to_auto_never_off(self):
        """The migration patch leaves prompt_cache_mode NULL on Agents that had no
        legacy caching data. Resolving NULL to Off would silently switch caching
        off for exactly those rows."""
        for raw in (None, "", "   ", "nonsense", 0, False, []):
            with self.subTest(raw=raw):
                self.assertEqual(
                    resolve_prompt_cache_mode({"prompt_cache_mode": raw}), PROMPT_CACHE_MODE_AUTO
                )
        self.assertEqual(resolve_prompt_cache_mode({}), PROMPT_CACHE_MODE_AUTO)
        self.assertEqual(resolve_prompt_cache_mode(None), PROMPT_CACHE_MODE_AUTO)

    def test_reads_attribute_when_doc_has_no_get(self):
        doc = SimpleNamespace(prompt_cache_mode="Off")
        self.assertEqual(resolve_prompt_cache_mode(doc), PROMPT_CACHE_MODE_OFF)


class TestResolveCacheSettings(unittest.TestCase):
    """Effective per-segment gates produced from the mode."""

    def test_auto_caches_despite_legacy_flag_zero(self):
        """The crux of the migration."""
        settings = _resolve_cache_settings(_agent_doc("Auto", enable_prompt_caching=0))
        self.assertTrue(settings.enabled)
        self.assertTrue(settings.cache_system_message)
        self.assertTrue(settings.cache_static_prefix)
        self.assertEqual(settings.cache_control_type, "ephemeral")


    def test_missing_mode_behaves_exactly_like_auto(self):
        self.assertEqual(
            _resolve_cache_settings(_agent_doc(None, enable_prompt_caching=0)).as_dict(),
            _resolve_cache_settings(_agent_doc("Auto", enable_prompt_caching=0)).as_dict(),
        )

    def test_auto_ignores_legacy_per_segment_flags(self):
        """Legacy checkboxes must not gate anything in Auto mode."""
        all_off = _resolve_cache_settings(
            _agent_doc(
                "Auto",
                enable_prompt_caching=0,
                cache_system_message=0,
                cache_conversation_history=0,
                cache_control_type="auto",
            )
        )
        all_on = _resolve_cache_settings(
            _agent_doc(
                "Auto",
                enable_prompt_caching=1,
                cache_system_message=1,
                cache_conversation_history=1,
            )
        )
        self.assertEqual(all_off.as_dict(), all_on.as_dict())

    def test_off_bypasses_despite_legacy_flag_one(self):
        settings = _resolve_cache_settings(
            _agent_doc(
                "Off",
                enable_prompt_caching=1,
                cache_system_message=1,
                cache_conversation_history=1,
            ),
            {"cache_static_prefix": True, "cache_dynamic_content": True},
        )
        self.assertFalse(settings.enabled)
        self.assertFalse(settings.cache_system_message)
        self.assertFalse(settings.cache_dynamic_content)
        self.assertFalse(settings.cache_static_prefix)
        self.assertFalse(
            settings.allow_provider_cache_params,
            "Off must set no cache-related provider kwargs either",
        )

    def test_advanced_respects_legacy_flags(self):
        off = _resolve_cache_settings(
            _agent_doc("Advanced", enable_prompt_caching=0, cache_system_message=1)
        )
        self.assertFalse(off.enabled)

        on = _resolve_cache_settings(
            _agent_doc(
                "Advanced",
                enable_prompt_caching=1,
                cache_system_message=1,
                cache_conversation_history=0,
                cache_control_type="auto",
            )
        )
        self.assertTrue(on.enabled)
        self.assertTrue(on.cache_system_message)
        self.assertFalse(on.cache_dynamic_content)
        self.assertEqual(on.cache_control_type, "auto")

    def test_advanced_respects_prompt_cache_options(self):
        settings = _resolve_cache_settings(
            _agent_doc("Advanced", enable_prompt_caching=1, cache_conversation_history=1),
            {"cache_dynamic_content": False, "cache_static_prefix": False},
        )
        self.assertTrue(settings.enabled)
        self.assertFalse(settings.cache_dynamic_content)
        self.assertFalse(settings.cache_static_prefix)

    def test_local_llm_disables_caching_in_every_mode(self):
        for mode in ("Auto", "Advanced", "Off", None):
            with self.subTest(mode=mode):
                settings = _resolve_cache_settings(
                    _agent_doc(mode, enable_prompt_caching=1, cache_system_message=1),
                    is_local_llm=True,
                )
                self.assertFalse(settings.enabled)

    def test_missing_agent_doc_defaults_to_auto(self):
        settings = _resolve_cache_settings(None)
        self.assertEqual(settings.mode, PROMPT_CACHE_MODE_AUTO)
        self.assertTrue(settings.enabled)


def _anthropic_cache_markers(messages):
    """Extract (role, index) of every cache_control marker in a message list."""
    markers = []
    for i, msg in enumerate(messages):
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    markers.append((i, msg.get("role"), block["cache_control"]))
    return markers


class TestSyncStreamParity(unittest.TestCase):
    """run() and run_stream() must place identical markers for identical input.

    A reviewer has previously caught sync/stream divergence in this module; both
    paths now resolve their gates through the single _resolve_cache_settings()
    helper, and this test is the executable proof.
    """

    CONVERSATION = [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
    ]

    def _mocks(self, agent_doc_fields):
        agent = Mock()
        agent.instructions = "You are a helpful assistant."
        agent.tools = None
        agent.max_turns = 5
        agent.model_settings = None

        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 1.0
        fields = dict(agent_doc_fields)
        fields.setdefault("reasoning_mode", None)
        fields.setdefault("reasoning_effort", None)
        fields.setdefault("reasoning_budget_tokens", None)
        fields.setdefault("reasoning_summary", None)
        agent_doc.get = Mock(side_effect=lambda key, default=None: fields.get(key, default))

        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)
        return agent, agent_doc, provider_doc

    def _frappe(self, mock_frappe, agent_doc, provider_doc):
        mock_frappe.get_doc = Mock(
            side_effect=lambda doctype, name: {
                "Agent": agent_doc,
                "AI Provider": provider_doc,
            }.get(doctype)
        )
        mock_frappe.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
        mock_frappe.has_permission = Mock(return_value=True)
        mock_frappe.session = Mock(user="test")
        mock_frappe.logger = Mock(return_value=Mock())

    def _messages_from_both_paths(self, agent_doc_fields):
        captured = {}

        patches = [
            patch("huf.ai.providers.litellm.frappe"),
            patch("huf.ai.providers.litellm._litellm_completion_with_retry"),
            patch("huf.ai.providers.litellm._resolve_api_key", return_value="test-key"),
            patch(
                "huf.ai.providers.litellm._normalize_model_name",
                return_value="anthropic/claude-haiku",
            ),
            patch("huf.ai.providers.litellm._resolve_api_base", return_value=None),
            patch(
                "huf.ai.providers.litellm.trim_messages",
                side_effect=lambda messages, model: messages,
            ),
            patch(
                "huf.ai.providers.litellm.repair_message_sequence",
                side_effect=lambda messages, conversation_name: messages,
            ),
            patch("huf.ai.providers.litellm.serialize_tools", return_value=None),
            patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True),
            patch(
                "huf.ai.providers.litellm.resolve_capabilities",
                return_value=Mock(min_cacheable_tokens=1),
            ),
            patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock()),
            patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={})),
            patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={}),
            patch(
                "huf.ai.providers.litellm.normalise_usage_payload",
                return_value={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                },
            ),
            patch(
                "huf.ai.providers.litellm.extract_round_usage",
                return_value={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                },
            ),
            patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test")),
        ]

        started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in patches])

        mock_frappe = started[0]
        mock_litellm = started[1]

        from huf.ai.providers.litellm import run, run_stream

        agent, agent_doc, provider_doc = self._mocks(agent_doc_fields)
        self._frappe(mock_frappe, agent_doc, provider_doc)

        context = {
            "agent_name": "TestAgent",
            "conversation_history": [dict(m) for m in self.CONVERSATION],
        }

        # --- sync path ---
        sync_response = Mock()
        sync_response.choices = [Mock()]
        sync_response.choices[0].message = Mock(
            content="Final answer", tool_calls=None, thinking_blocks=None, reasoning_content=None
        )
        sync_response.usage = Mock()

        def _sync_call(**kwargs):
            captured["sync"] = copy.deepcopy(kwargs.get("messages"))
            return sync_response

        mock_litellm.side_effect = _sync_call
        asyncio.run(run(agent, "latest question", "Anthropic", "claude-haiku", context=dict(context)))

        # --- streaming path ---
        delta1 = SimpleNamespace(
            content="Final", thinking_blocks=None, reasoning_content=None, tool_calls=None
        )
        chunk1 = SimpleNamespace(
            usage=None, choices=[SimpleNamespace(delta=delta1, finish_reason=None)]
        )
        delta2 = SimpleNamespace(
            content=None, thinking_blocks=None, reasoning_content=None, tool_calls=None
        )
        chunk2 = SimpleNamespace(
            usage=Mock(), choices=[SimpleNamespace(delta=delta2, finish_reason="stop")]
        )

        async def _stream_call(**kwargs):
            captured["stream"] = copy.deepcopy(kwargs.get("messages"))
            return [chunk1, chunk2]

        mock_litellm.side_effect = _stream_call

        async def _collect():
            async for _event in run_stream(
                agent, "latest question", "Anthropic", "claude-haiku", context=dict(context)
            ):
                pass

        asyncio.run(_collect())

        self.assertIn("sync", captured, "sync path never reached the completion call")
        self.assertIn("stream", captured, "stream path never reached the completion call")
        return captured["sync"], captured["stream"]

    def test_auto_mode_parity_and_markers_present(self):
        """A tool-capable Agent is ELIGIBLE for the dynamic (latest-user-turn)
        breakpoint (cache_dynamic_content=True from _resolve_cache_settings),
        but that breakpoint is additionally round-gated in run()/run_stream():
        it is attached only once round_num >= 1, i.e. once a second provider
        round is actually happening. `_messages_from_both_paths` drives a
        single-round turn (the mocked response never emits tool_calls), so
        round 0 is the only round that happens and it must carry the system
        breakpoint only — the dynamic marker never gets written for a turn
        that never loops.

        The round-gate mechanics themselves (marker absent at round 0,
        present from round 1 onward, identical between sync and stream) are
        covered end-to-end in test_cache_marker_placement.TestDynamicMarkerRoundGate.
        """
        sync, stream = self._messages_from_both_paths(
            {
                "prompt_cache_mode": "Auto",
                "enable_prompt_caching": 0,
                "agent_tool": [{"tool": "frappe_list_records"}],
            }
        )
        self.assertEqual(sync, stream, "sync and stream must build identical message payloads")

        markers = _anthropic_cache_markers(sync)
        self.assertTrue(
            markers,
            "Auto mode must place cache_control markers even with enable_prompt_caching=0",
        )
        roles = {role for _i, role, _c in markers}
        self.assertIn("system", roles)
        self.assertNotIn(
            "user",
            roles,
            "a single-round turn must never pay for the dynamic marker, even when "
            "the Agent is tool-capable (cache_dynamic_content=True) — it is only "
            "attached from round_num >= 1 onward",
        )
        # History must never carry a marker.
        for index, _role, _control in markers:
            self.assertNotIn(
                sync[index]["content"],
                [m["content"] for m in self.CONVERSATION],
            )

    def test_auto_mode_tool_less_agent_marks_system_only(self):
        """Without tools every turn is a single round, so the dynamic entry would
        be written each call and read back never. Auto drops it."""
        sync, stream = self._messages_from_both_paths(
            {"prompt_cache_mode": "Auto", "enable_prompt_caching": 0}
        )
        self.assertEqual(sync, stream, "sync and stream must build identical message payloads")

        markers = _anthropic_cache_markers(sync)
        self.assertEqual(
            [role for _i, role, _c in markers],
            ["system"],
            "a tool-less Auto Agent must carry exactly one, system-only, breakpoint",
        )

    def test_off_mode_parity_and_no_markers(self):
        sync, stream = self._messages_from_both_paths(
            {
                "prompt_cache_mode": "Off",
                "enable_prompt_caching": 1,
                "cache_system_message": 1,
                "cache_conversation_history": 1,
            }
        )
        self.assertEqual(sync, stream)
        self.assertEqual(
            _anthropic_cache_markers(sync),
            [],
            "Off must inject no cache_control markers even with the legacy flag on",
        )

    def test_advanced_mode_parity(self):
        sync, stream = self._messages_from_both_paths(
            {
                "prompt_cache_mode": "Advanced",
                "enable_prompt_caching": 1,
                "cache_control_type": "ephemeral",
                "cache_system_message": 1,
                "cache_conversation_history": 0,
            }
        )
        self.assertEqual(sync, stream)
        roles = {role for _i, role, _c in _anthropic_cache_markers(sync)}
        self.assertEqual(
            roles, {"system"}, "Advanced with cache_conversation_history=0 caches system only"
        )


if __name__ == "__main__":
    unittest.main()


class TestAutoDynamicBreakpointGate(unittest.TestCase):
    """Auto places the dynamic (latest-user-message) breakpoint only for Agents
    that can emit tool calls.

    Measured on caching-phase0.local (claude-haiku-4-5, 23k-char system prompt):
    for a tool-less Agent the dynamic entry is written every call and read back
    never — cache_read stayed pinned at the 5088-token system prefix across four
    consecutive calls of a fresh, strictly-growing conversation — because the
    latest user turn is sent as the enhanced_prompt wrapper but re-enters the
    next request from history as the bare persisted text. Inside one turn's tool
    loop the same breakpoint IS read back by rounds 2..N (11094 units vs 12182
    for a forced 4-round turn), which is the case this gate preserves.
    """

    def test_tool_less_agent_gets_no_dynamic_breakpoint(self):
        settings = _resolve_cache_settings(_agent_doc("Auto"))
        self.assertTrue(settings.enabled)
        self.assertTrue(settings.cache_system_message)
        self.assertFalse(settings.cache_dynamic_content)

    def test_each_tool_bearing_field_enables_the_dynamic_breakpoint(self):
        cases = {
            "agent_tool": [{"tool": "frappe_list_records"}],
            "agent_mcp_server": [{"mcp_server": "srv"}],
            "agent_skill": [{"skill": "s"}],
            "ssh_connections": [{"ssh_connection": "c"}],
            "enable_lazy_tools": 1,
            "enable_memory_search_tool": 1,
            "enable_memory_write_tool": 1,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                settings = _resolve_cache_settings(_agent_doc("Auto", **{field: value}))
                self.assertTrue(
                    settings.cache_dynamic_content,
                    f"{field} should enable the dynamic breakpoint",
                )

    def test_empty_tool_table_does_not_enable_the_dynamic_breakpoint(self):
        settings = _resolve_cache_settings(_agent_doc("Auto", agent_tool=[]))
        self.assertFalse(settings.cache_dynamic_content)

    def test_explicit_agent_has_tools_overrides_the_doc(self):
        """The kwarg exists for a caller with a better-filtered signal than the doc.

        run()/run_stream() deliberately do NOT pass the runtime `agent.tools`
        list: HUF attaches the `get_result_context` internal-capability tool to
        every agent, so that list is unconditionally non-empty and would leave
        the gate permanently open."""
        tool_doc = _agent_doc("Auto", agent_tool=[{"tool": "frappe_list_records"}])
        self.assertFalse(
            _resolve_cache_settings(tool_doc, agent_has_tools=False).cache_dynamic_content
        )
        self.assertTrue(
            _resolve_cache_settings(_agent_doc("Auto"), agent_has_tools=True).cache_dynamic_content
        )

    def test_gate_does_not_leak_into_off_or_advanced(self):
        tools = {"agent_tool": [{"tool": "frappe_list_records"}]}
        off = _resolve_cache_settings(_agent_doc("Off", **tools))
        self.assertFalse(off.cache_dynamic_content)
        # Advanced stays driven purely by the legacy field, tools or not.
        adv_off = _resolve_cache_settings(
            _agent_doc("Advanced", enable_prompt_caching=1, cache_conversation_history=0, **tools)
        )
        self.assertFalse(adv_off.cache_dynamic_content)
        adv_on = _resolve_cache_settings(
            _agent_doc("Advanced", enable_prompt_caching=1, cache_conversation_history=1)
        )
        self.assertTrue(adv_on.cache_dynamic_content)

    def test_local_llm_gate_still_wins(self):
        settings = _resolve_cache_settings(
            _agent_doc("Auto", agent_tool=[{"tool": "t"}]),
            is_local_llm=True,
            agent_has_tools=True,
        )
        self.assertFalse(settings.enabled)
        self.assertFalse(settings.cache_dynamic_content)
