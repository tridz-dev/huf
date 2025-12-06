"""
Canvas Editor API
Handles agent communication and canvas operations
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_canvas_metadata(slug):
    """Get canvas metadata including agent info"""
    # TEMPORARY: Hardcode agent to "canvas" for testing
    # TODO: Fix Canvas DocType record retrieval
    hardcoded_agent = "canvas"
    
    try:
        canvas = frappe.get_doc("Canvas", {"slug": slug})
        agent_name = canvas.agent or hardcoded_agent
        allow_editing = canvas.allow_editing
        canvas_title = canvas.title
        canvas_name = canvas.name
        canvas_description = canvas.description
        canvas_mode = canvas.mode
    except:
        # If Canvas record doesn't exist, use defaults
        agent_name = hardcoded_agent
        allow_editing = 1
        canvas_title = slug.replace("-", " ").title()
        canvas_name = slug
        canvas_description = f"Canvas for {slug}"
        canvas_mode = "canvas"
    
    agent_info = None
    try:
        agent = frappe.get_doc("Agent", agent_name)
        agent_info = {
            "name": agent.agent_name,
            "description": agent.description,
            "instructions": agent.instructions
        }
    except:
        # Agent not found, but still return success with null agent_info
        pass
    
    return {
        "success": True,
        "canvas": {
            "name": canvas_name,
            "title": canvas_title,
            "slug": slug,
            "agent": agent_name,
            "description": canvas_description,
            "allow_editing": allow_editing,
            "mode": canvas_mode
        },
        "agent": agent_info
    }


@frappe.whitelist()
def send_canvas_message(slug, message):
    """Send message to canvas agent"""
    try:
        # TEMPORARY: Hardcode agent to "canvas" for testing
        hardcoded_agent = "canvas"
        
        # Get canvas or use defaults
        try:
            canvas = frappe.get_doc("Canvas", {"slug": slug})
            agent_name = canvas.agent or hardcoded_agent
            allow_editing = canvas.allow_editing
        except:
            # Canvas record doesn't exist, use defaults
            agent_name = hardcoded_agent
            allow_editing = 1
        
        if not allow_editing:
            frappe.throw(_("Editing not allowed for this canvas"))
        
        if not agent_name:
            frappe.throw(_("No agent assigned to this canvas"))
        
        # Import agent integration
        from huf.ai.agent_integration import run_agent_sync
        from huf.ai.canvas_tools import read_canvas_file
        
        # Prepare context with canvas info
        context = {
            "canvas_slug": slug,
            "canvas_mode": "canvas"
        }
        
        # Build enhanced prompt with canvas context
        agents_md_result = read_canvas_file(slug, "agents.md")
        agents_md_content = agents_md_result.get("content", "") if agents_md_result.get("success") else ""
        
        enhanced_prompt = f"""
Canvas: {slug}

{agents_md_content}

USER REQUEST: {message}

IMPORTANT: Use your tools immediately. Do not explain what you will do - just do it. Call read_canvas_file() and write_canvas_files() directly.
"""
        
        # Get provider and model from agent
        agent_doc = frappe.get_doc("Agent", agent_name)
        provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
        model_doc = frappe.get_doc("AI Model", agent_doc.model)
        
        # DEBUG: Log context and tools
        frappe.logger().info(f"Canvas API - Calling agent with context: {context}")
        frappe.logger().info(f"Canvas API - Agent: {agent_name}, Provider: {provider_doc.provide_name}, Model: {model_doc.model_name}")
        
        # DEBUG: Check what tools the agent has
        agent_tools = frappe.get_all("Agent Tool", filters={"parent": agent_name}, fields=["tool"])
        frappe.logger().info(f"Canvas API - Agent tools from DB: {[t.tool for t in agent_tools]}")
        
        # Call agent
        result = run_agent_sync(
            agent_name=agent_name,
            prompt=enhanced_prompt,
            provider=provider_doc.provide_name,
            model=model_doc.model_name,
            channel_id=f"canvas:{slug}",
            external_id=frappe.session.user,
            context=context,
            persist_conversation=True
        )
        
        return {
            "success": True,
            "response": result.get("response", "Task completed"),
            "run_id": result.get("run_id")
        }
    
    except Exception as e:
        frappe.log_error(f"Failed to send canvas message: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }