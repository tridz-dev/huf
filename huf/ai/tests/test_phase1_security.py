# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Phase 1 security & transaction safety tests.

Covers:
- transaction_checkpoint context awareness
- audio_service / orchestrator commit gating
- set_user restore guards
- capability checks on prompt_api and huf_data_table/api.py
- webhook endpoint signature/token validation
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase


class TestTransactionCheckpoint(IntegrationTestCase):
    """transaction_checkpoint must delegate to commit_if_background."""

    def test_checkpoint_calls_commit_if_background(self):
        from huf.ai.transaction import transaction_checkpoint

        with patch("huf.ai.transaction.commit_if_background") as mock_commit:
            transaction_checkpoint(reason="test_context")
            mock_commit.assert_called_once()


class TestCommitIfBackground(IntegrationTestCase):
    """commit_if_background must only commit outside HTTP requests."""

    def test_no_commit_inside_request(self):
        from huf.ai.transaction import commit_if_background

        setattr(frappe.local, "request", frappe._dict(method="GET"))
        try:
            with patch("huf.ai.transaction.safe_commit") as mock_commit:
                commit_if_background()
                mock_commit.assert_not_called()
        finally:
            if hasattr(frappe.local, "request"):
                delattr(frappe.local, "request")

    def test_commit_outside_request(self):
        from huf.ai.transaction import commit_if_background

        if hasattr(frappe.local, "request"):
            delattr(frappe.local, "request")

        with patch("huf.ai.transaction.safe_commit") as mock_commit:
            commit_if_background()
            mock_commit.assert_called_once()


class TestAudioServiceCommitGating(IntegrationTestCase):
    """create_audio_user_message must not hard-commit in request handlers."""

    def test_create_audio_user_message_uses_commit_if_background(self):
        from huf.ai import audio_service

        setattr(frappe.local, "request", frappe._dict(method="POST"))
        try:
            file_doc = MagicMock(file_url="/files/audio.mp3")
            agent_doc = MagicMock(provider="openai", model="whisper-1")
            msg_doc = MagicMock()
            msg_doc.name = "MSG-0001"

            def get_doc(doctype, name=None, *args, **kwargs):
                if doctype == "File":
                    return file_doc
                if doctype == "Agent":
                    return agent_doc
                if doctype == "Agent Message":
                    return msg_doc
                if isinstance(doctype, dict) and doctype.get("doctype") == "Agent Message":
                    return msg_doc
                raise frappe.DoesNotExistError(f"{doctype} {name}")

            with patch("huf.ai.audio_service.commit_if_background") as mock_commit:
                with patch("frappe.get_doc", side_effect=get_doc):
                    with patch("frappe.db.get_value", return_value="test-agent"):
                        with patch("frappe.db.sql", return_value=[frappe._dict(last_index=0)]):
                            with patch("frappe.db.set_value"):
                                with patch("frappe.publish_realtime"):
                                    audio_service.create_audio_user_message(
                                    conversation_id="conv-1",
                                    file_id="file-1",
                                    transcript="hello",
                                    metadata={},
                                )
                mock_commit.assert_called_once()
        finally:
            if hasattr(frappe.local, "request"):
                delattr(frappe.local, "request")


class TestOrchestratorCommitGating(IntegrationTestCase):
    """create_orchestration must not hard-commit in request handlers."""

    def _make_agent_doc(self):
        return SimpleNamespace(
            name="test-agent",
            provider="openai",
            model="gpt-4o",
            default_plan=[],
        )

    def test_create_orchestration_uses_commit_if_background(self):
        from huf.ai.orchestration.orchestrator import create_orchestration

        agent_doc = self._make_agent_doc()
        orch = MagicMock()
        orch.agent_orchestration_plan = []
        orch.name = "ORCH-0001"

        setattr(frappe.local, "request", frappe._dict(method="POST"))
        try:
            with patch("frappe.get_doc", return_value=agent_doc):
                with patch("frappe.new_doc", return_value=orch):
                    with patch("huf.ai.orchestration.orchestrator.commit_if_background") as mock_commit:
                        with patch("huf.ai.orchestration.orchestrator.run_planning", return_value=""):
                            create_orchestration("test-agent", "hello")
                        mock_commit.assert_called_once()
        finally:
            if hasattr(frappe.local, "request"):
                delattr(frappe.local, "request")


