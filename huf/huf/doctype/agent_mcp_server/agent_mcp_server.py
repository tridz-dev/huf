# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document


class AgentMCPServer(Document):
    def before_insert(self):
        """Fetch tool count from MCP server"""
        self._update_tool_count()
    
    def before_save(self):
        """Update tool count on save"""
        self._update_tool_count()
    
    def _update_tool_count(self):
        """Update the tool count from the linked MCP server"""
        if self.mcp_server:
            try:
                mcp_doc = frappe.get_doc("MCP Server", self.mcp_server)
                if mcp_doc.available_tools:
                    tools = json.loads(mcp_doc.available_tools)
                    self.tool_count = len(tools) if isinstance(tools, list) else 0
                else:
                    self.tool_count = 0
            except Exception:
                self.tool_count = 0
