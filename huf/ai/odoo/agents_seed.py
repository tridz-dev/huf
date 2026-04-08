import frappe

def create_odoo_agents():
    """Seed pre-built Odoo Agents for common use cases."""

    # Try to find a default model to use
    default_model = frappe.db.get_value(
        "AI Model", {"enabled": 1}, "name", order_by="creation asc"
    )

    agents = [
        {
            "agent_name": "Odoo CRM Assistant",
            "description": "Handles lead qualification, CRM updates, and customer research.",
            "instructions": "You are a CRM expert. Use search_read to find leads, write to update stages, and execute to confirm actions.",
            "tools": ["odoo_search_read", "odoo_read", "odoo_write", "odoo_execute"]
        },
        {
            "agent_name": "Odoo Sales Automation",
            "description": "Assists with quote generation and sales order management.",
            "instructions": "Help users manage sales orders. Use create to make quotes and read_group to analyze performance.",
            "tools": ["odoo_search_read", "odoo_read", "odoo_create", "odoo_write", "odoo_read_group"]
        },
        {
            "agent_name": "Odoo Inventory Manager",
            "description": "Tracks stock levels and stock move status.",
            "instructions": "You monitor inventory. Use search_count to check stock levels and read to get movement details.",
            "tools": ["odoo_search_read", "odoo_search_count", "odoo_read"]
        }
    ]

    for agent_def in agents:
        if not frappe.db.exists("Agent", agent_def["agent_name"]):
            agent_doc = frappe.new_doc("Agent")
            agent_doc.agent_name = agent_def["agent_name"]
            agent_doc.description = agent_def["description"]
            agent_doc.instructions = agent_def["instructions"]
            agent_doc.allow_chat = 1
            agent_doc.persist_conversation = 1

            # Set model if one exists
            if default_model:
                agent_doc.model = default_model

            for tool_name in agent_def["tools"]:
                if frappe.db.exists("Agent Tool Function", tool_name):
                    agent_doc.append("agent_tool", {"tool": tool_name})

            try:
                agent_doc.insert(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(f"Error seeding Odoo Agent {agent_def['agent_name']}: {str(e)}")
