import frappe
import json

def create_odoo_agents():
    """Seed pre-built Odoo Agents for common use cases."""
    
    # Define Agents
    agents = [
        {
            "agent_name": "Odoo CRM Assistant",
            "description": "Expert in Odoo CRM. Manages leads, opportunities, and customers.",
            "instructions": "You are a CRM specialist for Odoo. You help users manage leads, opportunities, and res.partner records. You can search for existing leads, update statuses, and create new contacts. Use odoo_search_read to find information before making changes.",
            "tools": ["odoo_search_read", "odoo_read", "odoo_create", "odoo_write", "odoo_fields_get", "odoo_list_models"]
        },
        {
            "agent_name": "Odoo Sales Automator",
            "description": "Handles sales orders, quotations, and product catalog.",
            "instructions": "You are a Sales expert for Odoo. Your goal is to help users manage quotations and sales orders (sale.order). You can check stock (via products), verify order statuses, and even confirm orders using odoo_execute with method 'action_confirm'. Always check for existing orders before creating new ones.",
            "tools": ["odoo_search_read", "odoo_read", "odoo_create", "odoo_write", "odoo_execute", "odoo_fields_get"]
        },
        {
            "agent_name": "Odoo Inventory Bot",
            "description": "Manages stock levels, moves, and warehouse operations.",
            "instructions": "You are an Inventory Clerk for Odoo. You help users track products (product.product), check stock levels (stock.quant), and monitor stock moves (stock.move). You can provide summaries of what is in stock and identify low-stock items.",
            "tools": ["odoo_search_read", "odoo_read", "odoo_fields_get"]
        }
    ]
    
    for agent_def in agents:
        if not frappe.db.exists("Agent", agent_def["agent_name"]):
            # Create Agent
            agent_doc = frappe.new_doc("Agent")
            agent_doc.agent_name = agent_def["agent_name"]
            agent_doc.description = agent_def["description"]
            agent_doc.instructions = agent_def["instructions"]
            agent_doc.allow_chat = 1
            agent_doc.persist_conversation = 1
            
            # Map tools
            for tool_name in agent_def["tools"]:
                if frappe.db.exists("Agent Tool Function", tool_name):
                    agent_doc.append("agent_tool", {"tool": tool_name})
            
            try:
                agent_doc.agent_name = agent_def["agent_name"]
                agent_doc.insert(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(f"Error seeding Odoo Agent {agent_def['agent_name']}: {str(e)}")
