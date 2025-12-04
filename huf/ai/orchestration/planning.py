# huf/ai/orchestration/planning.py

import frappe

PLANNING_PROMPT = """You are a planning assistant. Break down the user's objective into a sequence of clear, atomic steps that can be executed one at a time.

Rules:
- Each step should be self-contained and actionable
- Steps should be in logical order
- Return ONLY a numbered list, nothing else
- Keep steps concise but clear

Example format:
1. First action to take
2. Second action to take
3. Third action to take

Now break down this objective:"""


def run_planning(agent_name, user_prompt, provider, model, conversation_id=None):
    """
    Runs the planning phase to break down user objective into steps.
    
    Args:
        agent_name: Name of the agent to use for planning
        user_prompt: The user's objective to break down
        provider: AI provider name
        model: AI model name
    
    Returns:
        str: The plan as a numbered list, or empty string on failure
    """
    from huf.ai.agent_integration import run_agent_sync

    planning_message = f"{PLANNING_PROMPT}\n\n{user_prompt}"

    try:
        result = run_agent_sync(
            agent_name=agent_name,
            prompt=planning_message,
            provider=provider,
            model=model,
            channel_id="orchestration_planning",
            conversation_id=conversation_id
        )

        if result.get("success"):
            return result.get("response", "")
        else:
            frappe.log_error(
                f"Planning failed for agent {agent_name}: {result.get('error')}",
                "Orchestration Planning Error"
            )
            return ""

    except Exception as e:
        frappe.log_error(
            f"Planning exception for agent {agent_name}: {str(e)}",
            "Orchestration Planning Error"
        )
        return ""
