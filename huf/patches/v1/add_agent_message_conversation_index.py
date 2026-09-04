"""Add composite index on Agent Message (conversation, conversation_index).

The composite index serves hot queries in conversation_manager.py:
  - get_conversation_history (539-557): filters by conversation, orders by conversation_index desc
  - max conversation_index lookup (459-463): SELECT MAX(conversation_index) WHERE conversation = %s

This is a composite index only; do NOT add search_index: 1 to agent_message.json's
conversation field, which would cause Frappe schema sync to create a redundant
single-column index. The composite is required for both the filter and sort to
avoid a filesort on conversation_index.
"""

import frappe


def execute():
    """Create composite index if it does not already exist."""
    # Idempotency check: only add if not present
    result = frappe.db.sql(
        "SHOW INDEX FROM `tabAgent Message` WHERE Key_name = %s",
        ("idx_agent_message_conversation",)
    )
    if result:
        frappe.logger().info("Composite index idx_agent_message_conversation already exists, skipping")
        return

    # Create the composite index
    frappe.db.add_index(
        doctype="Agent Message",
        fields=["conversation", "conversation_index"],
        index_name="idx_agent_message_conversation"
    )
    frappe.logger().info("Created composite index on Agent Message (conversation, conversation_index)")
