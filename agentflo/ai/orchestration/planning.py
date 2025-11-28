# agentflo/agentflo/orchestration/planning.py

import frappe

PLANNING_PROMPT = """
Break the user's objective into a sequence of clear, atomic steps.
Return ONLY a numbered list. Example:
1. ...
2. ...
"""

def run_planning(agent_name, user_prompt):
    from agentflo.ai.agent_integration import run_agent_sync

    planning_message = f"{PLANNING_PROMPT}\n\nObjective: {user_prompt}"

    resp = run_agent_sync(
        agent_name=agent_name,
        prompt=planning_message,
        system_message="planning_step"
    )

    return resp
