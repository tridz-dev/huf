import frappe
from frappe.utils import now_datetime, add_to_date
from .agent_integration import run_agent_sync

@frappe.whitelist()
def run_scheduled_agents():
    now = now_datetime().replace(microsecond=0)

    if not frappe.db.exists("DocType", "Agent Trigger"):
        return

    triggers = frappe.get_all(
        "Agent Trigger",
        filters={
            "trigger_type": "Schedule",
            "disabled": 0,
            "next_execution": ("<=", now),
        },
        fields=["name", "agent", "scheduled_interval", "interval_count", "next_execution", "last_execution"]
    )

    for t in triggers:
        try:
            if not t.get("next_execution") or t.get("next_execution") > now:
                continue

            agent_name = t.get("agent")
            agent = frappe.get_doc("Agent", agent_name)

            prompt = agent.instructions or f"Run scheduled agent: {agent_name}"
            run_agent_sync(agent_name, prompt, agent.provider, agent.model)

            doc = frappe.get_doc("Agent Trigger", t["name"])
            doc.last_execution = now

            interval = (doc.interval_count or 1)
            si = (doc.scheduled_interval or "").lower()
            doc.next_execution = add_to_date(
                now,
                hours=interval if si == "hourly" else 0,
                days=interval if si == "daily" else 0,
                weeks=interval if si == "weekly" else 0,
                months=interval if si == "monthly" else 0,
                years=interval if si == "yearly" else 0,
            )

            doc.save(ignore_permissions=True)
            frappe.db.commit()

        except Exception:
            frappe.log_error(frappe.get_traceback(), "Scheduled Agent Trigger Error")
