"""
Agent runner handler for Huf Agent tools.

Queues another agent execution via Frappe background jobs
instead of blocking the current tool call.
"""

import frappe
from frappe.utils.background_jobs import enqueue


def handle_run_agent(agent_name: str, prompt: str, **kwargs):
	"""
	Queue another agent execution instead of blocking.

	Args:
		agent_name: Name of the agent to run
		prompt: Prompt to send to the agent

	Returns:
		dict: Job queuing result with job_id
	"""
	try:
		if not frappe.db.exists("Agent", agent_name):
			return {"success": False, "error": f"Agent '{agent_name}' does not exist"}

		target_agent = frappe.get_doc("Agent", agent_name)

		job = enqueue(
			"huf.ai.agent_integration.run_agent_sync",
			queue="default",
			timeout=300,
			is_async=True,
			agent_name=agent_name,
			prompt=prompt,
			provider=target_agent.provider,
			model=target_agent.model,
		)

		return {"success": True, "queued": True, "job_id": job.id}
	except Exception as e:
		frappe.log_error(title="Run Agent Tool Error", message=str(e))
		return {"success": False, "error": str(e)}
