"""
API tests for HUF Flow Engine.

Tests the whitelisted API endpoints including:
- Flow Definition management (get, save)
- Flow Run lifecycle (run, get, list, resume, approve, reject)
- Webhook trigger endpoint
- Schedule management
- Node schemas
- Agent tools
"""

import json
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.flow_api import (
    get_flow_definition,
    save_flow_definition,
    run_flow,
    get_flow_run,
    list_flow_runs,
    resume_flow_run,
    approve_flow_run,
    reject_flow_run,
    flow_webhook,
    schedule_flow,
    unschedule_flow,
    get_flow_schedule,
    get_node_schemas,
    handle_run_flow,
    handle_get_flow_run,
    handle_resume_flow_run,
    handle_approve_flow_run,
    get_pending_approvals,
)


class TestFlowAPI(FrappeTestCase):
    """Comprehensive API tests for Flow Engine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_flow_id = "test-flow-api"
        self._cleanup_test_data()
        self._create_test_flow()
    
    def tearDown(self):
        """Clean up test data."""
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Remove all test data."""
        # Clean up flow definitions
        for flow_id in [self.test_flow_id, "test-save-flow", "test-webhook-flow"]:
            if frappe.db.exists("Flow Definition", flow_id):
                frappe.delete_doc("Flow Definition", flow_id, force=True)
        
        # Clean up scheduled jobs
        job_id = f"huf.flow.schedule.{self.test_flow_id}"
        if frappe.db.exists("Scheduled Job Type", job_id):
            frappe.delete_doc("Scheduled Job Type", job_id, force=True)
        
        # Clean up flow runs
        flow_runs = frappe.get_all("Flow Run", filters={"flow_id": ["like", "test-%"]}, pluck="name")
        for run_name in flow_runs:
            frappe.delete_doc("Flow Run", run_name, force=True)
        
        frappe.db.commit()
    
    def _create_test_flow(self):
        """Create a test flow definition."""
        definition = {
            "schema_version": 1,
            "id": self.test_flow_id,
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {"id": "trigger-1", "type": "trigger.webhook"},
                {
                    "id": "action-1",
                    "type": "tool.call",
                    "config": {"tool_name": "create_document"}
                },
                {"id": "end-1", "type": "end"}
            ],
            "edges": [
                {"id": "e1", "from": "trigger-1", "to": "action-1", "type": "always"},
                {"id": "e2", "from": "action-1", "to": "end-1", "type": "always"}
            ],
            "settings": {},
            "metadata": {"name": "Test API Flow"}
        }
        
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = self.test_flow_id
        flow.flow_name = "Test API Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
    
    # -------------------------------------------------------------------------
    # Flow Definition API Tests
    # -------------------------------------------------------------------------
    
    def test_get_flow_definition(self):
        """Test getting a flow definition via API."""
        result = get_flow_definition(self.test_flow_id)
        
        self.assertEqual(result["flow_id"], self.test_flow_id)
        self.assertEqual(result["flow_name"], "Test API Flow")
        self.assertEqual(result["status"], "Active")
        self.assertIn("definition_json", result)
        self.assertIsInstance(result["definition_json"], dict)
    
    def test_get_flow_definition_not_found(self):
        """Test getting a non-existent flow definition."""
        with self.assertRaises(frappe.DoesNotExistError):
            get_flow_definition("non-existent-flow")
    
    def test_save_flow_definition_new(self):
        """Test saving a new flow definition."""
        definition = {
            "schema_version": 1,
            "id": "test-save-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}],
            "edges": [],
            "settings": {},
            "metadata": {"name": "Test Save Flow"}
        }
        
        result = save_flow_definition("test-save-flow", definition)
        
        self.assertEqual(result["flow_id"], "test-save-flow")
        self.assertEqual(result["version"], 1)
        
        # Verify it was saved
        doc = frappe.get_doc("Flow Definition", "test-save-flow")
        self.assertEqual(doc.flow_id, "test-save-flow")
        self.assertEqual(doc.status, "Draft")
    
    def test_save_flow_definition_update(self):
        """Test updating an existing flow definition."""
        # First create a flow
        definition = {
            "schema_version": 1,
            "id": "test-save-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}],
            "edges": [],
            "settings": {},
            "metadata": {"name": "Test Save Flow"}
        }
        save_flow_definition("test-save-flow", definition)
        
        # Now update it
        definition["nodes"].append({"id": "end-1", "type": "end"})
        result = save_flow_definition("test-save-flow", definition)
        
        # Version should be incremented
        self.assertEqual(result["flow_id"], "test-save-flow")
        
        # Verify it was updated
        doc = frappe.get_doc("Flow Definition", "test-save-flow")
        saved_def = json.loads(doc.definition_json)
        self.assertEqual(len(saved_def["nodes"]), 2)
    
    def test_save_flow_definition_as_string(self):
        """Test saving flow definition with JSON string."""
        definition = {
            "schema_version": 1,
            "id": "test-save-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}],
            "edges": [],
            "settings": {},
            "metadata": {"name": "Test Save Flow"}
        }
        
        # Pass as JSON string
        result = save_flow_definition("test-save-flow", json.dumps(definition))
        
        self.assertEqual(result["flow_id"], "test-save-flow")
    
    # -------------------------------------------------------------------------
    # Flow Run API Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_api.engine_run_flow")
    def test_run_flow(self, mock_run):
        """Test running a flow via API."""
        result = run_flow(
            flow_id=self.test_flow_id,
            payload={"title": "Test Task"}
        )
        
        self.assertIn("flow_run_id", result)
        self.assertIn("status", result)
        self.assertIn("current_node_id", result)
    
    @patch("huf.ai.flow_api.engine_run_flow")
    def test_run_flow_with_string_payload(self, mock_run):
        """Test running a flow with JSON string payload."""
        result = run_flow(
            flow_id=self.test_flow_id,
            payload='{"title": "Test Task"}'
        )
        
        self.assertIn("flow_run_id", result)
    
    @patch("huf.ai.flow_api.engine_run_flow")
    def test_run_flow_with_mode_override(self, mock_run):
        """Test running a flow with mode override."""
        result = run_flow(
            flow_id=self.test_flow_id,
            payload={},
            mode="agentic"
        )
        
        self.assertIn("flow_run_id", result)
    
    def test_get_flow_run(self):
        """Test getting flow run status via API."""
        # First create a flow run
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id, payload={"test": "data"})
        
        result = get_flow_run(flow_run.name)
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
        self.assertEqual(result["flow_id"], self.test_flow_id)
        self.assertEqual(result["status"], "Queued")
        self.assertIn("context_json", result)
        self.assertIn("waiting", result)
    
    def test_get_flow_run_not_found(self):
        """Test getting a non-existent flow run."""
        with self.assertRaises(frappe.DoesNotExistError):
            get_flow_run("non-existent-run")
    
    def test_list_flow_runs(self):
        """Test listing flow runs via API."""
        # Create some flow runs
        from huf.ai.flow_engine import create_flow_run
        for i in range(3):
            create_flow_run(self.test_flow_id, payload={"index": i})
        
        # List all flow runs for this flow
        results = list_flow_runs(flow_id=self.test_flow_id, limit=10)
        
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 3)
        
        # Check structure
        if results:
            self.assertIn("name", results[0])
            self.assertIn("flow_id", results[0])
            self.assertIn("status", results[0])
    
    def test_list_flow_runs_with_status_filter(self):
        """Test listing flow runs with status filter."""
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        # List with status filter
        results = list_flow_runs(flow_id=self.test_flow_id, status="Queued")
        
        self.assertIsInstance(results, list)
        for run in results:
            self.assertEqual(run["status"], "Queued")
    
    # -------------------------------------------------------------------------
    # Resume/Approval API Tests
    # -------------------------------------------------------------------------
    
    def test_resume_flow_run(self):
        """Test resuming a flow run via API."""
        # Create a flow run
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        # Set to waiting state
        flow_run.db_set({
            "status": "Waiting User",
            "waiting": json.dumps({"type": "user_input"})
        })
        frappe.db.commit()
        
        # Resume
        with patch("huf.ai.flow_api.engine_resume"):
            result = resume_flow_run(flow_run.name, input={"response": "yes"})
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
    
    def test_resume_flow_run_with_string_input(self):
        """Test resuming a flow run with JSON string input."""
        # Create a flow run
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        # Set to waiting state
        flow_run.db_set({
            "status": "Waiting User",
            "waiting": json.dumps({"type": "user_input"})
        })
        frappe.db.commit()
        
        # Resume with JSON string
        with patch("huf.ai.flow_api.engine_resume"):
            result = resume_flow_run(flow_run.name, input='{"response": "yes"}')
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
    
    def test_approve_flow_run(self):
        """Test approving a flow run via API."""
        # Create a flow run in waiting approval state
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "role",
                "approver_role": "System Manager"
            })
        })
        frappe.db.commit()
        
        # Approve
        with patch("huf.ai.flow_api.engine_approve"):
            result = approve_flow_run(flow_run.name, comment="Approved")
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
    
    def test_reject_flow_run(self):
        """Test rejecting a flow run via API."""
        # Create a flow run in waiting approval state
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "role",
                "approver_role": "System Manager"
            })
        })
        frappe.db.commit()
        
        # Reject
        with patch("huf.ai.flow_api.engine_approve"):
            result = reject_flow_run(flow_run.name, comment="Needs more info")
        
        self.assertEqual(result["flow_run_id"], flow_run.name)
    
    # -------------------------------------------------------------------------
    # Webhook API Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_api.frappe.request")
    def test_flow_webhook(self, mock_request):
        """Test webhook trigger endpoint."""
        # Create a flow with webhook trigger
        definition = {
            "schema_version": 1,
            "id": "test-webhook-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger.webhook",
                    "config": {"auth": "secret-key-123"}
                },
                {"id": "end-1", "type": "end"}
            ],
            "edges": [{"id": "e1", "from": "trigger-1", "to": "end-1", "type": "always"}],
            "settings": {},
            "metadata": {"name": "Test Webhook Flow"}
        }
        
        if frappe.db.exists("Flow Definition", "test-webhook-flow"):
            frappe.delete_doc("Flow Definition", "test-webhook-flow", force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = "test-webhook-flow"
        flow.flow_name = "Test Webhook Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
        
        # Mock request
        mock_request.is_json = True
        mock_request.get_json.return_value = {"data": "test"}
        
        # Call webhook
        with patch("huf.ai.flow_api.frappe.enqueue"):
            result = flow_webhook("test-webhook-flow", webhook_key="secret-key-123")
        
        self.assertIn("flow_run_id", result)
        self.assertEqual(result["status"], "Queued")
    
    @patch("huf.ai.flow_api.frappe.request")
    def test_flow_webhook_invalid_auth(self, mock_request):
        """Test webhook with invalid auth key."""
        # Create a flow with webhook trigger
        definition = {
            "schema_version": 1,
            "id": "test-webhook-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger.webhook",
                    "config": {"auth": "secret-key-123"}
                },
                {"id": "end-1", "type": "end"}
            ],
            "edges": [{"id": "e1", "from": "trigger-1", "to": "end-1", "type": "always"}],
            "settings": {},
            "metadata": {"name": "Test Webhook Flow"}
        }
        
        if frappe.db.exists("Flow Definition", "test-webhook-flow"):
            frappe.delete_doc("Flow Definition", "test-webhook-flow", force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = "test-webhook-flow"
        flow.flow_name = "Test Webhook Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
        
        # Call webhook with wrong key
        with self.assertRaises(frappe.AuthenticationError):
            flow_webhook("test-webhook-flow", webhook_key="wrong-key")
    
    def test_flow_webhook_inactive_flow(self):
        """Test webhook with inactive flow."""
        # Create an inactive flow
        definition = {
            "schema_version": 1,
            "id": "test-webhook-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}],
            "edges": [],
            "settings": {},
            "metadata": {"name": "Test Webhook Flow"}
        }
        
        if frappe.db.exists("Flow Definition", "test-webhook-flow"):
            frappe.delete_doc("Flow Definition", "test-webhook-flow", force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = "test-webhook-flow"
        flow.flow_name = "Test Webhook Flow"
        flow.status = "Draft"  # Inactive
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
        
        with self.assertRaises(frappe.ValidationError):
            flow_webhook("test-webhook-flow")
    
    # -------------------------------------------------------------------------
    # Schedule API Tests
    # -------------------------------------------------------------------------
    
    def test_schedule_flow(self):
        """Test scheduling a flow."""
        result = schedule_flow(
            flow_id=self.test_flow_id,
            cron="*/5 * * * *",
            schedule_name="Test Schedule"
        )
        
        self.assertEqual(result["flow_id"], self.test_flow_id)
        self.assertEqual(result["cron"], "*/5 * * * *")
        self.assertEqual(result["status"], "scheduled")
        
        # Verify scheduled job was created
        job_id = f"huf.flow.schedule.{self.test_flow_id}"
        self.assertTrue(frappe.db.exists("Scheduled Job Type", job_id))
    
    def test_schedule_flow_invalid_cron(self):
        """Test scheduling with invalid cron expression."""
        with self.assertRaises(frappe.ValidationError):
            schedule_flow(
                flow_id=self.test_flow_id,
                cron="invalid-cron"
            )
    
    def test_unschedule_flow(self):
        """Test unscheduling a flow."""
        # First schedule
        schedule_flow(self.test_flow_id, cron="*/5 * * * *")
        
        # Then unschedule
        result = unschedule_flow(self.test_flow_id)
        
        self.assertEqual(result["status"], "unscheduled")
        
        # Verify scheduled job was removed
        job_id = f"huf.flow.schedule.{self.test_flow_id}"
        self.assertFalse(frappe.db.exists("Scheduled Job Type", job_id))
    
    def test_unschedule_flow_not_found(self):
        """Test unscheduling a flow that isn't scheduled."""
        result = unschedule_flow(self.test_flow_id)
        
        self.assertEqual(result["status"], "not_found")
    
    def test_get_flow_schedule(self):
        """Test getting flow schedule details."""
        # First schedule
        schedule_flow(self.test_flow_id, cron="*/5 * * * *")
        
        # Get schedule
        result = get_flow_schedule(self.test_flow_id)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["flow_id"], self.test_flow_id)
        self.assertEqual(result["cron"], "*/5 * * * *")
        self.assertEqual(result["status"], "active")
    
    def test_get_flow_schedule_not_found(self):
        """Test getting schedule for unscheduled flow."""
        result = get_flow_schedule(self.test_flow_id)
        
        self.assertIsNone(result)
    
    # -------------------------------------------------------------------------
    # Node Schema API Tests
    # -------------------------------------------------------------------------
    
    def test_get_node_schemas(self):
        """Test getting node schema definitions."""
        result = get_node_schemas()
        
        self.assertIsInstance(result, dict)
        
        # Check for expected node types
        expected_types = [
            "trigger.webhook",
            "trigger.schedule",
            "agent.run",
            "tool.call",
            "router.llm",
            "human.approval",
            "condition",
            "http_request",
            "transform",
            "loop",
            "end"
        ]
        
        for node_type in expected_types:
            self.assertIn(node_type, result)
            self.assertIn("label", result[node_type])
            self.assertIn("icon", result[node_type])
            self.assertIn("category", result[node_type])
            self.assertIn("description", result[node_type])
            self.assertIn("config_schema", result[node_type])
    
    # -------------------------------------------------------------------------
    # Agent Tool API Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_api.engine_run_flow")
    def test_handle_run_flow(self, mock_run):
        """Test agent tool: run flow."""
        mock_run.return_value = None
        
        result = handle_run_flow(
            flow_id=self.test_flow_id,
            payload={"key": "value"}
        )
        
        self.assertTrue(result["success"])
        self.assertIn("flow_run_id", result)
    
    @patch("huf.ai.flow_api.engine_run_flow")
    def test_handle_run_flow_with_string_payload(self, mock_run):
        """Test agent tool: run flow with JSON string payload."""
        mock_run.return_value = None
        
        result = handle_run_flow(
            flow_id=self.test_flow_id,
            payload='{"key": "value"}'
        )
        
        self.assertTrue(result["success"])
    
    def test_handle_get_flow_run(self):
        """Test agent tool: get flow run."""
        # Create a flow run
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        result = handle_get_flow_run(flow_run_id=flow_run.name)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "Queued")
        self.assertIn("context_summary", result)
    
    def test_handle_get_flow_run_not_found(self):
        """Test agent tool: get non-existent flow run."""
        result = handle_get_flow_run(flow_run_id="non-existent")
        
        self.assertFalse(result["success"])
        self.assertIn("error", result)
    
    def test_handle_resume_flow_run(self):
        """Test agent tool: resume flow run."""
        # Create a flow run
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        flow_run.db_set({
            "status": "Waiting User",
            "waiting": json.dumps({"type": "user_input"})
        })
        frappe.db.commit()
        
        with patch("huf.ai.flow_api.engine_resume"):
            result = handle_resume_flow_run(
                flow_run_id=flow_run.name,
                input={"response": "yes"}
            )
        
        self.assertTrue(result["success"])
    
    def test_handle_approve_flow_run(self):
        """Test agent tool: approve/reject flow run."""
        # Create a flow run
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "role",
                "approver_role": "System Manager"
            })
        })
        frappe.db.commit()
        
        with patch("huf.ai.flow_api.engine_approve"):
            result = handle_approve_flow_run(
                flow_run_id=flow_run.name,
                decision="approved",
                comment="Looks good"
            )
        
        self.assertTrue(result["success"])
    
    # -------------------------------------------------------------------------
    # Pending Approvals API Tests
    # -------------------------------------------------------------------------
    
    def test_get_pending_approvals(self):
        """Test getting pending approvals for current user."""
        # Create a flow run in waiting approval state
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "role",
                "approver_role": "System Manager",
                "title": "Test Approval",
                "instructions": "Please approve this test"
            })
        })
        frappe.db.commit()
        
        # Get pending approvals
        result = get_pending_approvals()
        
        self.assertIsInstance(result, list)
        # Should find the approval since current user has System Manager role
        approval_ids = [a["flow_run_id"] for a in result]
        self.assertIn(flow_run.name, approval_ids)
    
    def test_get_pending_approvals_no_permission(self):
        """Test pending approvals when user doesn't have permission."""
        # Create a flow run in waiting approval state with different role
        from huf.ai.flow_engine import create_flow_run
        flow_run = create_flow_run(self.test_flow_id)
        
        flow_run.db_set({
            "status": "Waiting Approval",
            "waiting": json.dumps({
                "type": "approval",
                "approval_type": "role",
                "approver_role": "NonExistentRole123",
                "title": "Test Approval"
            })
        })
        frappe.db.commit()
        
        # Get pending approvals
        result = get_pending_approvals()
        
        # Should not include this approval
        approval_ids = [a["flow_run_id"] for a in result]
        self.assertNotIn(flow_run.name, approval_ids)


