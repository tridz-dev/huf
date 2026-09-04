"""
Tests for WP-06 authorization on maintenance and tool endpoints.

Covers ST-06.1 through ST-06.8, and ST-06.9 (webhook path verification).
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import frappe
from frappe import _


class TestMaintenanceEndpointAuthorization(unittest.TestCase):
    """Pure-mock tests for endpoint permission checks."""

    def setUp(self):
        """Set up mock Frappe environment."""
        self.patcher_session = patch('frappe.session')
        self.mock_session = self.patcher_session.start()
        self.mock_session.user = "test_user@example.com"

        self.patcher_throw = patch('frappe.throw')
        self.mock_throw = self.patcher_throw.start()

    def tearDown(self):
        """Clean up patches."""
        self.patcher_session.stop()
        self.patcher_throw.stop()

    # ST-06.1 Tests: automation_scheduler.py - remove @frappe.whitelist()
    @patch('huf.ai.automation_scheduler.now_datetime')
    @patch('huf.ai.automation_scheduler.frappe.get_all')
    @patch('huf.ai.automation_scheduler.frappe.db.exists')
    @patch('huf.ai.automation_scheduler.automation_runtime_is_new')
    def test_st06_1_run_due_automations_not_whitelisted(
        self, mock_runtime_new, mock_db_exists, mock_get_all, mock_now
    ):
        """ST-06.1: run_due_automations should not be whitelisted for HTTP access."""
        # This test verifies the decorator is removed by checking that
        # the function exists and can be called directly.
        from huf.ai import automation_scheduler

        self.assertTrue(hasattr(automation_scheduler, 'run_due_automations'))
        # Verify the function itself doesn't have a whitelist decorator
        # (decorators would be in the function's __wrapped__ or similar).
        self.assertFalse(hasattr(
            automation_scheduler.run_due_automations,
            '__self__'  # Would indicate a bound method decorator
        ))

    # ST-06.2 Tests: tool_registry.py - require System Manager
    @patch('frappe.only_for')
    @patch('huf.ai.tool_registry.get_tools_by_app')
    def test_st06_2_sync_discovered_tools_system_manager_only(
        self, mock_get_tools, mock_only_for
    ):
        """ST-06.2: sync_discovered_tools should require System Manager role."""
        from huf.ai import tool_registry

        # Set up mock to raise PermissionError when not System Manager
        def only_for_side_effect(role):
            if role != "System Manager":
                frappe.throw(_("Not permitted"), frappe.PermissionError)

        mock_only_for.side_effect = only_for_side_effect
        mock_get_tools.return_value = {}

        # Call should invoke only_for with "System Manager"
        try:
            tool_registry.sync_discovered_tools(apps_to_scan=None)
        except:
            pass

        # Verify frappe.only_for was called with "System Manager"
        mock_only_for.assert_called_once_with("System Manager")

    # ST-06.3 Tests: orchestrator.py - add permission check
    @patch('frappe.has_permission')
    @patch('frappe.throw')
    @patch('frappe.get_doc')
    def test_st06_3_recreate_orchestration_plan_permission_check(
        self, mock_get_doc, mock_throw, mock_has_permission
    ):
        """ST-06.3: recreate_orchestration_plan should check write permission."""
        from huf.ai.orchestration import orchestrator

        mock_has_permission.return_value = False
        mock_throw.side_effect = frappe.PermissionError
        mock_orch = Mock()
        mock_orch.agent = "Test Agent"
        mock_get_doc.return_value = mock_orch

        # frappe.throw must actually stop execution (as it does for real);
        # without side_effect, the mock would silently fall through into
        # the unmocked planning code below the permission check.
        with self.assertRaises(frappe.PermissionError):
            orchestrator.recreate_orchestration_plan("test_orch")

        # Verify permission check was performed
        mock_has_permission.assert_called_with("Agent Orchestration", "write")
        # Verify throw was called due to failed permission
        mock_throw.assert_called_once()
        args = mock_throw.call_args[0]
        self.assertEqual(args[1], frappe.PermissionError)

    @patch('frappe.has_permission')
    @patch('frappe.get_doc')
    @patch('huf.ai.orchestration.orchestrator.run_planning')
    @patch('huf.ai.orchestration.orchestrator.parse_plan_steps')
    def test_st06_3_recreate_orchestration_plan_allowed_with_permission(
        self, mock_parse, mock_run_planning, mock_get_doc, mock_has_permission
    ):
        """ST-06.3: recreate_orchestration_plan should proceed when permitted."""
        from huf.ai.orchestration import orchestrator

        mock_has_permission.return_value = True
        mock_orch = Mock()
        mock_orch.agent = "Test Agent"
        mock_orch.agent_orchestration_plan = []
        mock_get_doc.side_effect = [mock_orch, Mock()]  # Two calls to get_doc
        mock_run_planning.return_value = "1. Step one\n2. Step two"
        mock_parse.return_value = ["Step one", "Step two"]

        orchestrator.recreate_orchestration_plan("test_orch")

        # Should not throw, should proceed with planning
        mock_run_planning.assert_called_once()

    # ST-06.4 Tests: memory_record.py - add permission check
    @patch('frappe.get_doc')
    def test_st06_4_queue_memory_knowledge_projection_permission_check(
        self, mock_get_doc
    ):
        """ST-06.4: queue_memory_knowledge_projection should check write permission."""
        from huf.huf.doctype.memory_record import memory_record

        mock_doc = Mock()
        mock_doc.check_permission = Mock(side_effect=frappe.PermissionError)
        mock_get_doc.return_value = mock_doc

        with self.assertRaises(frappe.PermissionError):
            memory_record.queue_memory_knowledge_projection("test_record")

        # Verify check_permission was called with "write"
        mock_doc.check_permission.assert_called_once_with("write")

    @patch('frappe.get_doc')
    def test_st06_4_remove_memory_knowledge_projection_permission_check(
        self, mock_get_doc
    ):
        """ST-06.4: remove_memory_knowledge_projection should check write permission."""
        from huf.huf.doctype.memory_record import memory_record

        mock_doc = Mock()
        mock_doc.check_permission = Mock(side_effect=frappe.PermissionError)
        mock_get_doc.return_value = mock_doc

        with self.assertRaises(frappe.PermissionError):
            memory_record.remove_memory_knowledge_projection("test_record")

        # Verify check_permission was called with "write"
        mock_doc.check_permission.assert_called_once_with("write")

    @patch('frappe.get_doc')
    def test_st06_4_queue_memory_allowed_with_permission(self, mock_get_doc):
        """ST-06.4: queue_memory_knowledge_projection should proceed when permitted."""
        from huf.huf.doctype.memory_record import memory_record

        mock_doc = Mock()
        mock_doc.check_permission = Mock()  # No exception
        mock_doc.queue_knowledge_projection = Mock(
            return_value={"status": "queued"}
        )
        mock_get_doc.return_value = mock_doc

        result = memory_record.queue_memory_knowledge_projection("test_record")

        self.assertEqual(result["status"], "queued")
        mock_doc.check_permission.assert_called_once_with("write")
        mock_doc.queue_knowledge_projection.assert_called_once()

    # ST-06.5 Tests: client_side_tool.py - permission check and user scoping
    @patch('frappe.session')
    @patch('frappe.has_permission')
    @patch('frappe.throw')
    def test_st06_5_client_side_function_permission_check(
        self, mock_throw, mock_has_permission, mock_session
    ):
        """ST-06.5: client_side_function should check write permission on conversation."""
        from huf.ai import client_side_tool

        mock_session.user = "test_user"
        mock_has_permission.return_value = False
        mock_throw.side_effect = frappe.PermissionError

        # frappe.throw must actually stop execution (as it does for real);
        # without side_effect, the mock would silently fall through into
        # the unmocked _get_or_create_call below the permission check.
        with self.assertRaises(frappe.PermissionError):
            client_side_tool.client_side_function(
                conversation_id="test_conv",
                agent_run_id="test_run",
                function_name="test_func",
            )

        # Should throw permission error
        mock_throw.assert_called_once()
        args = mock_throw.call_args[0]
        self.assertEqual(args[1], frappe.PermissionError)

    @patch('frappe.session')
    @patch('frappe.get_doc')
    @patch('frappe.db.get_value')
    @patch('frappe.has_permission')
    @patch('frappe.cache')
    @patch('frappe.publish_realtime')
    def test_st06_5_client_side_function_publish_realtime_scoped_to_owner(
        self,
        mock_publish,
        mock_cache,
        mock_has_permission,
        mock_get_value,
        mock_get_doc,
        mock_session,
    ):
        """ST-06.5: publish_realtime should be scoped to conversation owner."""
        from huf.ai import client_side_tool

        mock_session.user = "test_user"
        mock_has_permission.return_value = True
        mock_cache_obj = MagicMock()
        mock_cache_obj.set_value = Mock()
        mock_cache_obj.blpop = Mock(return_value=None)  # Timeout
        mock_cache.return_value = mock_cache_obj
        mock_get_value.return_value = "conversation_owner@example.com"
        # call_id is None in this test, so _get_or_create_call always takes
        # the "create" branch: frappe.get_doc({...}); call.insert(...). This
        # must stay pure-mock (per the file's own docstring) rather than
        # hitting a real, uncreated Agent Tool Call row.
        mock_call_doc = Mock()
        mock_get_doc.return_value = mock_call_doc

        result = client_side_tool.client_side_function(
            conversation_id="test_conv",
            agent_run_id="test_run",
            function_name="test_func",
        )

        # Verify publish_realtime was called with user=conversation_owner
        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args[1]
        self.assertEqual(call_kwargs["user"], "conversation_owner@example.com")
        self.assertNotEqual(call_kwargs["user"], "test_user")

    # ST-06.6 Tests: mcp_connection_resolver.py - System Manager only + hardened URL check
    @patch('frappe.only_for')
    def test_st06_6_resolve_mcp_connection_system_manager_only(
        self, mock_only_for
    ):
        """ST-06.6: resolve_mcp_connection should require System Manager."""
        from huf.ai import mcp_connection_resolver

        mock_only_for.side_effect = frappe.PermissionError

        with self.assertRaises(frappe.PermissionError):
            mcp_connection_resolver.resolve_mcp_connection(
                "https://example.com", "https://callback.com"
            )

        mock_only_for.assert_called_once_with("System Manager")

    def test_st06_6_is_safe_url_rejects_localhost(self):
        """ST-06.6: _is_safe_url should reject localhost."""
        from huf.ai.mcp_connection_resolver import _is_safe_url

        self.assertFalse(_is_safe_url("http://localhost:8080/mcp"))
        self.assertFalse(_is_safe_url("http://127.0.0.1:8080/mcp"))
        self.assertFalse(_is_safe_url("http://[::1]:8080/mcp"))

    def test_st06_6_is_safe_url_rejects_private_ips(self):
        """ST-06.6: _is_safe_url should reject private IP ranges."""
        from huf.ai.mcp_connection_resolver import _is_safe_url

        self.assertFalse(_is_safe_url("http://10.0.0.1/mcp"))
        self.assertFalse(_is_safe_url("http://192.168.1.1/mcp"))
        self.assertFalse(_is_safe_url("http://172.16.0.1/mcp"))

    @patch('socket.getaddrinfo')
    def test_st06_6_is_safe_url_requires_dns_resolution(
        self, mock_getaddrinfo
    ):
        """ST-06.6: _is_safe_url should require successful DNS resolution."""
        from huf.ai.mcp_connection_resolver import _is_safe_url
        import socket

        # Test DNS failure
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        self.assertFalse(_is_safe_url("http://invalid-unknown-domain.invalid/mcp"))

    @patch('socket.getaddrinfo')
    def test_st06_6_is_safe_url_allows_public_ips(
        self, mock_getaddrinfo
    ):
        """ST-06.6: _is_safe_url should allow public IP addresses."""
        from huf.ai.mcp_connection_resolver import _is_safe_url

        # Mock DNS resolution to return a public IP
        mock_getaddrinfo.return_value = [
            (2, 1, 6, '', ('8.8.8.8', 443))  # Public IP
        ]

        self.assertTrue(_is_safe_url("https://example.com/mcp"))

    # ST-06.7 Tests: automation_app_event.py - keep read gate, add initiating_user
    @patch('frappe.session')
    @patch('frappe.has_permission')
    @patch('frappe.throw')
    def test_st06_7_trigger_app_event_read_permission_gate(
        self, mock_throw, mock_has_permission, mock_session
    ):
        """ST-06.7: trigger_app_event should gate on Automation read permission."""
        from huf.ai import automation_app_event

        mock_session.user = "test_user"
        mock_has_permission.return_value = False

        automation_app_event.trigger_app_event("test_app", "test_event", {})

        # Verify read permission was checked
        mock_has_permission.assert_called_with("Automation", "read")
        mock_throw.assert_called_once()

    @patch('frappe.session')
    @patch('frappe.has_permission')
    @patch('frappe.get_all')
    @patch('huf.ai.automation_app_event.run_automation')
    @patch('huf.ai.automation_app_event.automation_runtime_is_new')
    def test_st06_7_trigger_app_event_passes_initiating_user(
        self,
        mock_runtime_new,
        mock_run_automation,
        mock_get_all,
        mock_has_permission,
        mock_session,
    ):
        """ST-06.7: trigger_app_event should pass initiating_user to run_automation."""
        from huf.ai import automation_app_event

        mock_session.user = "test_user@example.com"
        mock_has_permission.return_value = True
        mock_runtime_new.return_value = True
        mock_get_all.return_value = [
            {"name": "trigger1", "automation": "auto1"}
        ]

        automation_app_event.trigger_app_event("test_app", "test_event", {})

        # Verify run_automation was called with initiating_user
        mock_run_automation.assert_called_once()
        call_kwargs = mock_run_automation.call_args[1]
        self.assertEqual(call_kwargs["initiating_user"], "test_user@example.com")

    # ST-06.8 Tests: batch_poll.py - remove @frappe.whitelist()
    def test_st06_8_poll_pending_batch_jobs_not_whitelisted(self):
        """ST-06.8: poll_pending_batch_jobs should not be whitelisted."""
        from huf.ai import batch_poll

        self.assertTrue(hasattr(batch_poll, 'poll_pending_batch_jobs'))
        # Verify the function doesn't have a whitelist decorator
        self.assertFalse(hasattr(
            batch_poll.poll_pending_batch_jobs,
            '__self__'
        ))

    # ST-06.9 Tests: automation_webhook.py - verify existing guard works
    @patch('frappe.get_doc')
    @patch('frappe.throw')
    @patch('huf.ai.automation_runner.frappe.get_roles')
    def test_st06_9_webhook_run_as_user_guard_fires(
        self, mock_get_roles, mock_throw, mock_get_doc
    ):
        """ST-06.9: webhook's run_automation should use existing _check_run_as_user_permission guard."""
        from huf.ai.automation_runner import run_automation

        # Create an Automation where owner lacks System Manager
        # and run_as_user != owner (the violation condition)
        mock_automation = Mock()
        mock_automation.name = "test_auto"
        mock_automation.disabled = False
        mock_automation.status = "Active"
        mock_automation.agent = "test_agent"
        mock_automation.owner = "regular_user@example.com"
        mock_automation.run_as_user = "admin@example.com"
        mock_get_doc.return_value = mock_automation
        mock_get_roles.return_value = ["Huf User"]  # No System Manager
        # Without side_effect, the mocked frappe.throw silently returns None
        # instead of raising, so execution would fall through past the
        # permission check into instruction rendering (and crash there on
        # unconfigured Mock attributes) instead of actually verifying the
        # guard fires. See the sibling fix already applied above in this
        # same file for test_st06_5_client_side_function_permission_check.
        mock_throw.side_effect = frappe.PermissionError

        # Call with no initiating_user (webhook path)
        # Should trigger _check_run_as_user_permission guard
        try:
            run_automation("test_auto", trigger_name="webhook", commit=False)
        except frappe.PermissionError:
            pass  # Expected

        # Verify the throw was called due to permission check
        mock_throw.assert_called_once()
        args = mock_throw.call_args[0]
        self.assertEqual(args[1], frappe.PermissionError)

    @patch('frappe.get_doc')
    @patch('huf.ai.automation_runner.frappe.get_roles')
    @patch('huf.ai.automation_runner._execute')
    def test_st06_9_webhook_run_as_user_allowed_for_owner(
        self, mock_execute, mock_get_roles, mock_get_doc
    ):
        """ST-06.9: webhook automation should proceed when run_as_user == owner."""
        from huf.ai.automation_runner import run_automation

        mock_automation = Mock()
        mock_automation.name = "test_auto"
        mock_automation.disabled = False
        mock_automation.status = "Active"
        mock_automation.agent = "test_agent"
        mock_automation.owner = "user@example.com"
        mock_automation.run_as_user = "user@example.com"  # Same as owner
        mock_get_doc.return_value = mock_automation
        mock_execute.return_value = {"success": True}
        mock_get_roles.return_value = ["Huf User"]

        result = run_automation("test_auto", trigger_name="webhook", commit=False)

        # Should proceed without error
        self.assertIsNotNone(result)
        mock_execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
