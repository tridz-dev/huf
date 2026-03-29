"""
Unit tests for HUF Flow Engine.

Tests the core flow engine functionality including:
- Flow definition loading
- Flow run creation and execution
- Node execution (triggers, tools, agents, conditions, etc.)
- Edge evaluation
- Context management
- Hop limit protection
"""

import json
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.flow_engine import (
    _exec_trigger_webhook,
    _exec_trigger_schedule,
    _exec_trigger_doc_event,
    _exec_tool_call,
    _exec_condition,
    _exec_transform,
    _exec_loop_node,
    _exec_end,
    _evaluate_edges,
    _get_outgoing_edges,
    _load_context,
    _interpolate_string,
    _substitute_dict,
    _resolve_context_path,
    load_definition,
    create_flow_run,
    run_flow,
    resume_flow_run,
    approve_flow_run,
    DEFAULT_MAX_HOPS,
)


class TestFlowEngine(FrappeTestCase):
    """Comprehensive unit tests for Flow Engine."""
    
    def setUp(self):
        """Set up test fixtures before each test."""
        self.test_flow_id = "test-flow-unit"
        self._cleanup_test_data()
        self._create_test_flow_definition()
    
    def tearDown(self):
        """Clean up test data after each test."""
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Remove all test flow definitions and runs."""
        # Clean up flow definitions
        for flow_id in [self.test_flow_id, "test-hop-limit", "test-circular"]:
            if frappe.db.exists("Flow Definition", flow_id):
                frappe.delete_doc("Flow Definition", flow_id, force=True)
        
        # Clean up flow runs
        flow_runs = frappe.get_all("Flow Run", filters={"flow_id": ["like", "test-%"]}, pluck="name")
        for run_name in flow_runs:
            frappe.delete_doc("Flow Run", run_name, force=True)
        
        frappe.db.commit()
    
    def _create_test_flow_definition(self, flow_id: str | None = None, definition: dict | None = None):
        """Create a simple test flow definition."""
        flow_id = flow_id or self.test_flow_id
        
        if definition is None:
            definition = {
                "schema_version": 1,
                "id": flow_id,
                "version": 1,
                "entry": "trigger-1",
                "nodes": [
                    {"id": "trigger-1", "type": "trigger.webhook"},
                    {
                        "id": "action-1",
                        "type": "tool.call",
                        "config": {
                            "tool_name": "create_document",
                            "parameters": {"reference_doctype": "ToDo", "description": "Test"}
                        }
                    },
                    {"id": "end-1", "type": "end"}
                ],
                "edges": [
                    {"id": "e1", "from": "trigger-1", "to": "action-1", "type": "always"},
                    {"id": "e2", "from": "action-1", "to": "end-1", "type": "always"}
                ],
                "settings": {},
                "metadata": {"name": flow_id}
            }
        
        if frappe.db.exists("Flow Definition", flow_id):
            frappe.delete_doc("Flow Definition", flow_id, force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = flow_id
        flow.flow_name = f"Test Flow {flow_id}"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
        
        return flow
    
    # -------------------------------------------------------------------------
    # Flow Definition Loading Tests
    # -------------------------------------------------------------------------
    
    def test_load_flow_definition(self):
        """Test loading a flow definition by ID."""
        flow_def = load_definition(self.test_flow_id)
        
        self.assertIsNotNone(flow_def)
        self.assertEqual(flow_def["id"], self.test_flow_id)
        self.assertEqual(len(flow_def["nodes"]), 3)
        self.assertEqual(len(flow_def["edges"]), 2)
    
    def test_load_flow_definition_inactive(self):
        """Test that loading an inactive flow raises an error."""
        # Make flow inactive
        flow = frappe.get_doc("Flow Definition", self.test_flow_id)
        flow.status = "Draft"
        flow.save()
        frappe.db.commit()
        
        with self.assertRaises(frappe.ValidationError):
            load_definition(self.test_flow_id)
    
    def test_load_flow_definition_not_found(self):
        """Test that loading a non-existent flow raises an error."""
        with self.assertRaises(frappe.DoesNotExistError):
            load_definition("non-existent-flow")
    
    # -------------------------------------------------------------------------
    # Flow Run Creation Tests
    # -------------------------------------------------------------------------
    
    def test_create_flow_run(self):
        """Test creating a new flow run."""
        payload = {"test": "data", "value": 123}
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload=payload,
            mode="normal",
            trigger_type="Manual"
        )
        
        self.assertIsNotNone(flow_run)
        self.assertEqual(flow_run.flow_id, self.test_flow_id)
        self.assertEqual(flow_run.status, "Queued")
        self.assertEqual(flow_run.current_node_id, "trigger-1")
        
        # Check context was saved
        ctx = json.loads(flow_run.context_json)
        self.assertEqual(ctx["test"], "data")
        self.assertEqual(ctx["value"], 123)
    
    def test_create_flow_run_default_payload(self):
        """Test creating a flow run with no payload."""
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        
        self.assertIsNotNone(flow_run)
        ctx = json.loads(flow_run.context_json)
        self.assertEqual(ctx, {})
    
    def test_create_flow_run_mode_inheritance(self):
        """Test that flow run inherits mode from definition settings."""
        # Create flow with specific mode
        definition = {
            "schema_version": 1,
            "id": "test-mode-flow",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [{"id": "trigger-1", "type": "trigger.webhook"}, {"id": "end-1", "type": "end"}],
            "edges": [{"id": "e1", "from": "trigger-1", "to": "end-1", "type": "always"}],
            "settings": {"mode": "agentic"},
            "metadata": {"name": "Test Mode Flow"}
        }
        self._create_test_flow_definition("test-mode-flow", definition)
        
        flow_run = create_flow_run(flow_id="test-mode-flow")
        self.assertEqual(flow_run.mode, "Agentic")
    
    # -------------------------------------------------------------------------
    # Context Loading Tests
    # -------------------------------------------------------------------------
    
    def test_load_context(self):
        """Test loading context from a flow run."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"name": "John", "age": 30, "nested": {"key": "value"}}
        )
        
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["name"], "John")
        self.assertEqual(ctx["age"], 30)
        self.assertEqual(ctx["nested"]["key"], "value")
    
    def test_load_context_empty(self):
        """Test loading empty context."""
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx, {})
    
    def test_load_context_invalid_json(self):
        """Test loading context with invalid JSON."""
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        flow_run.db_set("context_json", "invalid json")
        
        ctx = _load_context(flow_run)
        self.assertEqual(ctx, {})
    
    # -------------------------------------------------------------------------
    # String Interpolation Tests
    # -------------------------------------------------------------------------
    
    def test_interpolate_string_simple(self):
        """Test simple variable interpolation."""
        ctx = {"name": "John", "age": 30}
        
        result = _interpolate_string("Hello {{name}}!", ctx)
        self.assertEqual(result, "Hello John!")
        
        result = _interpolate_string("Age: {{age}}", ctx)
        self.assertEqual(result, "Age: 30")
    
    def test_interpolate_string_with_spaces(self):
        """Test interpolation with spaces around variable."""
        ctx = {"name": "John"}
        
        result = _interpolate_string("Hello {{ name }}!", ctx)
        self.assertEqual(result, "Hello John!")
    
    def test_interpolate_string_missing_variable(self):
        """Test interpolation with missing variable."""
        ctx = {"name": "John"}
        
        result = _interpolate_string("Hello {{missing}}!", ctx)
        self.assertEqual(result, "Hello {{missing}}!")
    
    def test_interpolate_string_nested_path(self):
        """Test interpolation with nested path."""
        ctx = {"user": {"name": "John", "email": "john@example.com"}}
        
        result = _interpolate_string("User: {{user.name}}, Email: {{user.email}}", ctx)
        self.assertEqual(result, "User: John, Email: john@example.com")
    
    def test_interpolate_string_no_placeholders(self):
        """Test string without placeholders."""
        ctx = {"name": "John"}
        
        result = _interpolate_string("Hello World!", ctx)
        self.assertEqual(result, "Hello World!")
    
    # -------------------------------------------------------------------------
    # Context Path Resolution Tests
    # -------------------------------------------------------------------------
    
    def test_resolve_context_path_simple(self):
        """Test resolving simple context paths."""
        ctx = {"name": "John", "age": 30}
        
        self.assertEqual(_resolve_context_path(ctx, "name"), "John")
        self.assertEqual(_resolve_context_path(ctx, "age"), 30)
    
    def test_resolve_context_path_nested(self):
        """Test resolving nested context paths."""
        ctx = {"user": {"profile": {"name": "John", "email": "john@example.com"}}}
        
        self.assertEqual(_resolve_context_path(ctx, "user.profile.name"), "John")
        self.assertEqual(_resolve_context_path(ctx, "user.profile.email"), "john@example.com")
    
    def test_resolve_context_path_missing(self):
        """Test resolving missing paths."""
        ctx = {"name": "John"}
        
        self.assertIsNone(_resolve_context_path(ctx, "missing"))
        self.assertIsNone(_resolve_context_path(ctx, "name.missing"))
    
    # -------------------------------------------------------------------------
    # Substitute Dict Tests
    # -------------------------------------------------------------------------
    
    def test_substitute_dict_simple(self):
        """Test substituting values in a dict."""
        ctx = {"name": "John", "value": 42}
        data = {"message": "Hello {{name}}!", "count": "{{value}}"}
        
        result = _substitute_dict(data, ctx)
        self.assertEqual(result["message"], "Hello John!")
        self.assertEqual(result["count"], "42")
    
    def test_substitute_dict_nested(self):
        """Test substituting values in nested structures."""
        ctx = {"user": "John", "id": 123}
        data = {
            "level1": {
                "level2": {
                    "name": "{{user}}"
                }
            },
            "items": ["{{id}}", "static"]
        }
        
        result = _substitute_dict(data, ctx)
        self.assertEqual(result["level1"]["level2"]["name"], "John")
        self.assertEqual(result["items"], ["123", "static"])
    
    # -------------------------------------------------------------------------
    # Trigger Executor Tests
    # -------------------------------------------------------------------------
    
    def test_exec_trigger_webhook(self):
        """Test webhook trigger execution."""
        flow_run = Mock()
        flow_run.context_json = json.dumps({"payload_key": "payload_value"})
        
        node = {"id": "trigger-1", "type": "trigger.webhook"}
        config = {}
        settings = {}
        
        result = _exec_trigger_webhook(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("output", result)
    
    def test_exec_trigger_schedule(self):
        """Test schedule trigger execution."""
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        
        node = {"id": "trigger-1", "type": "trigger.schedule"}
        config = {"cron": "*/5 * * * *", "schedule_name": "Test Schedule"}
        settings = {}
        
        result = _exec_trigger_schedule(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["trigger_type"], "schedule")
        self.assertIn("schedule_info", result)
    
    def test_exec_trigger_doc_event(self):
        """Test doc event trigger execution."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={
                "trigger": {"doctype": "ToDo", "docname": "test-doc", "event": "after_insert"},
                "doc": {"name": "test-doc", "description": "Test"}
            }
        )
        
        node = {"id": "trigger-1", "type": "trigger.doc-event"}
        config = {}
        settings = {}
        
        result = _exec_trigger_doc_event(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["trigger_type"], "doc_event")
    
    # -------------------------------------------------------------------------
    # Tool Call Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.execute")
    def test_exec_tool_call(self, mock_execute):
        """Test tool call execution with context substitution."""
        mock_execute.return_value = {"success": True, "result": {"id": "doc-123"}}
        
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"doctype": "ToDo", "desc": "Test Task"}
        )
        
        node = {"id": "action-1", "type": "tool.call"}
        config = {
            "tool_name": "create_document",
            "args": {
                "reference_doctype": "{{doctype}}",
                "description": "{{desc}}"
            }
        }
        settings = {}
        
        result = _exec_tool_call(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        # Verify the tool was called with substituted values
        call_args = mock_execute.call_args[0][1]
        self.assertEqual(call_args["reference_doctype"], "ToDo")
        self.assertEqual(call_args["description"], "Test Task")
    
    @patch("huf.ai.flow_engine.execute")
    def test_exec_tool_call_save_to_context(self, mock_execute):
        """Test tool call result saved to context."""
        mock_execute.return_value = {"success": True, "result": {"id": "doc-123"}}
        
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        
        node = {"id": "action-1", "type": "tool.call"}
        config = {
            "tool_name": "create_document",
            "args": {"reference_doctype": "ToDo"},
            "output": {"save_result_to_context": "created_doc"}
        }
        settings = {}
        
        _exec_tool_call(flow_run, node, config, settings)
        
        # Reload flow run and check context
        flow_run.reload()
        ctx = json.loads(flow_run.context_json)
        self.assertIn("created_doc", ctx)
    
    # -------------------------------------------------------------------------
    # Condition Tests
    # -------------------------------------------------------------------------
    
    def test_exec_condition_true_branch(self):
        """Test condition node with true branch."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"status": "approved"}
        )
        
        node = {"id": "cond-1", "type": "condition"}
        config = {
            "expression": 'context["status"] == "approved"',
            "true_node": "action-1",
            "false_node": "end-1"
        }
        settings = {}
        
        result = _exec_condition(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["branch"], "true")
        self.assertEqual(result["next_node_id"], "action-1")
    
    def test_exec_condition_false_branch(self):
        """Test condition node with false branch."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"status": "rejected"}
        )
        
        node = {"id": "cond-1", "type": "condition"}
        config = {
            "expression": 'context["status"] == "approved"',
            "true_node": "action-1",
            "false_node": "end-1"
        }
        settings = {}
        
        result = _exec_condition(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["branch"], "false")
        self.assertEqual(result["next_node_id"], "end-1")
    
    def test_exec_condition_missing_expression(self):
        """Test condition node without expression."""
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        
        node = {"id": "cond-1", "type": "condition"}
        config = {"true_node": "action-1"}
        settings = {}
        
        result = _exec_condition(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "failed")
        self.assertIn("missing", result["error"].lower())
    
    # -------------------------------------------------------------------------
    # Transform Tests
    # -------------------------------------------------------------------------
    
    def test_exec_transform_copy(self):
        """Test transform node with copy operation."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"source": "original_value"}
        )
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "source", "target_field": "target", "operation": "copy"}
            ]
        }
        settings = {}
        
        result = _exec_transform(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        
        # Check context was updated
        flow_run.reload()
        ctx = json.loads(flow_run.context_json)
        self.assertEqual(ctx["target"], "original_value")
    
    def test_exec_transform_template(self):
        """Test transform node with template operation."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"name": "John"}
        )
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "Hello {{name}}!", "target_field": "greeting", "operation": "template"}
            ]
        }
        settings = {}
        
        result = _exec_transform(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        
        # Check context was updated
        flow_run.reload()
        ctx = json.loads(flow_run.context_json)
        self.assertEqual(ctx["greeting"], "Hello John!")
    
    # -------------------------------------------------------------------------
    # Loop Tests
    # -------------------------------------------------------------------------
    
    def test_exec_loop_node_iteration(self):
        """Test loop node iteration."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"items": ["a", "b", "c"]}
        )
        
        node = {"id": "loop-1", "type": "loop"}
        config = {
            "iterate_over": "items",
            "item_key": "current_item",
            "index_key": "current_index",
            "loop_node": "action-1",
            "done_node": "end-1"
        }
        settings = {}
        
        result = _exec_loop_node(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "a")
        self.assertEqual(result["next_node_id"], "action-1")
        
        # Check context was updated
        flow_run.reload()
        ctx = json.loads(flow_run.context_json)
        self.assertEqual(ctx["current_item"], "a")
        self.assertEqual(ctx["current_index"], 1)
    
    def test_exec_loop_node_complete(self):
        """Test loop node when iteration is complete."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"items": ["a"], "current_index": 1, "current_item": "a"}
        )
        
        node = {"id": "loop-1", "type": "loop"}
        config = {
            "iterate_over": "items",
            "item_key": "current_item",
            "index_key": "current_index",
            "loop_node": "action-1",
            "done_node": "end-1"
        }
        settings = {}
        
        result = _exec_loop_node(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "iteration_complete")
        self.assertEqual(result["next_node_id"], "end-1")
    
    def test_exec_loop_node_not_a_list(self):
        """Test loop node when iterate_over is not a list."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"items": "not_a_list"}
        )
        
        node = {"id": "loop-1", "type": "loop"}
        config = {
            "iterate_over": "items",
            "loop_node": "action-1",
            "done_node": "end-1"
        }
        settings = {}
        
        result = _exec_loop_node(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "failed")
    
    def test_exec_loop_node_max_iterations(self):
        """Test loop node max iterations limit."""
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"items": ["a", "b", "c"], "current_index": 100}
        )
        
        node = {"id": "loop-1", "type": "loop"}
        config = {
            "iterate_over": "items",
            "item_key": "current_item",
            "index_key": "current_index",
            "loop_node": "action-1",
            "done_node": "end-1",
            "max_iterations": 100
        }
        settings = {}
        
        result = _exec_loop_node(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "max_iterations reached")
    
    # -------------------------------------------------------------------------
    # End Node Tests
    # -------------------------------------------------------------------------
    
    def test_exec_end(self):
        """Test end node execution."""
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        
        node = {"id": "end-1", "type": "end"}
        result = _exec_end(flow_run, node, {}, {})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"], "flow_complete")
    
    # -------------------------------------------------------------------------
    # Edge Evaluation Tests
    # -------------------------------------------------------------------------
    
    def test_evaluate_edges_always(self):
        """Test edge evaluation with always type."""
        edges = [
            {"id": "e1", "from": "node-1", "to": "node-2", "type": "always"}
        ]
        
        next_node = _evaluate_edges(None, "node-1", {"status": "success"}, edges)
        
        self.assertEqual(next_node, "node-2")
    
    def test_evaluate_edges_on_success(self):
        """Test edge evaluation with on_success type."""
        edges = [
            {"id": "e1", "from": "node-1", "to": "node-2", "type": "on_success"},
            {"id": "e2", "from": "node-1", "to": "node-3", "type": "on_failure"}
        ]
        
        next_node = _evaluate_edges(None, "node-1", {"status": "success"}, edges)
        self.assertEqual(next_node, "node-2")
    
    def test_evaluate_edges_on_failure(self):
        """Test edge evaluation with on_failure type."""
        edges = [
            {"id": "e1", "from": "node-1", "to": "node-2", "type": "on_success"},
            {"id": "e2", "from": "node-1", "to": "node-3", "type": "on_failure"}
        ]
        
        next_node = _evaluate_edges(None, "node-1", {"status": "failed"}, edges)
        self.assertEqual(next_node, "node-3")
    
    def test_evaluate_edges_no_match(self):
        """Test edge evaluation when no edge matches."""
        edges = [
            {"id": "e1", "from": "node-1", "to": "node-2", "type": "on_success"}
        ]
        
        next_node = _evaluate_edges(None, "node-1", {"status": "failed"}, edges)
        self.assertIsNone(next_node)
    
    def test_get_outgoing_edges(self):
        """Test getting outgoing edges from a node."""
        edges_list = [
            {"id": "e1", "from": "node-1", "to": "node-2", "type": "always", "meta": {"label": "Edge 1"}},
            {"id": "e2", "from": "node-1", "to": "node-3", "type": "always"},
            {"id": "e3", "from": "node-2", "to": "node-3", "type": "always"}
        ]
        
        candidates = _get_outgoing_edges("node-1", edges_list)
        
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["to"], "node-2")
        self.assertEqual(candidates[1]["to"], "node-3")
    
    # -------------------------------------------------------------------------
    # Hop Limit Tests
    # -------------------------------------------------------------------------
    
    def test_hop_limit_stops_infinite_loops(self):
        """Test that hop limit stops infinite loops."""
        # Create a flow with circular edges (A -> B -> A)
        definition = {
            "schema_version": 1,
            "id": "test-hop-limit",
            "version": 1,
            "entry": "node-a",
            "nodes": [
                {"id": "node-a", "type": "trigger.webhook"},
                {"id": "node-b", "type": "tool.call", "config": {"tool_name": "noop"}},
            ],
            "edges": [
                {"id": "e1", "from": "node-a", "to": "node-b", "type": "always"},
                {"id": "e2", "from": "node-b", "to": "node-a", "type": "always"}  # Creates loop
            ],
            "settings": {"max_hops": 5},
            "metadata": {"name": "Test Hop Limit"}
        }
        self._create_test_flow_definition("test-hop-limit", definition)
        
        flow_run = create_flow_run(flow_id="test-hop-limit")
        flow_run.db_set("max_hops", 5)
        frappe.db.commit()
        
        # Run the flow - it should stop at hop limit
        run_flow(flow_run.name)
        
        # Reload and check
        flow_run.reload()
        self.assertEqual(flow_run.status, "Failed")
        self.assertIn("Hop limit reached", flow_run.last_error)
    
    def test_default_max_hops(self):
        """Test that default max hops is applied."""
        self.assertEqual(DEFAULT_MAX_HOPS, 100)
    
    # -------------------------------------------------------------------------
    # Resume Flow Tests
    # -------------------------------------------------------------------------
    
    def test_resume_flow_run(self):
        """Test resuming a flow run."""
        # Create a flow run
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"initial": "data"}
        )
        
        # Simulate waiting state
        flow_run.db_set({
            "status": "Waiting User",
            "waiting": json.dumps({"type": "user_input"})
        })
        frappe.db.commit()
        
        # Resume with new input
        resume_flow_run(flow_run.name, user_input={"new": "input"})
        
        # Check that flow is running again
        flow_run.reload()
        self.assertEqual(flow_run.status, "Success")  # Flow completes since it's a simple flow
    
    # -------------------------------------------------------------------------
    # Approve Flow Tests
    # -------------------------------------------------------------------------
    
    def test_approve_flow_run(self):
        """Test approving a flow run."""
        # Create a flow with approval
        definition = {
            "schema_version": 1,
            "id": "test-approval",
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {"id": "trigger-1", "type": "trigger.webhook"},
                {"id": "approval-1", "type": "human.approval"},
                {"id": "approved-action", "type": "tool.call", "config": {"tool_name": "noop"}},
                {"id": "end-1", "type": "end"}
            ],
            "edges": [
                {"id": "e1", "from": "trigger-1", "to": "approval-1", "type": "always"},
                {"id": "e2", "from": "approval-1", "to": "approved-action", "type": "always", "meta": {"outcome": "approved"}},
                {"id": "e3", "from": "approval-1", "to": "end-1", "type": "always", "meta": {"outcome": "rejected"}},
                {"id": "e4", "from": "approved-action", "to": "end-1", "type": "always"}
            ],
            "settings": {},
            "metadata": {"name": "Test Approval Flow"}
        }
        self._create_test_flow_definition("test-approval", definition)
        
        flow_run = create_flow_run(flow_id="test-approval")
        
        # Manually set waiting approval state (simulate what _exec_human_approval does)
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
            approve_flow_run(flow_run.name, decision="approved", comment="Looks good")
        
        # Check flow was approved and continued
        flow_run.reload()
        ctx = json.loads(flow_run.context_json)
        self.assertIn("approval", ctx)
        self.assertEqual(ctx["approval"]["decision"], "approved")
    
    # -------------------------------------------------------------------------
    # HTTP Request Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.http_lib")
    def test_exec_http_request_get(self, mock_http):
        """Test HTTP request node with GET method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.headers = {"Content-Type": "application/json"}
        mock_http.request.return_value = mock_response
        
        flow_run = create_flow_run(flow_id=self.test_flow_id)
        
        from huf.ai.flow_engine import _exec_http_request
        node = {"id": "http-1", "type": "http_request"}
        config = {
            "url": "https://api.example.com/data",
            "method": "GET",
            "headers": {"Authorization": "Bearer token123"}
        }
        settings = {}
        
        result = _exec_http_request(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["status_code"], 200)
    
    @patch("huf.ai.flow_engine.http_lib")
    def test_exec_http_request_post_with_body(self, mock_http):
        """Test HTTP request node with POST method and body."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new-id"}
        mock_response.headers = {}
        mock_http.request.return_value = mock_response
        
        flow_run = create_flow_run(
            flow_id=self.test_flow_id,
            payload={"name": "Test Item"}
        )
        
        from huf.ai.flow_engine import _exec_http_request
        node = {"id": "http-1", "type": "http_request"}
        config = {
            "url": "https://api.example.com/items",
            "method": "POST",
            "body": {"name": "{{name}}"}
        }
        settings = {}
        
        result = _exec_http_request(flow_run, node, config, settings)
        
        self.assertEqual(result["status"], "success")
        # Verify POST was called with JSON body
        call_kwargs = mock_http.request.call_args[1]
        self.assertIn("json", call_kwargs)