class TestFlowAPIPermissions(FrappeTestCase):
    """Tests for API permission checks."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_flow_id = "test-permissions-flow"
        self._create_test_flow()
    
    def tearDown(self):
        """Clean up test data."""
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        frappe.db.commit()
    
    def _create_test_flow(self):
        """Create a test flow definition."""
        definition = {
            "schema_version": 1,
            "id": self.test_flow_id,
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}],
            "edges": [],
            "settings": {},
            "metadata": {"name": "Test Permissions Flow"}
        }
        
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = self.test_flow_id
        flow.flow_name = "Test Permissions Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
    
    @patch("huf.ai.flow_api.frappe.has_permission")
    def test_get_flow_definition_no_permission(self, mock_has_perm):
        """Test that get_flow_definition checks permissions."""
        mock_has_perm.return_value = False
        
        with self.assertRaises(frappe.PermissionError):
            get_flow_definition(self.test_flow_id)
    
    @patch("huf.ai.flow_api.frappe.has_permission")
    def test_save_flow_definition_no_permission(self, mock_has_perm):
        """Test that save_flow_definition checks permissions."""
        mock_has_perm.return_value = False
        
        definition = {
            "schema_version": 1,
            "id": "test-new-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}],
            "edges": [],
            "settings": {},
            "metadata": {"name": "Test"}
        }
        
        with self.assertRaises(frappe.PermissionError):
            save_flow_definition("test-new-flow", definition)
    
    @patch("huf.ai.flow_api.frappe.has_permission")
    def test_run_flow_no_permission(self, mock_has_perm):
        """Test that run_flow checks permissions."""
        mock_has_perm.return_value = False
        
        with self.assertRaises(frappe.PermissionError):
            run_flow(self.test_flow_id)
