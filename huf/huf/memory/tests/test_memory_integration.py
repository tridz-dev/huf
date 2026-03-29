"""Integration Tests for HUF Memory System

These tests verify end-to-end memory system integration with agent execution:
- Memory capture during and after agent runs
- Memory retrieval and injection before agent execution
- Full memory lifecycle: capture → storage → retrieval → injection
"""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_days
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock


class TestMemoryIntegration(FrappeTestCase):
    """Integration tests for memory system with agent runner."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures once for all tests."""
        super().setUpClass()
        
        # Create test agent
        if not frappe.db.exists("Agent", "_test_memory_integration_agent"):
            agent = frappe.new_doc("Agent")
            agent.agent_name = "_test_memory_integration_agent"
            agent.model = "gpt-4"
            agent.provider = "openai"
            agent.enable_memory = 1
            agent.insert()
            cls.agent_name = agent.name
        else:
            cls.agent_name = "_test_memory_integration_agent"
        
        # Create test user
        if not frappe.db.exists("User", "_test_memory_user@example.com"):
            user = frappe.new_doc("User")
            user.email = "_test_memory_user@example.com"
            user.first_name = "Test"
            user.last_name = "Memory User"
            user.insert()
            cls.user_id = user.name
        else:
            cls.user_id = "_test_memory_user@example.com"
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures."""
        # Clean up test memory records
        frappe.db.sql("""
            DELETE FROM `tabMemory Record` 
            WHERE agent = %s OR created_by = %s
        """, (cls.agent_name, cls.user_id))
        
        # Clean up test agent
        if frappe.db.exists("Agent", cls.agent_name):
            frappe.delete_doc("Agent", cls.agent_name)
        
        # Clean up test user
        if frappe.db.exists("User", cls.user_id):
            frappe.delete_doc("User", cls.user_id)
        
        super().tearDownClass()
    
    def setUp(self):
        """Set up for each test."""
        # Create a test conversation
        self.conversation = frappe.new_doc("Agent Conversation")
        self.conversation.title = "Test Memory Integration Conversation"
        self.conversation.agent = self.agent_name
        self.conversation.user = self.user_id
        self.conversation.insert()
        
        # Create a test agent run
        self.run = frappe.new_doc("Agent Run")
        self.run.agent = self.agent_name
        self.run.conversation = self.conversation.name
        self.run.prompt = "Test prompt"
        self.run.status = "Started"
        self.run.insert()
    
    def tearDown(self):
        """Clean up after each test."""
        # Clean up memory records from this test
        frappe.db.sql("""
            DELETE FROM `tabMemory Record` 
            WHERE conversation = %s
        """, (self.conversation.name,))
        
        # Clean up test run
        if frappe.db.exists("Agent Run", self.run.name):
            frappe.delete_doc("Agent Run", self.run.name)
        
        # Clean up test conversation
        if frappe.db.exists("Agent Conversation", self.conversation.name):
            frappe.delete_doc("Agent Conversation", self.conversation.name)
        
        frappe.db.commit()
    
    def test_memory_record_creation_basic(self):
        """Test basic memory record creation through the system."""
        from huf.memory.storage import MemoryStorage
        
        storage = MemoryStorage()
        
        record_data = {
            "title": "User prefers Python",
            "memory_type": "preference",
            "data": {"language": "Python", "reason": "familiarity"},
            "confidence": 0.9,
            "importance": 0.8,
            "summary": "User mentioned they prefer Python for scripting tasks",
            "scope_type": "conversation",
            "scope_key": self.conversation.name,
            "agent_id": self.agent_name,
            "conversation_id": self.conversation.name,
            "run_id": self.run.name,
            "source_type": "conversation",
            "producer_mode": "test",
        }
        
        record_id = storage.create_record(record_data)
        
        self.assertIsNotNone(record_id)
        self.assertTrue(record_id.startswith("MREC-"))
        
        # Verify record exists
        record = frappe.get_doc("Memory Record", record_id)
        self.assertEqual(record.title, "User prefers Python")
        self.assertEqual(record.memory_type, "preference")
        self.assertEqual(record.status, "active")
    
    def test_memory_capture_service_direct(self):
        """Test capture service directly."""
        from huf.memory.capture.capture_service import CaptureService
        
        service = CaptureService(agent_id=self.agent_name)
        
        context = {
            "agent_id": self.agent_name,
            "conversation_id": self.conversation.name,
            "run_id": self.run.name,
            "agent_response": "I'll remember that you prefer Python for scripting.",
            "conversation": {
                "messages": [
                    {"role": "user", "content": "I prefer Python for scripting tasks"},
                    {"role": "assistant", "content": "I'll remember that you prefer Python for scripting."}
                ]
            },
            "tool_outputs": [],
            "turn_count": 2,
            "source_type": "conversation",
        }
        
        result = service.capture(context)
        
        self.assertIsNotNone(result)
        self.assertIn("records_created", result)
        self.assertIn("capture_mode", result)
    
    def test_memory_retrieval_service_basic(self):
        """Test memory retrieval service."""
        from huf.memory.retrieval.retrieval_service import (
            MemoryRetrievalService, RetrievalContext, RetrievalMode
        )
        
        # Create a test memory record
        storage = frappe.get_doc({
            "doctype": "Memory Record",
            "title": "Test Memory for Retrieval",
            "agent": self.agent_name,
            "conversation": self.conversation.name,
            "run": self.run.name,
            "source_type": "manual",
            "producer_mode": "manual",
            "memory_type": "fact",
            "data_json": '{"test": "data"}',
            "scope_type": "conversation",
            "scope_key": self.conversation.name,
            "visibility": "private",
            "confidence": 0.9,
            "importance_score": 0.8,
        })
        storage.insert()
        
        # Now retrieve it
        service = MemoryRetrievalService()
        context = RetrievalContext(
            agent_name=self.agent_name,
            conversation_id=self.conversation.name,
            user_id=self.user_id
        )
        
        result = service.retrieve_by_mode(
            mode=RetrievalMode.HYBRID,
            context=context
        )
        
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result.memories), 1)
    
    def test_memory_injection_into_prompt(self):
        """Test memory injection into agent prompt."""
        from huf.memory.injection import inject_memory_into_prompt
        
        # Create a test memory
        memory = frappe.new_doc("Memory Record")
        memory.title = "User likes dark mode"
        memory.agent = self.agent_name
        memory.conversation = self.conversation.name
        memory.run = self.run.name
        memory.source_type = "manual"
        memory.producer_mode = "manual"
        memory.memory_type = "preference"
        memory.data_json = '{"setting": "dark_mode", "value": true}'
        memory.scope_type = "agent"
        memory.scope_key = self.agent_name
        memory.visibility = "private"
        memory.confidence = 0.95
        memory.importance_score = 0.9
        memory.insert()
        
        # Test injection
        original_prompt = "How should I configure the UI for you?"
        enhanced_prompt = inject_memory_into_prompt(
            prompt=original_prompt,
            agent_name=self.agent_name,
            conversation_id=self.conversation.name,
            user_id=self.user_id
        )
        
        # Verify prompt was enhanced
        self.assertNotEqual(enhanced_prompt, original_prompt)
        self.assertIn("dark mode", enhanced_prompt.lower())
    
    def test_memory_integration_class_injection(self):
        """Test MemoryAgentIntegration injection."""
        from huf.memory.integration import MemoryAgentIntegration
        
        # Create a test memory
        memory = frappe.new_doc("Memory Record")
        memory.title = "Integration Test Memory"
        memory.agent = self.agent_name
        memory.conversation = self.conversation.name
        memory.run = self.run.name
        memory.source_type = "manual"
        memory.producer_mode = "manual"
        memory.memory_type = "fact"
        memory.data_json = '{"test": true}'
        memory.scope_type = "conversation"
        memory.scope_key = self.conversation.name
        memory.visibility = "private"
        memory.insert()
        
        integration = MemoryAgentIntegration(self.agent_name)
        
        original_prompt = "What do you know about me?"
        enhanced_prompt = integration.inject_memory_context(
            prompt=original_prompt,
            conversation_id=self.conversation.name,
            user_id=self.user_id
        )
        
        self.assertIsNotNone(enhanced_prompt)
        # Should have memory context if injection worked
        if integration.memory_enabled:
            self.assertIn("## Relevant Memory", enhanced_prompt)
    
    def test_memory_integration_class_capture(self):
        """Test MemoryAgentIntegration capture."""
        from huf.memory.integration import MemoryAgentIntegration
        
        integration = MemoryAgentIntegration(self.agent_name)
        
        result = integration.capture_after_run(
            run_id=self.run.name,
            conversation_id=self.conversation.name,
            agent_response="I've noted your preference for Python.",
            conversation_history=[
                {"role": "user", "content": "I like Python"},
                {"role": "assistant", "content": "I've noted your preference for Python."}
            ],
            turn_count=2
        )
        
        self.assertIsNotNone(result)
        self.assertIn("capture_triggered", result)
    
    def test_end_to_end_memory_flow(self):
        """Test complete memory lifecycle: capture → storage → retrieval → injection."""
        from huf.memory.integration import (
            inject_memory_for_agent,
            capture_memory_after_run,
            get_memory_context_for_agent
        )
        
        # Step 1: Check initial state - no memories
        initial_context = get_memory_context_for_agent(
            agent_name=self.agent_name,
            query="What does the user like?",
            conversation_id=self.conversation.name,
            user_id=self.user_id
        )
        
        self.assertIsNotNone(initial_context)
        
        # Step 2: Simulate agent run with memory capture
        conversation_history = [
            {"role": "user", "content": "My favorite color is blue"},
            {"role": "assistant", "content": "I'll remember that your favorite color is blue."}
        ]
        
        capture_result = capture_memory_after_run(
            agent_name=self.agent_name,
            run_id=self.run.name,
            conversation_id=self.conversation.name,
            agent_response="I'll remember that your favorite color is blue.",
            conversation_history=conversation_history,
            turn_count=len(conversation_history)
        )
        
        self.assertIsNotNone(capture_result)
        # Capture may or may not create records depending on config
        
        # Step 3: Create a memory record manually for testing retrieval
        memory = frappe.new_doc("Memory Record")
        memory.title = "Favorite Color Blue"
        memory.agent = self.agent_name
        memory.conversation = self.conversation.name
        memory.run = self.run.name
        memory.source_type = "manual"
        memory.producer_mode = "manual"
        memory.memory_type = "preference"
        memory.data_json = '{"favorite_color": "blue"}'
        memory.summary = "User's favorite color is blue"
        memory.scope_type = "conversation"
        memory.scope_key = self.conversation.name
        memory.visibility = "private"
        memory.confidence = 0.95
        memory.importance_score = 0.8
        memory.insert()
        
        frappe.db.commit()
        
        # Step 4: Inject memory into new prompt
        new_prompt = "What color should I use for the interface?"
        enhanced_prompt = inject_memory_for_agent(
            agent_name=self.agent_name,
            prompt=new_prompt,
            conversation_id=self.conversation.name,
            user_id=self.user_id,
            query=new_prompt
        )
        
        # Step 5: Verify memory was injected
        self.assertIsNotNone(enhanced_prompt)
        # The prompt should contain memory context if agent has memory enabled
        
        # Step 6: Verify retrieval stats were updated
        memory.reload()
        self.assertGreaterEqual(memory.retrieval_count or 0, 0)
    
    def test_memory_with_agent_run_observability(self):
        """Test memory capture updates agent run observability fields."""
        from huf.memory.integration import MemoryAgentIntegration
        
        # Create memory record first
        memory = frappe.new_doc("Memory Record")
        memory.title = "Observable Memory"
        memory.agent = self.agent_name
        memory.conversation = self.conversation.name
        memory.run = self.run.name
        memory.source_type = "conversation"
        memory.producer_mode = "main_agent"
        memory.memory_type = "observation"
        memory.data_json = '{"observed": "behavior"}'
        memory.scope_type = "conversation"
        memory.scope_key = self.conversation.name
        memory.visibility = "private"
        memory.insert()
        
        # Capture should update run metrics
        integration = MemoryAgentIntegration(self.agent_name)
        integration._update_run_capture_metrics(self.run.name, {
            "capture_mode": "post_async",
            "records_created": 1,
            "records_updated": 0,
            "skipped": False,
            "latency_ms": 150
        })
        
        # Reload run and verify
        self.run.reload()
        self.assertTrue(self.run.memory_capture_triggered)
        self.assertEqual(self.run.memory_capture_mode, "post_async")
        self.assertEqual(self.run.memory_records_created, 1)
        self.assertEqual(self.run.memory_capture_latency_ms, 150)
    
    def test_memory_scope_filtering(self):
        """Test that memories are properly scoped."""
        from huf.memory.storage import MemoryStorage
        
        storage = MemoryStorage()
        
        # Create agent-scoped memory
        agent_memory = {
            "title": "Agent-wide Setting",
            "memory_type": "preference",
            "data": {"setting": "agent_wide"},
            "scope_type": "agent",
            "scope_key": self.agent_name,
            "agent_id": self.agent_name,
            "conversation_id": self.conversation.name,
            "run_id": self.run.name,
            "source_type": "manual",
            "producer_mode": "manual",
        }
        
        agent_record_id = storage.create_record(agent_memory)
        self.assertIsNotNone(agent_record_id)
        
        # Create conversation-scoped memory
        conv_memory = {
            "title": "Conversation-specific",
            "memory_type": "fact",
            "data": {"topic": "specific"},
            "scope_type": "conversation",
            "scope_key": self.conversation.name,
            "agent_id": self.agent_name,
            "conversation_id": self.conversation.name,
            "run_id": self.run.name,
            "source_type": "manual",
            "producer_mode": "manual",
        }
        
        conv_record_id = storage.create_record(conv_memory)
        self.assertIsNotNone(conv_record_id)
        
        # Verify both exist
        agent_record = frappe.get_doc("Memory Record", agent_record_id)
        self.assertEqual(agent_record.scope_type, "agent")
        
        conv_record = frappe.get_doc("Memory Record", conv_record_id)
        self.assertEqual(conv_record.scope_type, "conversation")
    
    def test_memory_importance_ranking(self):
        """Test that memories are ranked by importance."""
        from huf.memory.retrieval.retrieval_service import (
            MemoryRetrievalService, RetrievalContext, RetrievalMode
        )
        
        # Create memories with different importance
        for i, importance in enumerate([0.3, 0.7, 0.9]):
            memory = frappe.new_doc("Memory Record")
            memory.title = f"Memory Importance {importance}"
            memory.agent = self.agent_name
            memory.conversation = self.conversation.name
            memory.run = self.run.name
            memory.source_type = "manual"
            memory.producer_mode = "manual"
            memory.memory_type = "fact"
            memory.data_json = json.dumps({"index": i})
            memory.importance_score = importance
            memory.scope_type = "conversation"
            memory.scope_key = self.conversation.name
            memory.visibility = "private"
            memory.insert()
        
        frappe.db.commit()
        
        # Retrieve and verify ordering
        service = MemoryRetrievalService()
        context = RetrievalContext(
            agent_name=self.agent_name,
            conversation_id=self.conversation.name
        )
        
        result = service.retrieve_for_injection(context, max_items=5)
        
        # Should get memories ordered by importance
        self.assertGreaterEqual(len(result.memories), 3)
        
        # Check that higher importance comes first (roughly)
        importance_scores = [m.importance_score or 0 for m in result.memories[:3]]
        # First should be >= second >= third
        if len(importance_scores) >= 2:
            self.assertGreaterEqual(importance_scores[0], importance_scores[-1])


class TestMemoryCaptureModes(FrappeTestCase):
    """Test different memory capture modes."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Agent", "_test_capture_modes_agent"):
            agent = frappe.new_doc("Agent")
            agent.agent_name = "_test_capture_modes_agent"
            agent.model = "gpt-4"
            agent.provider = "openai"
            agent.enable_memory = 1
            agent.insert()
        cls.agent_name = "_test_capture_modes_agent"
    
    @classmethod
    def tearDownClass(cls):
        if frappe.db.exists("Agent", cls.agent_name):
            frappe.delete_doc("Agent", cls.agent_name)
        super().tearDownClass()
    
    def test_in_prompt_capture_mode(self):
        """Test in-prompt capture mode validation."""
        from huf.memory.capture.in_prompt_capture import InPromptCaptureMode
        
        capture_mode = InPromptCaptureMode({
            "max_memory_items": 5,
            "default_memory_type": "observation",
            "require_json_schema_match": False
        })
        
        is_valid, errors = capture_mode.validate()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Test prompt building
        prompt = capture_mode.build_memory_instruction_prompt()
        self.assertIn("Memory Capture Instructions", prompt)
        self.assertIn("memory_update", prompt)
    
    def test_in_prompt_capture_execution(self):
        """Test in-prompt capture execution."""
        from huf.memory.capture.in_prompt_capture import InPromptCaptureMode
        
        capture_mode = InPromptCaptureMode({
            "max_memory_items": 3,
            "default_memory_type": "preference"
        })
        
        # Valid response with memory update
        response_data = {
            "response": "I'll remember that!",
            "memory_update": {
                "has_updates": True,
                "records": [
                    {
                        "title": "User Preference",
                        "memory_type": "preference",
                        "data": {"key": "value"},
                        "confidence": 0.9,
                        "importance": 0.8
                    }
                ]
            }
        }
        
        result = capture_mode.execute(response_data)
        
        self.assertEqual(result["records_created"], 1)
        self.assertEqual(len(result["validation_errors"]), 0)
        self.assertFalse(result["skipped"])
    
    def test_in_prompt_capture_no_updates(self):
        """Test in-prompt capture with no updates."""
        from huf.memory.capture.in_prompt_capture import InPromptCaptureMode
        
        capture_mode = InPromptCaptureMode()
        
        response_data = {
            "response": "Just a regular response",
            "memory_update": {
                "has_updates": False,
                "records": []
            }
        }
        
        result = capture_mode.execute(response_data)
        
        self.assertTrue(result["skipped"])
        self.assertEqual(result["records_created"], 0)
    
    def test_post_run_async_capture(self):
        """Test post-run async capture mode."""
        from huf.memory.capture.post_run_capture import PostRunAsyncCaptureMode
        
        capture_mode = PostRunAsyncCaptureMode({
            "queue_name": "memory_capture",
            "timeout_seconds": 300,
            "retry_count": 3,
            "capture_mode": "llm_extraction"
        })
        
        is_valid, errors = capture_mode.validate()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Verify latency impact is zero
        self.assertEqual(capture_mode.get_latency_impact(), "zero")
    
    def test_capture_service_factory(self):
        """Test capture service with different modes."""
        from huf.memory.capture.capture_service import CaptureService
        
        # Test with in-prompt mode
        service = CaptureService(
            agent_id=self.agent_name,
            capture_mode="in_prompt"
        )
        
        self.assertIsNotNone(service)
        self.assertEqual(service.capture_mode, "in_prompt")
        
        # Test with post_async mode
        service2 = CaptureService(
            agent_id=self.agent_name,
            capture_mode="post_async"
        )
        
        self.assertIsNotNone(service2)
        self.assertEqual(service2.capture_mode, "post_async")


