import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from .automation_runner import _resolve_instruction, run_automation
from .automation_runtime_flag import automation_runtime_is_new

# Short-lived per-trigger lock so an overlapping scheduler tick (or a manual
# invocation racing a real tick) can't double-fire the same due trigger.
# Mirrors the lock pattern in huf/ai/agent_hooks.py's run_hooked_agents.
_LOCK_PREFIX = "huf:automation_scheduler:lock:"
_LOCK_TTL_SEC = 60


@frappe.whitelist()
def run_due_automations():
	"""Fire every due Schedule-type Automation Trigger.

	Registered in hooks.py's ``scheduler_events["all"]`` alongside (not
	replacing) the legacy ``huf.ai.agent_scheduler.run_scheduled_agents`` —
	each checks ``automation_runtime_is_new()`` and no-ops when the other
	runtime is active, so exactly one of the two ever actually executes.
	"""
	if not automation_runtime_is_new():
		return

	now = now_datetime().replace(microsecond=0)

	if not frappe.db.exists("DocType", "Automation Trigger"):
		return

	triggers = frappe.get_all(
		"Automation Trigger",
		filters={
			"trigger_type": "Schedule",
			"disabled": 0,
			"next_execution": ("<=", now),
		},
		fields=[
			"name",
			"automation",
			"scheduled_interval",
			"interval_count",
			"next_execution",
			"last_execution",
			"execution_mode",
		],
	)

	for t in triggers:
		try:
			_fire_due_trigger(t, now)
		except Exception:
			frappe.log_error(
				title=f"Automation Scheduler Error: {t.get('name')}",
				message=frappe.get_traceback(),
			)


def _fire_due_trigger(t, now):
	trigger_name = t["name"]

	# Re-check next_execution against a fresh read under the lock — the
	# batch query above may be stale by the time we get here.
	lock_key = f"{_LOCK_PREFIX}{trigger_name}"
	cache = frappe.cache()
	if cache.get_value(lock_key):
		return
	cache.set_value(lock_key, now.isoformat(), expires_in_sec=_LOCK_TTL_SEC)

	current_next = frappe.db.get_value("Automation Trigger", trigger_name, "next_execution")
	if not current_next or current_next > now:
		return

	# Claim immediately by advancing next_execution BEFORE executing, so a
	# second overlapping tick (or a slow run) can't re-select this trigger
	# while the first run is still in flight.
	interval = t.get("interval_count") or 1
	si = (t.get("scheduled_interval") or "").lower()
	provisional_next = add_to_date(
		now,
		hours=interval if si == "hourly" else 0,
		days=interval if si == "daily" else 0,
		weeks=interval if si == "weekly" else 0,
		months=interval if si == "monthly" else 0,
		years=interval if si == "yearly" else 0,
	)
	frappe.db.set_value(
		"Automation Trigger",
		trigger_name,
		{"next_execution": provisional_next},
		update_modified=False,
	)
	frappe.db.commit()

	automation_name = t.get("automation")
	if not automation_name:
		return

	trigger_context = {"type": "schedule", "fired_at": now.isoformat()}

	if t.get("execution_mode") == "Batch":
		automation_doc = frappe.get_doc("Automation", automation_name)
		prompt = _resolve_instruction(automation_doc, trigger_context)
		_submit_batch_job_for_automation_trigger(t, automation_doc, prompt)
	else:
		run_automation(
			automation_name,
			trigger_name=trigger_name,
			trigger_context=trigger_context,
			now=True,
		)

	# run_automation()'s own bookkeeping (_update_trigger_bookkeeping) only
	# touches last_execution/status, not next_execution — set last_execution
	# here explicitly for symmetry with the legacy scheduler's behavior.
	frappe.db.set_value(
		"Automation Trigger",
		trigger_name,
		{"last_execution": now},
		update_modified=False,
	)
	frappe.db.commit()


def _submit_batch_job_for_automation_trigger(t, automation_doc, prompt):
	"""Submit a single-request batch job for a due Schedule+Batch Automation Trigger.

	Mirrors ``huf.ai.agent_scheduler._submit_batch_job_for_trigger`` (the legacy
	Agent Trigger equivalent), but resolves its Agent via ``automation_doc.agent``
	instead of a trigger-carried agent name, and links the created Batch Job back
	via ``automation_trigger`` rather than ``agent_trigger``.

	Builds a batch of exactly one request — batching multiple due Automation
	Trigger fires into one provider batch is a future enhancement, out of scope
	here. The caller's existing per-trigger try/except in run_due_automations()
	already guards this call, so only the provider submit_batch() call itself is
	wrapped, so a submission failure can be recorded on the Batch Job instead of
	aborting before next_execution is advanced.
	"""
	from huf.ai.agent_scheduler import _PROVIDER_BRAND_TO_BATCH_JOB_PROVIDER

	agent = frappe.get_doc("Agent", automation_doc.agent)
	provider_brand = frappe.db.get_value("AI Provider", agent.provider, "provider_brand")
	batch_job_provider = _PROVIDER_BRAND_TO_BATCH_JOB_PROVIDER.get(provider_brand)

	batch_job = frappe.get_doc(
		{
			"doctype": "Batch Job",
			"agent": agent.name,
			"automation_trigger": t["name"],
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
		frappe.log_error(title="Batch Job Submit", message=unsupported_msg)
		batch_job.status = "Failed"
		batch_job.error_message = unsupported_msg
		batch_job.save(ignore_permissions=True)
		return

	from .agent_integration import _run_async_safely

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