class TestSetUserRestoreGuards(IntegrationTestCase):
    """Temporary user switches must restore the original user."""

    def _tracking_set_user(self, user):
        """Mock set_user that also updates the in-memory session user."""
        frappe.session.user = user

    def test_agent_hooks_restores_user(self):
        from huf.ai.agent_hooks import run_agent_for_doc

        original_user = "test@example.com"
        target_user = "trigger@example.com"

        frappe.session.user = original_user
        try:
            with patch("frappe.set_user", side_effect=self._tracking_set_user) as mock_set_user:
                with patch("huf.ai.agent_hooks.run_agent_sync"):
                    run_agent_for_doc(
                        doc={"doctype": "Note", "name": "TEST-001"},
                        agent_name="test-agent",
                        instructions="test",
                        event_name="after_insert",
                        provider="openai",
                        model="gpt-4o",
                        initiating_user=target_user,
                    )

            calls = mock_set_user.call_args_list
            self.assertTrue(any(c.args == (target_user,) for c in calls))
            self.assertTrue(any(c.args == (original_user,) for c in calls))
        finally:
            frappe.session.user = "Administrator"

    def test_telegram_webhook_restores_user(self):
        from huf.ai.tools.telegram_webhook import process_telegram_update

        original_user = "test@example.com"

        frappe.session.user = original_user
        try:
            with patch("frappe.set_user", side_effect=self._tracking_set_user) as mock_set_user:
                with patch("frappe.db.exists", return_value=False):
                    process_telegram_update("bot-settings", {})

            calls = mock_set_user.call_args_list
            self.assertTrue(any(c.args == ("Administrator",) for c in calls))
            self.assertTrue(any(c.args == (original_user,) for c in calls))
        finally:
            frappe.session.user = "Administrator"


