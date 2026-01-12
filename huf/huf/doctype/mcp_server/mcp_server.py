# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MCPServer(Document):
    def validate(self):
        """Validate MCP server configuration"""
        if self.auth_type and self.auth_type != "none":
            if not self.auth_header_name:
                frappe.throw("Auth Header Name is required when authentication is enabled")
    
    def before_save(self):
        """Format auth header based on auth type"""
        if self.auth_type == "bearer_token" and self.auth_header_name == "Authorization":
            # Will be formatted as "Bearer <token>" during request
            pass
    
    @frappe.whitelist()
    def sync_tools(self):
        """Fetch and cache available tools from the MCP server"""
        from huf.ai.mcp_client import sync_mcp_server_tools
        
        result = sync_mcp_server_tools(self.name)
        
        if result.get("success"):
            frappe.msgprint(
                f"Successfully synced {result.get('tool_count', 0)} tools from {self.server_name}",
                indicator="green",
                title="MCP Tools Synced"
            )
        else:
            frappe.msgprint(
                f"Failed to sync tools: {result.get('error', 'Unknown error')}",
                indicator="red",
                title="Sync Failed"
            )
        
        return result
