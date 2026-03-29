"""
Human Approval tests for HUF Flow Engine.

Tests the human approval workflow including:
- Human approval blocking flow execution
- Approval resuming flow
- Rejection taking alternate path
- Permission checks for approval
- Notification sending
- Edge routing based on approval outcome
"""

import json
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.flow_engine import (
    _exec_human_approval,
    approve_flow_run,
    _verify_approval_permission,
)
from huf.ai.flow_api import (
    approve_flow_run as api_approve_flow_run,
    reject_flow_run as api_reject_flow_run,
    get_pending_approvals,
)


class TestHumanApproval(FrappeTestCase):
    """Comprehensive tests for human approval functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_flow_id = "test-approval-flow"
        self._cleanup_test_data()
        self._create_test_flows()
    
    def tearDown(self):
        """Clean up test data."""
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Remove all test data."""
        for flow_id in [self.test_flow_id, "test-approval-role", "test-approval-users"]:
            if frappe.db.exists("Flow Definition", flow_id):
                frappe.delete_doc("Flow Definition", flow_id, force=True)
        
        flow_runs = frappe.get_all("Flow Run", filters={"flow_id": ["like", "test-approval%"]}, pluck="name")
        for run_name in flow_runs:
            frappe.delete_doc("Flow Run", run_name, force=True)
        
        frappe.db.commit()
    
    def _create_test_flows(self):
        """Create test flow definitions."""
        # Basic approval flow with approved/rejected paths
        definition = {
            "schema_version": 1,
            "id": self.test_flow_id,
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {"id": "trigger-1", "type": "trigger.webhook"},
                {
                    "id": "approval-1",
                    "type": "human.approval",
                    "config": {
                        "title": "Test Approval",
                        "instructions": "Please review and approve",
                        "approval_type": "role",
                        "approver_role": "System Manager",
                        "store_decision_in_context": "approval"
                    }
                },
                {"id": "approved-action", "type": "tool.call", "config": {"tool_name": "noop"}},
                {"id": "rejected-action", "type": "tool.call", "config": {"tool_name": "noop"}},
                {"id": "end-1", "type": "end"}
            ],
            "edges": [
                {"id": "e1", "from": "trigger-1", "to": "approval-1", "type": "always"},
                {"id": "e2", "from": "approval-1", "to": "approved-action", "type": "always", "meta": {"outcome": "approved"}},
                {"id": "e3", "from": "approval-1", "to": "rejected-action", "type": "always", "meta": {"outcome": "rejected"}},
                {"id": "e4", "from": "approved-action", "to": "end-1", "type": "always"},
                {"id": "e5", "from": "rejected-action", "to": "end-1", "type": "always"}
            ],
            "settings": {},
            "metadata": {"name": "Test Approval Flow"}
        }
        
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = self.test_flow_id
        flow.flow_name = "Test Approval Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        
        # Approval flow with user-based approval
        definition2 = {
            "schema_version": 1,
            "id": "test-approval-users",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {"id": "trigger-1", "type": "trigger.webhook"},
                {
                    "id": "approval-1",
                    "type": "human.approval",
                    "config": {
                        "title": "User Approval",
                        "approval_type": "users",
                        "approver_users": ["Administrator"],
                        "store_decision_in_context": "approval"
                    }
                },
                {"id": "end-1", "type": "end"}
            ],
            "edges": [
                {"id": "e1", "from": "trigger-1", "to": "approval-1", "type": "always"},
                {"id": "e2", "from": "approval-1", "to": "end-1", "type": "always", "meta": {"outcome": "approved"}}
            ],
            "settings": {},
            "metadata": {"name": "Test User Approval"}
        }
        
        if frappe.db.exists("Flow Definition", "test-approval-users"):
            frappe.delete_doc("Flow Definition", "test-approval-users", force=True)
        
        flow2 = frappe.new_doc("Flow Definition")
        flow2.flow_id = "test-approval-users"
        flow2.flow_name = "Test User Approval"
        flow2.status = "Active"
        flow2.definition_json = json.dumps(definition2)
        flow2.insert()
        
        frappe.db.commit()
    
    def _create_flow_run(self, flow_id: str = None, payload: dict = None) -> "frappe.Document":
        """Helper to create a flow run."""
        from huf.ai.flow_engine import create_flow_run
        return create_flow_run(
            flow_id=flow_id or self.test_flow_id,
            payload=payload or {}
        )
    
    # -------------------------------------------------------------------------
    # Human Approval Blocking Tests
    # -------------------------------------------------------------------------
    
    def test_human_approval_blocks_flow(self):
        """Test that human approval node blocks flow execution."""
        flow_run = self._create_flow_run()
        
        node = {
            "id": "approval-1",
            "type": "human.approval",
            "config": {
                "title": "Test Approval",
                "instructions": "Please review",
                "approval_type": "role",
                "approver_role": "System Manager"
            }
        }
        config = node["config"]
        settings = {}
        
        # Execute approval node
        with patch("huf.ai.flow_engine._send_approval_notifications"):
            result = _exec_human_approval(flow_run, node, config, settings)
        
        # Check that flow is blocked
        self.assertEqual(result["status"], "waiting_approval")
        
        flow_run.reload()
        self.assertEqual(flow_run.status, "Waiting Approval")
        self.assertIsNotNone(flow_run.waiting)
        
        # Verify waiting data structure
        waiting = json.loads(flow_run.waiting)
        self.assertEqual(waiting["type"], "approval")
        self.assertEqual(waiting["node_id"], "approval-1")
        self.assertEqual(waiting["title"], "Test Approval")
    
    def test_human_approval_default_values(self):
        """Test that human approval uses default values."""
        flow_run = self._create_flow_run()
        
        node = {
            "id": "approval-1",
            "type": "human.approval",
            "config": {}  # Minimal config
        }
        config = node["config"]
        settings = {}
        
        with patch("huf.ai.flow_engine._send_approval_notifications"):
            result = _exec_human_approval(flow_run, node, config, settings)
        
        flow_run.reload()
        waiting = json.loads(flow_run.waiting)
        
        self.assertEqual(waiting["title"], "Approval Required")
        self.assertEqual(waiting["approval_type"], "role")
        self.assertEqual(waiting["store_decision_in_context"], "approval")
    
    # -------------------------------------------------------------------------
    # Approval Resumption Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.run_flow")
    def test_approve_resumes_flow(self, mock_run_flow):
        """Test that approval resumes flow execution."""
        flow_run = self._create_flow_run()
        
        # Set up waiting approval state
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "node_id": "approval-1",
                "approval_type": "role",
                "approver_role": "System Manager",
                "store_decision_in_context": "approval"
            }),
            "current_node_id": "approval-1"
        })
        frappe.db.commit()
        
        # Approve the flow
        with patch("huf.ai.flow_engine._verify_approval_permission"):
            approve_flow_run(flow_run.name, decision="approved", comment="Approved")
        
        # Check flow resumed
        flow_run.reload()
        self.assertEqual(flow_run.status, "Running")
        
        # Verify decision stored in context
        ctx = json.loads(flow_run.context_json)
        self.assertIn("approval", ctx)
        self.assertEqual(ctx["approval"]["decision"], "approved")
        self.assertEqual(ctx["approval"]["comment"], "Approved")
        self.assertEqual(ctx["approval"]["approved_by"], frappe.session.user)
        self.assertIn("approved_at", ctx["approval"])
    
    @patch("huf.ai.flow_engine.run_flow")
    def test_approve_moves_to_correct_node(self, mock_run_flow):
        """Test that approval routes to the correct node based on outcome."""
        flow_run = self._create_flow_run()
        
        # Set up waiting approval state
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "node_id": "approval-1",
                "store_decision_in_context": "approval"
            }),
            "current_node_id": "approval-1"
        })
        frappe.db.commit()
        
        # Approve
        with patch("huf.ai.flow_engine._verify_approval_permission"):
            approve_flow_run(flow_run.name, decision="approved")
        
        flow_run.reload()
        # Should move to approved-action node
        self.assertEqual(flow_run.current_node_id, "approved-action")
    
    # -------------------------------------------------------------------------
    # Rejection Path Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.run_flow")
    def test_reject_alternate_path(self, mock_run_flow):
        """Test that rejection takes alternate path."""
        flow_run = self._create_flow_run()
        
        # Set up waiting approval state
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "node_id": "approval-1",
                "store_decision_in_context": "approval"
            }),
            "current_node_id": "approval-1"
        })
        frappe.db.commit()
        
        # Reject
        with patch("huf.ai.flow_engine._verify_approval_permission"):
            approve_flow_run(flow_run.name, decision="rejected", comment="Not approved")
        
        flow_run.reload()
        
        # Check rejection stored in context
        ctx = json.loads(flow_run.context_json)
        self.assertEqual(ctx["approval"]["decision"], "rejected")
        self.assertEqual(ctx["approval"]["comment"], "Not approved")
        
        # Should move to rejected-action node
        self.assertEqual(flow_run.current_node_id, "rejected-action")
    
    @patch("huf.ai.flow_engine.run_flow")
    def test_approve_no_matching_edge(self, mock_run_flow):
        """Test approval when no matching edge exists."""
        # Create a flow without proper edges
        flow_run = self._create_flow_run()
        
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "node_id": "approval-1",
                "store_decision_in_context": "approval"
            }),
            "current_node_id": "approval-1"
        })
        frappe.db.commit()
        
        # Create a minimal flow definition without proper edges
        definition = {
            "schema_version": 1,
            "id": self.test_flow_id,
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {"id": "approval-1", "type": "human.approval"},
                {"id": "end-1", "type": "end"}
            ],
            "edges": [],  # No edges for approval outcomes
            "settings": {},
            "metadata": {"name": "Test"}
        }
        flow_def = frappe.get_doc("Flow Definition", self.test_flow_id)
        flow_def.definition_json = json.dumps(definition)
        flow_def.save()
        frappe.db.commit()
        
        # Try to approve
        with patch("huf.ai.flow_engine._verify_approval_permission"):
            with patch("huf.ai.flow_engine._fail_flow_run") as mock_fail:
                approve_flow_run(flow_run.name, decision="approved")
                mock_fail.assert_called_once()
    
    # -------------------------------------------------------------------------
    # Permission Check Tests
    # -------------------------------------------------------------------------
    
    def test_permission_check_role_based(self):
        """Test role-based approval permission check."""
        waiting = {
            "type": "approval",
            "approval_type": "role",
            "approver_role": "System Manager"
        }
        
        # Should not raise for current user (has System Manager role)
        _verify_approval_permission(waiting)
    
    def test_permission_check_role_based_unauthorized(self):
        """Test role-based approval permission check fails for wrong role."""
        waiting = {
            "type": "approval",
            "approval_type": "role",
            "approver_role": "NonExistentRole12345"
        }
        
        with self.assertRaises(frappe.PermissionError):
            _verify_approval_permission(waiting)
    
    def test_permission_check_user_based(self):
        """Test user-based approval permission check."""
        waiting = {
            "type": "approval",
            "approval_type": "user",
            "approver_users": [frappe.session.user]
        }
        
        # Should not raise for current user
        _verify_approval_permission(waiting)
    
    def test_permission_check_user_based_unauthorized(self):
        """Test user-based approval permission check fails for wrong user."""
        waiting = {
            "type": "approval",
            "approval_type": "user",
            "approver_users": ["other.user@example.com"]
        }
        
        with self.assertRaises(frappe.PermissionError):
            _verify_approval_permission(waiting)
    
    def test_permission_check_no_restrictions(self):
        """Test approval with no permission restrictions."""
        waiting = {
            "type": "approval",
            "approval_type": "role"
            # No approver_role specified
        }
        
        # Should not raise
        _verify_approval_permission(waiting)
    
    # -------------------------------------------------------------------------
    # API Approval Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_api.engine_approve")
    def test_api_approve_flow_run(self, mock_approve):
        """Test API endpoint for approving flow run."""
        flow_run = self._create_flow_run()
        
        result = api_approve_flow_run(flow_run.name, comment="Approved via API")
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
        mock_approve.assert_called_once_with(
            flow_run.name,
            decision="approved",
            comment="Approved via API"
        )
    
    @patch("huf.ai.flow_api.engine_approve")
    def test_api_reject_flow_run(self, mock_approve):
        """Test API endpoint for rejecting flow run."""
        flow_run = self._create_flow_run()
        
        result = api_reject_flow_run(flow_run.name, comment="Rejected via API")
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
        mock_approve.assert_called_once_with(
            flow_run.name,
            decision="rejected",
            comment="Rejected via API"
        )
    
    # -------------------------------------------------------------------------
    # Notification Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.enqueue_create_notification")
    @patch("huf.ai.flow_engine.is_email_notifications_enabled")
    def test_approval_notifications_sent(self, mock_email_enabled, mock_create_notif):
        """Test that approval notifications are sent."""
        mock_email_enabled.return_value = False  # Skip email for test
        
        flow_run = self._create_flow_run()
        
        node = {
            "id": "approval-1",
            "type": "human.approval",
            "config": {
                "title": "Test Approval",
                "instructions": "Please review",
                "approval_type": "role",
                "approver_role": "System Manager"
            }
        }
        config = node["config"]
        settings = {}
        
        _exec_human_approval(flow_run, node, config, settings)
        
        # Verify notification was created
        mock_create_notif.assert_called()
        call_args = mock_create_notif.call_args[0][0]
        self.assertIn("Approval Required: Test Approval", call_args["subject"])
    
    @patch("huf.ai.flow_engine.enqueue_create_notification")
    @patch("huf.ai.flow_engine.is_email_notifications_enabled")
    @patch("huf.ai.flow_engine.frappe.sendmail")
    def test_approval_email_notifications(self, mock_sendmail, mock_email_enabled, mock_create_notif):
        """Test that email notifications are sent when enabled."""
        mock_email_enabled.return_value = True
        
        flow_run = self._create_flow_run()
        
        node = {
            "id": "approval-1",
            "type": "human.approval",
            "config": {
                "title": "Test Approval",
                "approval_type": "role",
                "approver_role": "System Manager"
            }
        }
        config = node["config"]
        settings = {}
        
        _exec_human_approval(flow_run, node, config, settings)
        
        # Verify email was sent
        mock_sendmail.assert_called()
    
    @patch("huf.ai.flow_engine.enqueue_create_notification")
    def test_approval_notifications_no_approvers(self, mock_create_notif):
        """Test notification when no approvers found."""
        flow_run = self._create_flow_run()
        
        node = {
            "id": "approval-1",
            "type": "human.approval",
            "config": {
                "title": "Test Approval",
                "approval_type": "role",
                "approver_role": "NonExistentRole12345"
            }
        }
        config = node["config"]
        settings = {}
        
        # Should not raise, just log
        _exec_human_approval(flow_run, node, config, settings)
        
        # No notifications should be created
        mock_create_notif.assert_not_called()
    
    # -------------------------------------------------------------------------
    # Pending Approvals List Tests
    # -------------------------------------------------------------------------
    
    def test_get_pending_approvals(self):
        """Test getting list of pending approvals."""
        # Create multiple flow runs waiting for approval
        flow_runs = []
        for i in range(3):
            flow_run = self._create_flow_run()
            flow_run.db_set({
                "status": "Waiting Approval",
                "waiting": json.dumps({
                    "type": "approval",
                    "approval_type": "role",
                    "approver_role": "System Manager",
                    "title": f"Approval {i}"
                })
            })
            flow_runs.append(flow_run)
        
        frappe.db.commit()
        
        # Get pending approvals
        approvals = get_pending_approvals()
        
        self.assertIsInstance(approvals, list)
        
        # Should find all our approvals
        approval_titles = [a["title"] for a in approvals]
        for i in range(3):
            self.assertIn(f"Approval {i}", approval_titles)
    
    def test_get_pending_approvals_by_users(self):
        """Test getting pending approvals filtered by users."""
        # Create flow run with user-based approval
        flow_run = self._create_flow_run(flow_id="test-approval-users")
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "users",
                "approver_users": [frappe.session.user],
                "title": "User-based Approval"
            })
        })
        frappe.db.commit()
        
        # Get pending approvals
        approvals = get_pending_approvals()
        
        # Should find the user-based approval
        approval_titles = [a["title"] for a in approvals]
        self.assertIn("User-based Approval", approval_titles)
    
    def test_get_pending_approvals_structure(self):
        """Test structure of pending approvals response."""
        flow_run = self._create_flow_run()
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "role",
                "approver_role": "System Manager",
                "title": "Test",
                "instructions": "Instructions here"
            })
        })
        frappe.db.commit()
        
        approvals = get_pending_approvals()
        
        if approvals:
            approval = approvals[0]
            self.assertIn("flow_run_id", approval)
            self.assertIn("flow_id", approval)
            self.assertIn("title", approval)
            self.assertIn("instructions", approval)
            self.assertIn("view_link", approval)
            self.assertIn("approval_type", approval)
