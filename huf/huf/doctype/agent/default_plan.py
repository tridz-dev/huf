"""Background generation of an Agent's default plan (multi-step runs).

Rules:
- A plan is generated only while ``default_plan`` is empty; an existing plan is never overwritten.
- Rows are written straight to the child table without saving the parent, so the Agent's
  ``modified`` does not move and an open editor's next section save is not rejected as stale.
- Progress is kept in the cache (``get_default_plan_status``) and announced with a realtime
  event so the editor can show "Generating plan..." and pull the rows in without a reload.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

PLAN_DOCTYPE = "Agent Orchestration Plan"
STATUS_TTL_SEC = 3600
REALTIME_EVENT = "huf_default_plan"
JOB_PATH = "huf.huf.doctype.agent.agent.generate_default_plan_job"


def _status_key(agent: str) -> str:
	return f"huf:default_plan_status:{agent}"


def set_status(agent: str, state: str, error: str | None = None) -> None:
	"""Record ``generating`` / ``done`` / ``failed`` and tell open editors."""
	payload = {"state": state, "error": error}
	try:
		frappe.cache().set_value(_status_key(agent), payload, expires_in_sec=STATUS_TTL_SEC)
		frappe.publish_realtime(
			REALTIME_EVENT,
			{"agent": agent, **payload},
			doctype="Agent",
			docname=agent,
			after_commit=True,
		)
	except Exception:  # noqa: BLE001
		frappe.log_error(title="Default plan status update failed", message=frappe.get_traceback())


def plan_is_empty(agent: str) -> bool:
	return not frappe.db.exists(
		PLAN_DOCTYPE, {"parent": agent, "parenttype": "Agent", "parentfield": "default_plan"}
	)


def enqueue_default_plan(agent: str) -> None:
	"""Queue generation for an agent whose plan is still empty."""
	if not plan_is_empty(agent):
		return
	set_status(agent, "generating")
	frappe.enqueue(JOB_PATH, agent=agent, enqueue_after_commit=True, queue="long")


def write_rows(agent: str, steps: list[str]) -> bool:
	"""Insert plan rows directly under the Agent. Returns False when a plan appeared meanwhile."""
	if not plan_is_empty(agent):
		return False
	now = now_datetime()
	user = frappe.session.user
	for idx, step in enumerate(steps, start=1):
		row = frappe.get_doc(
			{
				"doctype": PLAN_DOCTYPE,
				"parent": agent,
				"parenttype": "Agent",
				"parentfield": "default_plan",
				"idx": idx,
				"step_index": idx,
				"instruction": step,
				"status": "pending",
			}
		)
		row.name = frappe.generate_hash(length=10)
		row.owner = row.modified_by = user
		row.creation = row.modified = now
		row.db_insert()
	frappe.clear_document_cache("Agent", agent)
	return True


def build_planning_prompt(resolved: str) -> str:
	return f"""You are a planning assistant. Break down the user's objective into a sequence of clear, atomic steps that can be executed one at a time.

            Rules:
            - Each step should be self-contained and actionable
            - Steps should be in logical order
            - Return ONLY a numbered list, nothing else
            - Keep steps concise but clear

            Example format:
            1. First action to take
            2. Second action to take

            Now break down this objective:
            {resolved}"""


def generate_default_plan(agent_doc):
	"""Generate steps for ``agent_doc`` and store them if its plan is still empty.

	Returns ``(planning_run_id, steps)``, or ``None`` when nothing was generated.
	"""
	from huf.ai.agent.integration import run_agent_sync
	from huf.ai.orchestration.orchestrator import parse_plan_steps
	from huf.ai.prompt_resolver import resolve_prompt

	agent = agent_doc.name
	if not plan_is_empty(agent):
		set_status(agent, "done")
		return None
	resolved = resolve_prompt(agent_doc)
	if not resolved:
		set_status(agent, "failed", _("The agent has no instructions to plan from."))
		return None

	set_status(agent, "generating")
	try:
		result = run_agent_sync(
			agent_name=agent,
			prompt=build_planning_prompt(resolved),
			provider=agent_doc.provider,
			model=agent_doc.model,
			channel_id="orchestration_planning",
			now=True,
		)
		steps = parse_plan_steps(result.get("response", ""))
		if not steps:
			set_status(agent, "failed", _("The model did not return any steps."))
			return result.get("agent_run_id"), steps
		if write_rows(agent, steps):
			# Commit before announcing "done" so an editor that refetches right away sees the rows.
			frappe.db.commit()  # nosemgrep: justified background-job commit
		set_status(agent, "done")
		return result.get("agent_run_id"), steps
	except Exception as e:  # noqa: BLE001
		frappe.log_error(title="Agent Plan Error", message=f"Plan Generation Failed: {e}")
		set_status(agent, "failed", str(e) or _("Plan generation failed."))
		return None


@frappe.whitelist(methods=["GET", "POST"])
def get_default_plan_status(agent: str) -> dict:
	"""Return ``{"state": "idle|generating|done|failed", "error": str|None}`` for the editor."""
	frappe.get_doc("Agent", agent).check_permission("read")
	cached = frappe.cache().get_value(_status_key(agent))
	if isinstance(cached, dict) and cached.get("state"):
		return {"state": cached["state"], "error": cached.get("error")}
	return {"state": "idle", "error": None}
