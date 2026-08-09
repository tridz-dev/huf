import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date
from .automation_runtime_flag import automation_runtime_is_new
from .automation_runner import run_automation

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

	run_automation(
		automation_name,
		trigger_name=trigger_name,
		trigger_context={"type": "schedule", "fired_at": now.isoformat()},
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
