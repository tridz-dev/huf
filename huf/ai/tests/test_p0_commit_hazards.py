# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.sdk_tools import handle_generate_image, handle_generate_audio


class _FakeDoc:
    """Minimal document-like stand-in for Frappe get_doc mocks."""

    def __init__(self, **fields):
        for k, v in fields.items():
            setattr(self, k, v)

    def get_password(self, field):
        return getattr(self, field, None)


class TestP0CommitHazards(FrappeTestCase):
    """Batch 2 Category B: media generation must fail closed when ordering fails."""

    def _mock_agent_setup(self, mock_get_doc, with_image_model=True):
        """Return mocks so handle_generate_* reaches the conversation_index block."""
        provider = _FakeDoc(name="openai", provider_name="OpenAI", api_key="sk-test")
        model = _FakeDoc(name="dall-e-3", model_name="dall-e-3")
        agent_fields = {"name": "test-agent", "provider": "openai", "image_generation_model": "dall-e-3"}
        if not with_image_model:
            agent_fields["image_generation_model"] = None
        agent = _FakeDoc(**agent_fields)

        def get_doc(doctype, name=None, *args, **kwargs):
            if doctype == "Agent":
                return agent
            if doctype == "AI Provider":
                return provider
            if doctype == "AI Model":
                return model
            raise frappe.DoesNotExistError(f"{doctype} {name}")

        mock_get_doc.side_effect = get_doc

    def test_generate_image_fails_closed_when_index_query_raises(self):
        with patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.sql") as mock_sql, \
             patch("frappe.log_error"), \
             patch("litellm.image_generation") as mock_image:

            self._mock_agent_setup(mock_get_doc)
            mock_sql.side_effect = Exception("deadlock")
            mock_image.return_value = SimpleNamespace(
                data=[SimpleNamespace(url="https://example.com/img.png")]
            )

            conversation_id = "conv-img-test"
            result = asyncio.run(
                handle_generate_image(
                    prompt="a blue square",
                    agent_name="test-agent",
                    conversation_id=conversation_id,
                )
            )

            self.assertFalse(result["success"])
            self.assertIn("message order", result["error"].lower())
            insert_calls = [
                c for c in mock_sql.call_args_list
                if c.args and "INSERT" in str(c.args[0]).upper()
            ]
            self.assertEqual(insert_calls, [])

    def test_generate_audio_fails_closed_when_index_query_raises(self):
        with patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.sql") as mock_sql, \
             patch("frappe.log_error"), \
             patch("litellm.speech") as mock_speech:

            self._mock_agent_setup(mock_get_doc, with_image_model=False)
            mock_sql.side_effect = Exception("deadlock")
            mock_speech.return_value = SimpleNamespace(content=b"fake-audio-bytes")

            conversation_id = "conv-audio-test"
            result = asyncio.run(
                handle_generate_audio(
                    input="hello world",
                    agent_name="test-agent",
                    conversation_id=conversation_id,
                )
            )

            self.assertFalse(result["success"])
            self.assertIn("message order", result["error"].lower())
            insert_calls = [
                c for c in mock_sql.call_args_list
                if c.args and "INSERT" in str(c.args[0]).upper()
            ]
            self.assertEqual(insert_calls, [])