class TestPromptApiCapabilityChecks(IntegrationTestCase):
    """prompt_api endpoints require capabilities after removing ignore_permissions."""

    def test_create_new_version_requires_agent_create(self):
        from huf.ai import prompt_api

        with patch.object(prompt_api, "has_capability", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                prompt_api.create_new_version("PROMPT-001", "body")

    def test_detach_from_template_requires_agent_edit(self):
        from huf.ai import prompt_api

        with patch.object(prompt_api, "has_capability", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                prompt_api.detach_from_template("AGENT-001")

    def test_get_version_history_requires_agent_use(self):
        from huf.ai import prompt_api

        with patch.object(prompt_api, "has_capability", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                prompt_api.get_version_history("PROMPT-001")


class TestHufDataTableCapabilityChecks(IntegrationTestCase):
    """huf_data_table/api.py endpoints require capabilities after removing ignore_permissions."""

    def test_create_data_table_requires_flows_manage(self):
        from huf.huf.doctype.huf_data_table import api as data_table_api

        with patch.object(data_table_api, "has_capability", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                data_table_api.create_data_table("TestTable", [])

    def test_get_table_schema_requires_flows_use(self):
        from huf.huf.doctype.huf_data_table import api as data_table_api

        with patch.object(data_table_api, "has_capability", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                data_table_api.get_table_schema("TABLE-001")


class TestWebhookEndpointSecurity(IntegrationTestCase):
    """allow_guest webhook endpoints must reject unsigned/invalid requests."""

    def test_telegram_webhook_rejects_missing_secret(self):
        from huf.ai.tools.telegram_webhook import handle_update

        settings = SimpleNamespace(
            service="telegram",
            is_active=True,
            get_password=lambda field: "secret-token",
        )

        mock_request = frappe._dict(args={"doc": "BOT-001"}, headers={}, get_data=lambda **kw: b"{}")
        frappe.request = mock_request
        try:
            with patch("frappe.db.exists", return_value=True):
                with patch("frappe.get_doc", return_value=settings):
                    result = handle_update()

            self.assertFalse(result.get("success"))
            self.assertIn("secret", result.get("error", "").lower())
        finally:
            frappe.request = None

    def test_elevenlabs_webhook_rejects_invalid_signature(self):
        from huf.ai.providers.elevenlabs_convai_api import handle_elevenlabs_webhook

        settings = SimpleNamespace(
            provider="openai",
            agent_id="agent-123",
            get_password=lambda field: "webhook-secret",
        )

        mock_request = frappe._dict(
            get_data=lambda **kw: b'{"type":"post_call_transcription"}',
            headers={"elevenlabs-signature": "invalid"},
        )
        frappe.request = mock_request
        try:
            with patch("frappe.get_single", return_value=settings):
                result = handle_elevenlabs_webhook()

            self.assertEqual(result.get("status"), "forbidden")
        finally:
            frappe.request = None

    def test_flow_webhook_rejects_invalid_key(self):
        from huf.ai.flow_api import flow_webhook

        defn_doc = SimpleNamespace(
            status="Active",
            definition_json='{"entry":"start","nodes":[{"id":"start","type":"trigger.webhook","config":{"auth":"correct-key"}}]}',
        )

        mock_request = frappe._dict(args={"webhook_key": "wrong-key"}, get_data=lambda **kw: b"{}")
        frappe.request = mock_request
        try:
            with patch("frappe.db.exists", return_value=True):
                with patch("frappe.get_doc", return_value=defn_doc):
                    with self.assertRaises(frappe.AuthenticationError):
                        flow_webhook("flow-1", webhook_key="wrong-key")
        finally:
            frappe.request = None

    def test_clean_flow_webhook_accepts_frappe_cloud_secret_header(self):
        from huf.ai.flow_api import flow_webhook_clean

        definition_json = (
            '{"entry":"start","nodes":[{"id":"start","type":"trigger.webhook",'
            '"config":{"auth":"correct-key"}}]}'
        )
        defn_doc = SimpleNamespace(status="Active", definition_json=definition_json, owner="flow-owner")
        flow_run = SimpleNamespace(name="FLOW-RUN-1", status="Queued")
        mock_request = frappe._dict(
            args={},
            form={},
            headers={"X-Webhook-Secret": "correct-key"},
            get_data=lambda **kw: b'{"event":"Site Status Update","site":"demo.frappe.cloud"}',
        )
        frappe.request = mock_request
        try:
            with patch("frappe.get_all", return_value=[{"name": "flow-1", "definition_json": definition_json}]):
                with patch("frappe.db.exists", return_value=True):
                    with patch("frappe.get_doc", return_value=defn_doc):
                        with patch("frappe.set_user") as mock_set_user:
                            with patch("huf.ai.flow_engine.create_flow_run", return_value=flow_run) as mock_create_run:
                                with patch("frappe.enqueue") as mock_enqueue:
                                    result = flow_webhook_clean()

            self.assertEqual(result["flow_run_id"], "FLOW-RUN-1")
            mock_set_user.assert_called_once_with("flow-owner")
            mock_create_run.assert_called_once()
            self.assertEqual(mock_create_run.call_args.kwargs["flow_id"], "flow-1")
            self.assertEqual(mock_create_run.call_args.kwargs["payload"]["event"], "Site Status Update")
            mock_enqueue.assert_called_once()
        finally:
            frappe.request = None

    def test_clean_flow_webhook_rejects_ambiguous_key_without_flow_id(self):
        from huf.ai.flow_api import flow_webhook_clean

        definition_json = (
            '{"entry":"start","nodes":[{"id":"start","type":"trigger.webhook",'
            '"config":{"auth":"shared-key"}}]}'
        )
        mock_request = frappe._dict(
            args={},
            form={},
            headers={"X-Webhook-Secret": "shared-key"},
            get_data=lambda **kw: b"{}",
        )
        frappe.request = mock_request
        try:
            with patch(
                "frappe.get_all",
                return_value=[
                    {"name": "flow-1", "definition_json": definition_json},
                    {"name": "flow-2", "definition_json": definition_json},
                ],
            ):
                with self.assertRaises(Exception):
                    flow_webhook_clean()
        finally:
            frappe.request = None
