
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
from huf.ai.knowledge.tool import (
    create_knowledge_search_tool,
    handle_knowledge_search,
    create_get_knowledge_sources_tool,
    handle_get_knowledge_sources
)

class TestKnowledgeTool(FrappeTestCase):
    def setUp(self):
        # Create dependencies
        if not frappe.db.exists("AI Provider", "Test Provider"):
            frappe.get_doc({
                "doctype": "AI Provider",
                "provider_name": "Test Provider",
                "api_key": "dummy-key"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("AI Model", "gpt-4"):
            frappe.get_doc({
                "doctype": "AI Model",
                "model_name": "gpt-4",
                "provider": "Test Provider"
            }).insert(ignore_permissions=True)
            
        self.source_1 = "Test Source Mandatory"
        if not frappe.db.exists("Knowledge Source", self.source_1):
            frappe.get_doc({
                "doctype": "Knowledge Source",
                "source_name": self.source_1,
                "scope": "Global",
                "storage_mode": "Frappe File",
                "knowledge_type": "sqlite_fts",
                "status": "Ready",
                "chunk_size": 512,
                "chunk_overlap": 50
            }).insert(ignore_permissions=True)

        self.source_2 = "Test Source Optional"
        if not frappe.db.exists("Knowledge Source", self.source_2):
            frappe.get_doc({
                "doctype": "Knowledge Source",
                "source_name": self.source_2,
                "scope": "Global",
                "storage_mode": "Frappe File",
                "knowledge_type": "sqlite_fts",
                "status": "Ready",
                "chunk_size": 512,
                "chunk_overlap": 50
            }).insert(ignore_permissions=True)

        self.agent_name = "Test Tool Agent"
        if frappe.db.exists("Agent", self.agent_name):
            frappe.delete_doc("Agent", self.agent_name, force=True)
        
        doc = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": self.agent_name,
            "provider": "Test Provider",
            "model": "gpt-4",
            "instructions": "You are a test agent.",
            "agent_knowledge": [
                {
                    "knowledge_source": self.source_1,
                    "mode": "Mandatory",
                    "priority": 10
                },
                {
                    "knowledge_source": self.source_2,
                    "mode": "Optional",
                    "priority": 5
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        
    def tearDown(self):
        frappe.delete_doc("Agent", self.agent_name, force=True)
        if frappe.db.exists("Knowledge Source", self.source_1):
            frappe.delete_doc("Knowledge Source", self.source_1, force=True)
        if frappe.db.exists("Knowledge Source", self.source_2):
            frappe.delete_doc("Knowledge Source", self.source_2, force=True)

    def test_create_knowledge_search_tool(self):
        tool = create_knowledge_search_tool(self.agent_name)
        self.assertIsNotNone(tool)
        self.assertEqual(tool["tool_name"], "knowledge_search")
        # Check description contains both sources
        self.assertIn(self.source_1, tool["description"])
        self.assertIn(self.source_2, tool["description"])
        self.assertIn("(Mandatory)", tool["description"])
        self.assertIn("(Optional)", tool["description"])

    def test_handle_knowledge_search_allowed_sources(self):
        # Mock actual search to avoid backend calls
        with patch("huf.ai.knowledge.tool.knowledge_search") as mock_search:
            mock_search.return_value = [{"text": "Result 1", "title": "Doc 1", "score": 0.9, "source": self.source_1}]
            
            # Test explicit search in Mandatory source (now allowed)
            res = handle_knowledge_search(self.agent_name, "query", self.source_1)
            self.assertIn("Result 1", res)
            self.assertIn(self.source_1, res)
            
            # Test explicit search in Optional source
            mock_search.return_value = [{"text": "Result 2", "title": "Doc 2", "score": 0.8, "source": self.source_2}]
            res = handle_knowledge_search(self.agent_name, "query", self.source_2)
            self.assertIn("Result 2", res)
            
    def test_handle_knowledge_search_invalid_source(self):
        res = handle_knowledge_search(self.agent_name, "query", "NonExistent")
        self.assertIn("Error: Knowledge source 'NonExistent' is not available", res)
        # Check that it lists available sources
        self.assertIn(self.source_1, res)
        self.assertIn(self.source_2, res)

    def test_create_get_knowledge_sources_tool(self):
        tool = create_get_knowledge_sources_tool(self.agent_name)
        self.assertIsNotNone(tool)
        self.assertEqual(tool["tool_name"], "get_knowledge_sources")

    def test_handle_get_knowledge_sources(self):
        res = handle_get_knowledge_sources(self.agent_name)
        self.assertIn("Available Knowledge Sources:", res)
        self.assertIn(self.source_1, res)
        self.assertIn("Mandatory", res)
        self.assertIn(self.source_2, res)
        self.assertIn("Optional", res)
