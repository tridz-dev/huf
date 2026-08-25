import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from .agent_integration import _run_async_safely, run_agent_sync
from .automation_runtime_flag import automation_runtime_is_new

_PROVIDER_BRAND_TO_BATCH_JOB_PROVIDER = {
	"openai": "OpenAI",
	"anthropic": "Anthropic",
	"google": "Gemini",
}


def _submit_batch_job_for_trigger(t, agent, prompt):
	"""Submit a single-request batch job for a due Schedule+Batch trigger.

	Builds a batch of exactly one request. A single-request batch job is still
	valid and still gets the provider's batch discount -- batching multiple
	scheduled runs into one provider batch is a future enhancement, out of
	scope here.

	The caller's existing per-trigger try/except in run_scheduled_agents()
	already guards this call, so this function does not need its own
	top-level try/except; only the provider submit_batch() call itself is
	wrapped, so a submission failure can be recorded on the Batch Job instead
	of aborting before next_execution is advanced.
	"""
	agent_name = t.get("agent")
	provider_brand = frappe.db.get_value("AI Provider", agent.provider, "provider_brand")
	batch_job_provider = _PROVIDER_BRAND_TO_BATCH_JOB_PROVIDER.get(provider_brand)

	batch_job = frappe.get_doc(
		{
			"doctype": "Batch Job",
			"agent": agent_name,
			"agent_trigger": t["name"],
			"provider": batch_job_provider,
			"status": "Pending",
			"request_count": 1,
		}
	)
	batch_job.insert(ignore_permissions=True)

	requests = [
		{"custom_id": batch_job.name, "messages": [{"role": "user", "content": prompt}], "model": agent.model}
	]

	if provider_brand == "google":
		from huf.ai.providers.batch.gemini_batch import _GEMINI_STATE_TO_BATCH_JOB_STATUS, submit_batch

		status_map = _GEMINI_STATE_TO_BATCH_JOB_STATUS
	elif provider_brand == "openai":
		from huf.ai.providers.batch.openai_batch import _OPENAI_STATUS_TO_BATCH_JOB_STATUS, submit_batch

		status_map = _OPENAI_STATUS_TO_BATCH_JOB_STATUS
	elif provider_brand == "anthropic":
		from huf.ai.providers.batch.anthropic_batch import _ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS, submit_batch

		status_map = _ANTHROPIC_STATUS_TO_BATCH_JOB_STATUS
	else:
		unsupported_msg = f"Unsupported provider brand for batch submission: {provider_brand}"
		frappe.log_error(unsupported_msg, "Batch Job Submit")
		batch_job.status = "Failed"
		batch_job.error_message = unsupported_msg
		batch_job.save(ignore_permissions=True)
		return

	try:
		result = _run_async_safely(submit_batch(agent, requests))
	except Exception as e:  # noqa: BLE001 -- boundary catch: record on Batch Job, never abort the scheduler loop
		frappe.log_error(frappe.get_traceback(), "Batch Job Submit")
		batch_job.status = "Failed"
		batch_job.error_message = str(e)
		batch_job.save(ignore_permissions=True)
		return

	batch_job.provider_batch_id = result.get("provider_batch_id")
	batch_job.status = status_map.get(result.get("status"), "Submitted")
	batch_job.submitted_at = now_datetime()
	batch_job.save(ignore_permissions=True)


@frappe.whitelist()
def run_scheduled_agents():
	if automation_runtime_is_new():
		return
	now = now_datetime().replace(microsecond=0)

	if frappe.session.user != "Administrator" and not frappe.has_permission("Agent Trigger", "write"):
		frappe.throw(
			_("Permission denied: You cannot run scheduled agents manually."), frappe.PermissionError
		)

	if not frappe.db.exists("DocType", "Agent Trigger"):
		return

	triggers = frappe.get_all(
		"Agent Trigger",
		filters={
			"trigger_type": "Schedule",
			"disabled": 0,
			"next_execution": ("<=", now),
		},
		fields=[
			"name",
			"agent",
			"scheduled_interval",
			"interval_count",
			"next_execution",
			"last_execution",
			"execution_mode",
		],
	)

	for t in triggers:
		try:
			if not t.get("next_execution") or t.get("next_execution") > now:
				continue

			agent_name = t.get("agent")
			agent = frappe.get_doc("Agent", agent_name)

			from huf.ai.prompt_resolver import resolve_prompt

			prompt = resolve_prompt(agent) or f"Run scheduled agent: {agent_name}"

			if t.get("execution_mode") == "Batch":
				_submit_batch_job_for_trigger(t, agent, prompt)
			else:
				run_agent_sync(agent_name, prompt, agent.provider, agent.model)

			doc = frappe.get_doc("Agent Trigger", t["name"])
			doc.last_execution = now

			interval = doc.interval_count or 1
			si = (doc.scheduled_interval or "").lower()
			doc.next_execution = add_to_date(
				now,
				hours=interval if si == "hourly" else 0,
				days=interval if si == "daily" else 0,
				weeks=interval if si == "weekly" else 0,
				months=interval if si == "monthly" else 0,
				years=interval if si == "yearly" else 0,
			)

			doc.save()
			frappe.db.commit()

		except Exception:
			frappe.log_error(frappe.get_traceback(), "Scheduled Agent Trigger Error")