class TestFlowEngineIntegration(FrappeTestCase):
    """Integration tests for complete flow execution."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_flow_id = "test-integration"
        self._cleanup()
    
    def tearDown(self):
        """Clean up test data."""
        self._cleanup()
    
    def _cleanup(self):
        """Remove test data."""
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        
        flow_runs = frappe.get_all("Flow Run", filters={"flow_id": self.test_flow_id}, pluck="name")
        for run_name in flow_runs:
            frappe.delete_doc("Flow Run", run_name, force=True)
        
        frappe.db.commit()
    
    @patch("huf.ai.flow_engine.execute")
    def test_complete_flow_execution(self, mock_execute):
        """Test execution of a complete flow from start to finish."""
        mock_execute.return_value = {"success": True, "result": {"id": "doc-123"}}
        
        # Create a simple linear flow
        definition = {
            "schema_version": 1,
            "id": self.test_flow_id,
            "version": 1,
            "entry": "trigger-1",
            "nodes": [
                {"id": "trigger-1", "type": "trigger.webhook"},
                {
                    "id": "tool-1",
                    "type": "tool.call",
                    "config": {
                        "tool_name": "create_document",
                        "args": {"reference_doctype": "ToDo"}
                    }
                },
                {"id": "end-1", "type": "end"}
            ],
            "edges": [
                {"id": "e1", "from": "trigger-1", "to": "tool-1", "type": "always"},
                {"id": "e2", "from": "tool-1", "to": "end-1", "type": "always"}
            ],
            "settings": {},
            "metadata": {"name": "Integration Test Flow"}
        }
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = self.test_flow_id
        flow.flow_name = "Integration Test Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
        
        # Run the flow
        from huf.ai.flow_api import run_flow
        result = run_flow(
            flow_id=self.test_flow_id,
            payload={"description": "Test ToDo"}
        )
        
        # Verify result
        self.assertIn("flow_run_id", result)
        self.assertEqual(result["status"], "Success")
        
        # Verify the flow run completed
        flow_run = frappe.get_doc("Flow Run", result["flow_run_id"])
        self.assertEqual(flow_run.status, "Success")
        self.assertEqual(flow_run.current_node_id, "end-1")