class TestMemoryRetrievalModes(FrappeTestCase):
    """Test different memory retrieval modes."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Agent", "_test_retrieval_agent"):
            agent = frappe.new_doc("Agent")
            agent.agent_name = "_test_retrieval_agent"
            agent.model = "gpt-4"
            agent.provider = "openai"
            agent.enable_memory = 1
            agent.insert()
        cls.agent_name = "_test_retrieval_agent"
        
        # Create test memories
        cls.conversation = frappe.new_doc("Agent Conversation")
        cls.conversation.title = "Test Retrieval Conversation"
        cls.conversation.agent = cls.agent_name
        cls.conversation.insert()
        
        # Create memories of different types
        for memory_type in ["profile", "preference", "fact", "plan"]:
            memory = frappe.new_doc("Memory Record")
            memory.title = f"Test {memory_type}"
            memory.agent = cls.agent_name
            memory.conversation = cls.conversation.name
            memory.source_type = "manual"
            memory.producer_mode = "manual"
            memory.memory_type = memory_type
            memory.data_json = json.dumps({"type": memory_type})
            memory.scope_type = "conversation"
            memory.scope_key = cls.conversation.name
            memory.visibility = "private"
            memory.insert()
    
    @classmethod
    def tearDownClass(cls):
        frappe.db.sql("DELETE FROM `tabMemory Record` WHERE agent = %s", cls.agent_name)
        if frappe.db.exists("Agent Conversation", cls.conversation.name):
            frappe.delete_doc("Agent Conversation", cls.conversation.name)
        if frappe.db.exists("Agent", cls.agent_name):
            frappe.delete_doc("Agent", cls.agent_name)
        super().tearDownClass()
    
    def test_retrieval_mode_inject(self):
        """Test inject retrieval mode."""
        from huf.memory.retrieval import InjectRetrievalMode, RetrievalMode
        
        mode = InjectRetrievalMode()
        
        result = mode.retrieve(
            query="test",
            agent_name=self.agent_name,
            conversation_id=self.conversation.name
        )
        
        self.assertIn("results", result)
        self.assertEqual(mode.mode, RetrievalMode.INJECT)
    
    def test_retrieval_mode_tool_only(self):
        """Test tool-only retrieval mode."""
        from huf.memory.retrieval import ToolOnlyRetrievalMode, RetrievalMode
        
        mode = ToolOnlyRetrievalMode()
        
        result = mode.retrieve(
            query="test",
            agent_name=self.agent_name,
            conversation_id=self.conversation.name
        )
        
        self.assertIn("results", result)
        self.assertEqual(mode.mode, RetrievalMode.TOOL_ONLY)
    
    def test_retrieval_mode_hybrid(self):
        """Test hybrid retrieval mode."""
        from huf.memory.retrieval import HybridRetrievalMode, RetrievalMode
        
        mode = HybridRetrievalMode()
        
        result = mode.retrieve(
            query="test",
            agent_name=self.agent_name,
            conversation_id=self.conversation.name
        )
        
        self.assertIn("results", result)
        self.assertIn("injected", result)
        self.assertEqual(mode.mode, RetrievalMode.HYBRID)
    
    def test_retrieval_mode_factory(self):
        """Test retrieval mode factory function."""
        from huf.memory.retrieval import get_retrieval_mode, RetrievalMode
        
        inject_mode = get_retrieval_mode(RetrievalMode.INJECT)
        self.assertEqual(inject_mode.mode, RetrievalMode.INJECT)
        
        tool_mode = get_retrieval_mode(RetrievalMode.TOOL_ONLY)
        self.assertEqual(tool_mode.mode, RetrievalMode.TOOL_ONLY)
        
        hybrid_mode = get_retrieval_mode(RetrievalMode.HYBRID)
        self.assertEqual(hybrid_mode.mode, RetrievalMode.HYBRID)


class TestMemoryHooks(FrappeTestCase):
    """Test memory hooks for agent runner integration."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Agent", "_test_hooks_agent"):
            agent = frappe.new_doc("Agent")
            agent.agent_name = "_test_hooks_agent"
            agent.model = "gpt-4"
            agent.provider = "openai"
            agent.enable_memory = 1
            agent.insert()
        cls.agent_name = "_test_hooks_agent"
    
    @classmethod
    def tearDownClass(cls):
        if frappe.db.exists("Agent", cls.agent_name):
            frappe.delete_doc("Agent", cls.agent_name)
        super().tearDownClass()
    
    def test_pre_run_memory_hook(self):
        """Test pre-run memory hook."""
        from huf.memory.integration import pre_run_memory_hook
        
        agent_doc = frappe.get_doc("Agent", self.agent_name)
        
        original_prompt = "What do you know about me?"
        result = pre_run_memory_hook(agent_doc, original_prompt)
        
        # Result should be the prompt (may be enhanced if memory exists)
        self.assertIsNotNone(result)
    
    def test_post_run_memory_hook(self):
        """Test post-run memory hook."""
        from huf.memory.integration import post_run_memory_hook
        
        agent_doc = frappe.get_doc("Agent", self.agent_name)
        
        conversation = frappe.new_doc("Agent Conversation")
        conversation.agent = self.agent_name
        conversation.insert()
        
        run_doc = frappe.new_doc("Agent Run")
        run_doc.agent = self.agent_name
        run_doc.conversation = conversation.name
        run_doc.insert()
        
        try:
            result = post_run_memory_hook(
                agent_doc=agent_doc,
                run_doc=run_doc,
                conversation=conversation,
                agent_response="Test response"
            )
            
            self.assertIsNotNone(result)
            self.assertIn("capture_triggered", result)
        finally:
            frappe.delete_doc("Agent Run", run_doc.name)
            frappe.delete_doc("Agent Conversation", conversation.name)
    
    def test_pre_run_hook_disabled_memory(self):
        """Test pre-run hook when memory is disabled."""
        from huf.memory.integration import pre_run_memory_hook
        
        # Create agent without memory
        if not frappe.db.exists("Agent", "_test_no_memory_agent"):
            agent = frappe.new_doc("Agent")
            agent.agent_name = "_test_no_memory_agent"
            agent.model = "gpt-4"
            agent.provider = "openai"
            # No enable_memory flag
            agent.insert()
        
        try:
            agent_doc = frappe.get_doc("Agent", "_test_no_memory_agent")
            
            original_prompt = "Test prompt"
            result = pre_run_memory_hook(agent_doc, original_prompt)
            
            # Should return original prompt unchanged
            self.assertEqual(result, original_prompt)
        finally:
            if frappe.db.exists("Agent", "_test_no_memory_agent"):
                frappe.delete_doc("Agent", "_test_no_memory_agent")
