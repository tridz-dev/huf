"""
Canvas Editor API
Handles agent communication and canvas operations
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_canvas_metadata(slug):
    """Get canvas metadata including agent info"""
    try:
        canvas = frappe.get_doc("Canvas", {"slug": slug})
        
        agent_info = None
        if canvas.agent:
            agent = frappe.get_doc("Agent", canvas.agent)
            agent_info = {
                "name": agent.agent_name,
                "description": agent.description,
                "instructions": agent.instructions
            }
        
        return {
            "success": True,
            "canvas": {
                "name": canvas.name,
                "title": canvas.title,
                "slug": canvas.slug,
                "agent": canvas.agent,
                "description": canvas.description,
                "allow_editing": canvas.allow_editing,
                "mode": canvas.mode
            },
            "agent": agent_info
        }
    
    except Exception as e:
        frappe.log_error(f"Failed to get canvas metadata: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def send_canvas_message(slug, message):
    """Send message to canvas agent"""
    try:
        # Get canvas
        canvas = frappe.get_doc("Canvas", {"slug": slug})
        
        if not canvas.allow_editing:
            frappe.throw(_("Editing not allowed for this canvas"))
        
        if not canvas.agent:
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
You are editing a Canvas artifact with slug: {slug}

{agents_md_content}

User request: {message}

Remember to:
1. Read existing files first if needed
2. Make changes carefully
3. Use validate_canvas() before major changes
4. Write all changed files in one call if possible
"""
        
        # Call agent
        result = run_agent_sync(
            agent_name=canvas.agent,
            prompt=enhanced_prompt,
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