"""Hub delegate tool: run a matching agent for the caller and return its answer.

The child always starts in a NEW conversation (unique ``external_id``); it never
touches the calling conversation, so no conversation lock is re-entered and the
child's reply is not written into the parent. The tool waits for the child's
Agent Run for a bounded time well below the gateway timeout. On timeout it
returns the queued status with a link to the child conversation, where the
result is delivered when the run finishes.

The tool handler is a coroutine so waiting uses ``asyncio.sleep`` and never
blocks the event loop. Each poll ends the read snapshot with ``safe_commit`` so
the child's committed progress is visible (reads inside one transaction are
stale under repeatable read).
"""

import asyncio
import time
import uuid
from urllib.parse import quote

import frappe
from frappe import _

from huf.ai.transaction import safe_commit

DELEGATE_CHANNEL = "hub-delegate"
# Well below the gateway timeout (typically 120s) so the Hub can still answer.
WAIT_CAP_SECONDS = 75
POLL_INTERVAL_SECONDS = 2
_TERMINAL = ("Success", "Failed")

_QUEUED_NOTE = (
	"The agent is still running. Tell the user it is still working and share the "
	"conversation link; the answer will be delivered there. Do not claim it finished."
)


def _conversation_link(conversation_id):
	return f"/huf/chat/{quote(conversation_id, safe='')}" if conversation_id else None


def _error(message, **extra):
	return {"success": False, "error": message, **extra}


def _check_delegation(target_agent_name, calling_agent):
	"""Reuse ``handle_run_agent``'s checks. Returns (agent_doc, None) or (None, error dict)."""
	from huf.ai.agent.integration import _is_user_allowed
	from huf.ai.run_budget import estimate_run_cost, get_current_budget

	if not target_agent_name or not frappe.db.exists("Agent", target_agent_name):
		return None, _error(f"Agent '{target_agent_name}' does not exist")
	target = frappe.get_doc("Agent", target_agent_name)
	if target.disabled:
		return None, _error(f"Agent '{target_agent_name}' is disabled")
	if not _is_user_allowed(target, frappe.session.user):
		return None, _error(
			f"Permission Denied: User '{frappe.session.user}' is not authorized to run agent '{target_agent_name}'."
		)
	if target_agent_name == calling_agent:
		return None, _error("Circular Dependency Error: An agent cannot invoke itself.")

	budget = get_current_budget()
	budget.check_depth()
	budget.check_spend(estimate_run_cost(target, model=target.model, provider=target.provider))
	return target, None


def _start_child(target, prompt, agent_run_id, calling_agent):
	"""Start the child in a new conversation. Returns (external_id, conversation_id, run_id)."""
	from huf.ai.agent.integration import run_agent_sync

	external_id = f"delegate-{uuid.uuid4().hex}"
	kwargs = {
		"agent_name": target.name,
		"prompt": prompt,
		"channel_id": DELEGATE_CHANNEL,
		"external_id": external_id,
		"parent_run_id": agent_run_id,
		"invoked_by_agent": calling_agent,
	}
	if target.run_immediately:
		# run_agent_sync would execute this agent inline; run it on a worker instead.
		safe_commit()
		frappe.enqueue(
			"huf.ai.agent.integration.run_agent_sync",
			queue="default",
			timeout=1500,
			is_async=True,
			enqueue_after_commit=True,
			**kwargs,
		)
		safe_commit()
		return external_id, None, None
	# Queue-first (``now`` is never set): persists the run and enqueues a worker drainer.
	res = run_agent_sync(**kwargs)
	return external_id, res.get("conversation_id"), res.get("agent_run_id")


def _locate_run(external_id, conversation_id, run_id):
	"""Find (conversation, run id, run row) from committed data; any may still be missing."""
	if not conversation_id:
		conversation_id = frappe.db.get_value(
			"Agent Conversation", {"external_id": external_id, "channel": DELEGATE_CHANNEL}, "name"
		)
	if conversation_id and not run_id:
		run_id = frappe.db.get_value("Agent Run", {"conversation": conversation_id}, "name")
	row = None
	if run_id:
		row = frappe.db.get_value("Agent Run", run_id, ["status", "response", "error_message"], as_dict=True)
	return conversation_id, run_id, row


async def delegate_to_agent(
	target_agent_name: str,
	prompt: str,
	agent_run_id: str | None = None,
	agent_name: str | None = None,
):
	"""Run ``target_agent_name`` as the calling user and return its answer (see module doc).

	``agent_run_id`` and ``agent_name`` are injected from the run context (the calling run and agent).
	"""
	try:
		target, err = _check_delegation(target_agent_name, agent_name)
		if err:
			return err
		external_id, conversation_id, run_id = _start_child(target, prompt, agent_run_id, agent_name)
	except (
		frappe.DoesNotExistError,
		frappe.PermissionError,
		frappe.ValidationError,
		ValueError,
		KeyError,
	) as e:
		return _error(str(e))

	deadline = time.monotonic() + WAIT_CAP_SECONDS
	row = None
	while True:
		safe_commit()  # end the read snapshot so the worker's commits become visible
		conversation_id, run_id, row = _locate_run(external_id, conversation_id, run_id)
		if (row and row.status in _TERMINAL) or time.monotonic() >= deadline:
			break
		await asyncio.sleep(POLL_INTERVAL_SECONDS)

	base = {
		"agent": target.name,
		"conversation_id": conversation_id,
		"conversation_link": _conversation_link(conversation_id),
	}
	if row and row.status == "Success":
		return {"success": True, "status": "Success", "result": row.response, **base}
	if row and row.status == "Failed":
		return {**_error(row.error_message or _("The agent run failed."), status="Failed"), **base}
	return {"success": True, "status": "Queued", "message": _QUEUED_NOTE, **base}
