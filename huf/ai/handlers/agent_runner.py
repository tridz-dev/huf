import frappe
from frappe.utils.background_jobs import enqueue

logger = frappe.logger("huf")


def handle_run_agent(target_agent_name: str, prompt: str, **kwargs):
    """
    Queue another agent execution instead of blocking.
    """
    try:
        if not frappe.db.exists("Agent", target_agent_name):
            return {"success": False, "error": f"Agent '{target_agent_name}' does not exist"}

        target_agent = frappe.get_doc("Agent", target_agent_name)

        from huf.ai.agent_integration import _is_user_allowed
        if not _is_user_allowed(target_agent, frappe.session.user):
            return {
                "success": False,
                "error": f"Permission Denied: User '{frappe.session.user}' is not authorized to run the sub-agent '{target_agent_name}'."
            }

        conversation_id = kwargs.get("conversation_id")
        agent_run_id = kwargs.get("agent_run_id")
        agent_name_self = kwargs.get("agent_name")

        if target_agent_name == agent_name_self:
            return {
                "success": False,
                "error": f"Circular Dependency Error: An agent cannot invoke itself as a sub-agent."
            }

        job = enqueue(
            "huf.ai.agent_integration.run_agent_sync",
            queue="default",
            timeout=1500,
            is_async=True,
            agent_name=target_agent_name,
            prompt=prompt,
            provider=target_agent.provider,
            model=target_agent.model,
            parent_conversation_id=conversation_id,
            invoked_by_agent=agent_name_self,
        )

        return {
            "status": "Queued",
            "message": "The task is currently being processed in the background. IMPORTANT: DO NOT tell the user that the task is completed or successful yet. Inform the user that you are working on it and will provide an update shortly. Do not mention the terms 'sub-agent' or 'background queue' explicitly, keep it natural (e.g., 'I am processing this for you now...').",
            "job_id": job.id
        }
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_run_agent failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}
