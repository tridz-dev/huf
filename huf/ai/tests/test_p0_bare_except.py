# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

import asyncio

from huf.ai.agent_integration import run_agent_sync, run_agent_stream
from huf.ai.sdk_tools import _load_state as sdk_load_state
from huf.ai.conversation_data_tools import _load_state as cd_load_state


class _FakeDoc:
    def __init__(self, **fields):
        for k, v in fields.items():
            setattr(self, k, v)

    def get_password(self, field):
        return getattr(self, field, None)

    def insert(self, *args, **kwargs):
        return self

    def db_set(self, *args, **kwargs):
        pass

    def get(self, field, default=None):
        return getattr(self, field, default)


class TestConversationDataLoadState(IntegrationTestCase):
    """Batch 1: malformed/legacy conversation_data must not abort the agent run."""

    def test_load_state_returns_default_for_none(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn(None)
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_returns_default_for_empty_string(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn("")
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_returns_default_for_invalid_json(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn("not valid json {{")
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_returns_default_for_non_string_non_dict(self):
        for fn in (sdk_load_state, cd_load_state):
            result = fn(12345)
            self.assertEqual(result, {"version": 1, "scope": {}, "items": []})

    def test_load_state_handles_double_encoded_string(self):
        payload = {"items": [{"name": "x", "value": 1}], "version": 2}
        for fn in (sdk_load_state, cd_load_state):
            result = fn(json.dumps(json.dumps(payload)))
            self.assertEqual(result["version"], 2)
            self.assertEqual(result["items"], [{"name": "x", "value": 1}])

    def test_load_state_preserves_valid_dict(self):
        payload = {"items": [{"name": "y", "value": "ok"}]}
        for fn in (sdk_load_state, cd_load_state):
            result = fn(payload)
            self.assertEqual(result["items"], [{"name": "y", "value": "ok"}])


class TestAgentSyncConversationData(IntegrationTestCase):
    """Batch 1: malformed conversation_data in run_agent_sync must not abort the run."""

    def _make_agent_doc(self):
        return _FakeDoc(
            name="test-agent",
            provider="openai",
            model="gpt-4o",
            enable_conversation_data=1,
            inject_conversation_data=1,
            persist_conversation=1,
            context_strategy="Summarize",
            history_limit=20,
            allow_guest=0,
            max_knowledge_tokens=4000,
            autonaming_of_conversation_title=0,
            prompt_mode="Local",
            agent_prompt=None,
            max_context_chars=2000,
            enable_multi_run=0,
            allow_chat=1,
        )

    def test_malformed_conversation_data_does_not_abort_run(self):
        conversation = _FakeDoc(
            name="conv-sync-test",
            title="Chat with test-agent",
            conversation_data="not valid json {{",
        )

        def get_doc(doctype, name=None, *args, **kwargs):
            if doctype == "Agent":
                return self._make_agent_doc()
            if doctype == "AI Provider":
                return _FakeDoc(name="openai", provider_name="OpenAI", api_key="sk-test")
            if doctype == "AI Model":
                return _FakeDoc(name="gpt-4o", model_name="gpt-4o")
            if doctype == "Agent Run":
                return _FakeDoc(name="RUN-0001")
            if isinstance(doctype, dict) and doctype.get("doctype") == "Agent Run":
                return _FakeDoc(name="RUN-0001")
            raise frappe.DoesNotExistError(f"{doctype} {name}")

        conv_manager_mock = SimpleNamespace(
            session_id="test-session",
            get_or_create_conversation=lambda **kw: conversation,
            get_conversation_history=lambda *a, **kw: [],
            add_message=lambda *a, **kw: SimpleNamespace(name="MSG-0001"),
            get_stored_summary=lambda *a, **kw: None,
        )

        with patch("frappe.get_doc", side_effect=get_doc), \
             patch("frappe.log_error"), \
             patch("huf.ai.agent_integration.AgentManager") as mock_manager, \
             patch("huf.ai.agent_integration.ConversationManager", return_value=conv_manager_mock), \
             patch("huf.ai.agent_integration._is_user_allowed", return_value=True), \
             patch("huf.ai.agent_integration.build_knowledge_context", return_value=None), \
             patch("huf.ai.agent_integration._run_async_safely", return_value=SimpleNamespace(final_output="ok", usage=None)), \
             patch("huf.ai.agent_integration.transaction_checkpoint"), \
             patch("frappe.db.set_value"), \
             patch("frappe.db.sql"), \
             patch("frappe.enqueue"), \
             patch("frappe.publish_realtime"), \
             patch("frappe.logger") as mock_logger:

            mock_manager.return_value.create_agent.return_value = SimpleNamespace()

            result = run_agent_sync(
                agent_name="test-agent",
                prompt="hello",
                channel_id="test",
                conversation_id="conv-sync-test",
            )

            self.assertTrue(result.get("success"))
            self.assertEqual(result.get("response"), "ok")
            mock_logger.return_value.warning.assert_called_once()
            self.assertIn("conversation_data", mock_logger.return_value.warning.call_args[0][0])

    async def _collect_stream(self, gen):
        chunks = []
        async for chunk in gen:
            chunks.append(chunk)
        return chunks

    def test_stream_malformed_conversation_data_does_not_abort_run(self):
        conversation = _FakeDoc(
            name="conv-stream-test",
            title="Streaming chat with test-agent",
            conversation_data="not valid json {{",
        )

        def get_doc(doctype, name=None, *args, **kwargs):
            if doctype == "Agent":
                return self._make_agent_doc()
            if doctype == "AI Provider":
                return _FakeDoc(name="openai", provider_name="OpenAI", api_key="sk-test")
            if doctype == "AI Model":
                return _FakeDoc(name="gpt-4o", model_name="gpt-4o")
            if doctype == "Agent Run":
                return _FakeDoc(name="RUN-0002")
            if isinstance(doctype, dict) and doctype.get("doctype") == "Agent Run":
                return _FakeDoc(name="RUN-0002")
            raise frappe.DoesNotExistError(f"{doctype} {name}")

        async def fake_stream():
            yield {"type": "delta", "content": "hi", "full_response": "hi"}
            yield {"type": "complete", "content": "hi", "full_response": "hi", "usage": {}}

        conv_manager_mock = SimpleNamespace(
            session_id="test-session",
            get_or_create_conversation=lambda **kw: conversation,
            get_conversation_history=lambda *a, **kw: [],
            add_message=lambda *a, **kw: SimpleNamespace(name="MSG-0002"),
            get_stored_summary=lambda *a, **kw: None,
        )

        with patch("frappe.get_doc", side_effect=get_doc), \
             patch("frappe.log_error"), \
             patch("huf.ai.agent_integration.AgentManager") as mock_manager, \
             patch("huf.ai.agent_integration.ConversationManager", return_value=conv_manager_mock), \
             patch("huf.ai.agent_integration._is_user_allowed", return_value=True), \
             patch("huf.ai.agent_integration.build_knowledge_context", return_value=None), \
             patch("huf.ai.agent_integration.RunProvider.run_stream", return_value=fake_stream()), \
             patch("huf.ai.agent_integration.transaction_checkpoint"), \
             patch("frappe.db.set_value"), \
             patch("frappe.db.sql"), \
             patch("frappe.enqueue"), \
             patch("frappe.publish_realtime"), \
             patch("frappe.logger") as mock_logger:

            mock_manager.return_value.create_agent.return_value = SimpleNamespace()

            chunks = asyncio.run(
                self._collect_stream(
                    run_agent_stream(
                        agent_name="test-agent",
                        prompt="hello",
                        channel_id="test",
                        conversation_id="conv-stream-test",
                    )
                )
            )

            self.assertTrue(any(c.get("type") == "complete" for c in chunks))
            mock_logger.return_value.warning.assert_called_once()
            self.assertIn("conversation_data", mock_logger.return_value.warning.call_args[0][0])
