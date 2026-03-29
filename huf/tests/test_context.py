"""
Context Passing tests for HUF Flow Engine.

Tests context handling including:
- Trigger payload in context
- Tool result saved to context
- Variable interpolation ({{variable}})
- Nested context access
- Context persistence across nodes
- Context transformation
"""

import json
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.flow_engine import (
    _load_context,
    _interpolate_string,
    _substitute_dict,
    _resolve_context_path,
    _exec_trigger_webhook,
    _exec_trigger_schedule,
    _exec_trigger_doc_event,
    _exec_tool_call,
    _exec_transform,
    create_flow_run,
)


class TestContextPassing(FrappeTestCase):
    """Comprehensive tests for context passing functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_flow_id = "test-context-flow"
        self._cleanup_test_data()
        self._create_test_flow()
    
    def tearDown(self):
        """Clean up test data."""
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Remove all test data."""
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        
        flow_runs = frappe.get_all("Flow Run", filters={"flow_id": self.test_flow_id}, pluck="name")
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
                {"id": "action-1", "type": "tool.call", "config": {"tool_name": "create_document"}},
                {"id": "end-1", "type": "end"}
            ],
            "edges": [
                {"id": "e1", "from": "trigger-1", "to": "action-1", "type": "always"},
                {"id": "e2", "from": "action-1", "to": "end-1", "type": "always"}
            ],
            "settings": {},
            "metadata": {"name": "Test Context Flow"}
        }
        
        if frappe.db.exists("Flow Definition", self.test_flow_id):
            frappe.delete_doc("Flow Definition", self.test_flow_id, force=True)
        
        flow = frappe.new_doc("Flow Definition")
        flow.flow_id = self.test_flow_id
        flow.flow_name = "Test Context Flow"
        flow.status = "Active"
        flow.definition_json = json.dumps(definition)
        flow.insert()
        frappe.db.commit()
    
    def _create_flow_run(self, payload: dict = None) -> "frappe.Document":
        """Helper to create a flow run."""
        return create_flow_run(
            flow_id=self.test_flow_id,
            payload=payload or {}
        )
    
    # -------------------------------------------------------------------------
    # Trigger Payload Tests
    # -------------------------------------------------------------------------
    
    def test_trigger_payload_in_context(self):
        """Test that trigger payload is available in context."""
        payload = {
            "title": "Test Task",
            "priority": "High",
            "metadata": {"source": "webhook", "id": 123}
        }
        
        flow_run = self._create_flow_run(payload=payload)
        
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["title"], "Test Task")
        self.assertEqual(ctx["priority"], "High")
        self.assertEqual(ctx["metadata"]["source"], "webhook")
        self.assertEqual(ctx["metadata"]["id"], 123)
    
    def test_trigger_payload_empty(self):
        """Test flow run with empty payload."""
        flow_run = self._create_flow_run(payload={})
        
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx, {})
    
    def test_trigger_webhook_preserves_context(self):
        """Test that webhook trigger preserves context."""
        flow_run = self._create_flow_run(payload={"key": "value"})
        
        node = {"id": "trigger-1", "type": "trigger.webhook"}
        result = _exec_trigger_webhook(flow_run, node, {}, {})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"]["key"], "value")
    
    def test_trigger_schedule_adds_metadata(self):
        """Test that schedule trigger adds metadata to context."""
        flow_run = self._create_flow_run(payload={"initial": "data"})
        
        node = {"id": "trigger-1", "type": "trigger.schedule"}
        config = {"cron": "*/5 * * * *", "schedule_name": "Test Schedule"}
        
        result = _exec_trigger_schedule(flow_run, node, config, {})
        
        # Reload and check context
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertIn("_schedule_trigger", ctx)
        self.assertEqual(ctx["_schedule_trigger"]["trigger_type"], "schedule")
        self.assertEqual(ctx["_schedule_trigger"]["cron_expression"], "*/5 * * * *")
        self.assertEqual(ctx["_schedule_trigger"]["schedule_name"], "Test Schedule")
        self.assertIn("triggered_at", ctx["_schedule_trigger"])
    
    def test_trigger_doc_event_adds_doc_context(self):
        """Test that doc event trigger adds document context."""
        payload = {
            "trigger": {"doctype": "ToDo", "docname": "todo-001", "event": "after_insert"},
            "doc": {"name": "todo-001", "description": "Test Task"}
        }
        
        flow_run = self._create_flow_run(payload=payload)
        
        node = {"id": "trigger-1", "type": "trigger.doc-event"}
        
        result = _exec_trigger_doc_event(flow_run, node, {}, {})
        
        # Reload and check context
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertIn("_doc_event_trigger", ctx)
        self.assertEqual(ctx["_doc_event_trigger"]["doctype"], "ToDo")
        self.assertEqual(ctx["_doc_event_trigger"]["docname"], "todo-001")
        self.assertEqual(ctx["_doc_event_trigger"]["event"], "after_insert")
        self.assertEqual(ctx["doc"]["name"], "todo-001")
    
    # -------------------------------------------------------------------------
    # Tool Result Context Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.execute")
    def test_tool_result_saved_to_context(self, mock_execute):
        """Test that tool results are saved to context."""
        mock_execute.return_value = {"success": True, "result": {"id": "doc-123", "name": "Test Doc"}}
        
        flow_run = self._create_flow_run(payload={})
        
        node = {"id": "action-1", "type": "tool.call"}
        config = {
            "tool_name": "create_document",
            "args": {"reference_doctype": "ToDo"},
            "output": {"save_result_to_context": "created_doc"}
        }
        
        _exec_tool_call(flow_run, node, config, {})
        
        # Reload and check context
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertIn("created_doc", ctx)
        self.assertEqual(ctx["created_doc"]["id"], "doc-123")
        self.assertEqual(ctx["created_doc"]["name"], "Test Doc")
    
    @patch("huf.ai.flow_engine.execute")
    def test_tool_result_without_save_config(self, mock_execute):
        """Test that tool results are not saved without config."""
        mock_execute.return_value = {"success": True, "result": {"id": "doc-123"}}
        
        flow_run = self._create_flow_run(payload={"existing": "data"})
        
        node = {"id": "action-1", "type": "tool.call"}
        config = {
            "tool_name": "create_document",
            "args": {"reference_doctype": "ToDo"}
            # No save_result_to_context
        }
        
        _exec_tool_call(flow_run, node, config, {})
        
        # Reload and check context
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        # Context should only have original data
        self.assertEqual(ctx, {"existing": "data"})
    
    # -------------------------------------------------------------------------
    # Variable Interpolation Tests
    # -------------------------------------------------------------------------
    
    def test_variable_interpolation_simple(self):
        """Test simple {{variable}} interpolation."""
        ctx = {"name": "John", "age": 30}
        
        result = _interpolate_string("Hello {{name}}!", ctx)
        self.assertEqual(result, "Hello John!")
    
    def test_variable_interpolation_multiple(self):
        """Test multiple variable interpolation."""
        ctx = {"first": "John", "last": "Doe", "age": 30}
        
        result = _interpolate_string("{{first}} {{last}} is {{age}} years old", ctx)
        self.assertEqual(result, "John Doe is 30 years old")
    
    def test_variable_interpolation_spaces(self):
        """Test interpolation with spaces around variable."""
        ctx = {"name": "John"}
        
        result = _interpolate_string("Hello {{ name }}!", ctx)
        self.assertEqual(result, "Hello John!")
        
        result = _interpolate_string("Hello {{  name  }}!", ctx)
        self.assertEqual(result, "Hello John!")
    
    def test_variable_interpolation_missing(self):
        """Test interpolation with missing variable."""
        ctx = {"name": "John"}
        
        result = _interpolate_string("Hello {{missing}}!", ctx)
        # Missing variables should keep the placeholder
        self.assertEqual(result, "Hello {{missing}}!")
    
    def test_variable_interpolation_nested(self):
        """Test nested variable interpolation."""
        ctx = {"user": {"profile": {"name": "John", "email": "john@example.com"}}}
        
        result = _interpolate_string("User: {{user.profile.name}}, Email: {{user.profile.email}}", ctx)
        self.assertEqual(result, "User: John, Email: john@example.com")
    
    def test_variable_interpolation_deeply_nested(self):
        """Test deeply nested variable interpolation."""
        ctx = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "found"
                    }
                }
            }
        }
        
        result = _interpolate_string("Value: {{level1.level2.level3.value}}", ctx)
        self.assertEqual(result, "Value: found")
    
    def test_variable_interpolation_types(self):
        """Test interpolation with different data types."""
        ctx = {
            "string": "text",
            "number": 42,
            "boolean": True,
            "null": None
        }
        
        self.assertEqual(_interpolate_string("{{string}}", ctx), "text")
        self.assertEqual(_interpolate_string("{{number}}", ctx), "42")
        self.assertEqual(_interpolate_string("{{boolean}}", ctx), "True")
        self.assertEqual(_interpolate_string("{{null}}", ctx), "{{null}}")  # None stays as placeholder
    
    # -------------------------------------------------------------------------
    # Nested Context Access Tests
    # -------------------------------------------------------------------------
    
    def test_nested_context_access_simple(self):
        """Test simple nested context access."""
        ctx = {"user": {"name": "John"}}
        
        self.assertEqual(_resolve_context_path(ctx, "user.name"), "John")
    
    def test_nested_context_access_deep(self):
        """Test deep nested context access."""
        ctx = {
            "a": {
                "b": {
                    "c": {
                        "d": "value"
                    }
                }
            }
        }
        
        self.assertEqual(_resolve_context_path(ctx, "a.b.c.d"), "value")
    
    def test_nested_context_access_array_index(self):
        """Test nested context with array access."""
        ctx = {
            "items": [
                {"name": "first"},
                {"name": "second"}
            ]
        }
        
        # Note: This would require additional implementation for array indexing
        # For now, we test the basic behavior
        self.assertEqual(_resolve_context_path(ctx, "items"), [{"name": "first"}, {"name": "second"}])
    
    def test_nested_context_access_missing_key(self):
        """Test nested context access with missing key."""
        ctx = {"user": {"name": "John"}}
        
        self.assertIsNone(_resolve_context_path(ctx, "user.email"))
        self.assertIsNone(_resolve_context_path(ctx, "profile.name"))
    
    def test_nested_context_access_non_dict(self):
        """Test nested context access on non-dict value."""
        ctx = {"name": "John"}
        
        # Trying to access property of a string should return None
        self.assertIsNone(_resolve_context_path(ctx, "name.first"))
    
    # -------------------------------------------------------------------------
    # Substitute Dict Tests
    # -------------------------------------------------------------------------
    
    def test_substitute_dict_simple(self):
        """Test simple dict value substitution."""
        ctx = {"name": "John", "value": 42}
        data = {"message": "Hello {{name}}!", "count": "{{value}}"}
        
        result = _substitute_dict(data, ctx)
        
        self.assertEqual(result["message"], "Hello John!")
        self.assertEqual(result["count"], "42")
    
    def test_substitute_dict_nested(self):
        """Test nested dict substitution."""
        ctx = {"user": "John", "id": 123}
        data = {
            "level1": {
                "level2": {
                    "name": "{{user}}"
                }
            }
        }
        
        result = _substitute_dict(data, ctx)
        
        self.assertEqual(result["level1"]["level2"]["name"], "John")
    
    def test_substitute_dict_with_arrays(self):
        """Test dict substitution with arrays."""
        ctx = {"id": 123, "name": "John"}
        data = {
            "items": ["{{id}}", "{{name}}", "static"],
            "nested": [{"key": "{{id}}"}]
        }
        
        result = _substitute_dict(data, ctx)
        
        self.assertEqual(result["items"], ["123", "John", "static"])
        self.assertEqual(result["nested"][0]["key"], "123")
    
    def test_substitute_dict_mixed_types(self):
        """Test dict substitution with mixed types."""
        ctx = {"name": "John"}
        data = {
            "string": "{{name}}",
            "number": 42,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {"key": "value"}
        }
        
        result = _substitute_dict(data, ctx)
        
        self.assertEqual(result["string"], "John")
        self.assertEqual(result["number"], 42)
        self.assertEqual(result["boolean"], True)
        self.assertIsNone(result["null"])
        self.assertEqual(result["array"], [1, 2, 3])
        self.assertEqual(result["nested"], {"key": "value"})
    
    # -------------------------------------------------------------------------
    # Transform Node Context Tests
    # -------------------------------------------------------------------------
    
    def test_transform_copy_operation(self):
        """Test transform node copy operation."""
        flow_run = self._create_flow_run(payload={"source": "original_value"})
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "source", "target_field": "target", "operation": "copy"}
            ]
        }
        
        _exec_transform(flow_run, node, config, {})
        
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["source"], "original_value")
        self.assertEqual(ctx["target"], "original_value")
    
    def test_transform_template_operation(self):
        """Test transform node template operation."""
        flow_run = self._create_flow_run(payload={"name": "John", "age": 30})
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "Hello {{name}}, you are {{age}} years old", "target_field": "greeting", "operation": "template"}
            ]
        }
        
        _exec_transform(flow_run, node, config, {})
        
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["greeting"], "Hello John, you are 30 years old")
    
    def test_transform_map_operation(self):
        """Test transform node map operation."""
        flow_run = self._create_flow_run(payload={"old_key": "value"})
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "old_key", "target_field": "new_key", "operation": "map"}
            ]
        }
        
        _exec_transform(flow_run, node, config, {})
        
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["old_key"], "value")
        self.assertEqual(ctx["new_key"], "value")
    
    def test_transform_nested_path(self):
        """Test transform node with nested source path."""
        flow_run = self._create_flow_run(payload={"user": {"profile": {"name": "John"}}})
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "user.profile.name", "target_field": "username", "operation": "copy"}
            ]
        }
        
        _exec_transform(flow_run, node, config, {})
        
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["username"], "John")
    
    def test_transform_multiple_operations(self):
        """Test transform node with multiple operations."""
        flow_run = self._create_flow_run(payload={
            "first": "John",
            "last": "Doe",
            "age": 30
        })
        
        node = {"id": "transform-1", "type": "transform"}
        config = {
            "transformations": [
                {"source_field": "first", "target_field": "first_name", "operation": "copy"},
                {"source_field": "last", "target_field": "last_name", "operation": "copy"},
                {"source_field": "Hello {{first}} {{last}}", "target_field": "full_greeting", "operation": "template"}
            ]
        }
        
        _exec_transform(flow_run, node, config, {})
        
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["first_name"], "John")
        self.assertEqual(ctx["last_name"], "Doe")
        self.assertEqual(ctx["full_greeting"], "Hello John Doe")
    
    # -------------------------------------------------------------------------
    # Context Persistence Tests
    # -------------------------------------------------------------------------
    
    def test_context_persists_across_nodes(self):
        """Test that context persists and accumulates across node execution."""
        flow_run = self._create_flow_run(payload={"step1": "data"})
        
        # Simulate first node execution
        ctx = _load_context(flow_run)
        ctx["step2"] = "more_data"
        flow_run.db_set("context_json", json.dumps(ctx))
        frappe.db.commit()
        
        # Reload and verify
        flow_run.reload()
        ctx = _load_context(flow_run)
        
        self.assertEqual(ctx["step1"], "data")
        self.assertEqual(ctx["step2"], "more_data")
    
    def test_context_accumulation(self):
        """Test that context accumulates values from multiple nodes."""
        flow_run = self._create_flow_run(payload={"trigger": "value"})
        
        # Simulate multiple node results being added
        ctx = _load_context(flow_run)
        ctx["node1_result"] = "result1"
        flow_run.db_set("context_json", json.dumps(ctx))
        frappe.db.commit()
        
        ctx = _load_context(flow_run)
        ctx["node2_result"] = "result2"
        flow_run.db_set("context_json", json.dumps(ctx))
        frappe.db.commit()
        
        ctx = _load_context(flow_run)
        ctx["node3_result"] = "result3"
        flow_run.db_set("context_json", json.dumps(ctx))
        frappe.db.commit()
        
        # Verify all values are present
        ctx = _load_context(flow_run)
        self.assertEqual(ctx["trigger"], "value")
        self.assertEqual(ctx["node1_result"], "result1")
        self.assertEqual(ctx["node2_result"], "result2")
        self.assertEqual(ctx["node3_result"], "result3")
    
    # -------------------------------------------------------------------------
    # Tool Call Context Substitution Tests
    # -------------------------------------------------------------------------
    
    @patch("huf.ai.flow_engine.execute")
    def test_tool_call_with_context_substitution(self, mock_execute):
        """Test tool call with context variable substitution in args."""
        mock_execute.return_value = {"success": True, "result": {}}
        
        flow_run = self._create_flow_run(payload={
            "doctype": "ToDo",
            "desc": "Test Task",
            "priority": "High"
        })
        
        node = {"id": "action-1", "type": "tool.call"}
        config = {
            "tool_name": "create_document",
            "args": {
                "reference_doctype": "{{doctype}}",
                "description": "{{desc}}",
                "priority": "{{priority}}"
            }
        }
        
        _exec_tool_call(flow_run, node, config, {})
        
        # Verify tool was called with substituted values
        call_args = mock_execute.call_args[0][1]
        self.assertEqual(call_args["reference_doctype"], "ToDo")
        self.assertEqual(call_args["description"], "Test Task")
        self.assertEqual(call_args["priority"], "High")
    
    @patch("huf.ai.flow_engine.execute")
    def test_tool_call_with_nested_context_substitution(self, mock_execute):
        """Test tool call with nested context variable substitution."""
        mock_execute.return_value = {"success": True, "result": {}}
        
        flow_run = self._create_flow_run(payload={
            "doc": {
                "name": "Test Doc",
                "values": {"key1": "val1", "key2": "val2"}
            }
        })
        
        node = {"id": "action-1", "type": "tool.call"}
        config = {
            "tool_name": "create_document",
            "args": {
                "name": "{{doc.name}}",
                "data": "{{doc.values}}"
            }
        }
        
        _exec_tool_call(flow_run, node, config, {})
        
        # Verify tool was called with substituted values
        call_args = mock_execute.call_args[0][1]
        self.assertEqual(call_args["name"], "Test Doc")
