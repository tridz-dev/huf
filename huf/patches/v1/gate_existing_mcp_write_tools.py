"""Turn on Requires Approval for already-synced MCP tools that are not read-only.

New rows default to gated unless the server marks the tool read-only; rows synced
before that default existed still have requires_approval=0.
"""

import frappe


def execute():
	frappe.reload_doc("huf", "doctype", "mcp_server_tool")
	frappe.db.sql(
		"""
		UPDATE `tabMCP Server Tool`
		SET requires_approval = 1
		WHERE IFNULL(read_only_hint, 0) = 0 AND IFNULL(requires_approval, 0) = 0
		"""
	)
