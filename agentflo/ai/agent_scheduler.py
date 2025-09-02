import frappe
from frappe.utils import now_datetime, add_to_date
from .agent_integration import run_agent_sync

@frappe.whitelist()
def run_scheduled_agents():
    now = now_datetime().replace(microsecond=0)
    agents = frappe.get_all(
        "Agent",
        filters={
            "is_scheduled": 1,
            "disabled": 0,
            "next_execution": ("<=", now),
        },
        fields=["name", "scheduled_interval", "interval_count",
                "next_execution", "last_execution", "instructions"]
    )

    for agent in agents:
        try:
            if agent.next_execution and agent.next_execution <= now:
                prompt = agent.get("instructions")
                run_agent_sync(agent.name, prompt)
                doc = frappe.get_doc("Agent", agent.name)
                doc.last_execution = now
                doc.next_execution = add_to_date(
                    now,
                    hours=doc.interval_count if doc.scheduled_interval == "Hourly" else 0,
                    days=doc.interval_count if doc.scheduled_interval == "Daily" else 0,
                    weeks=doc.interval_count if doc.scheduled_interval == "Weekly" else 0,
                    months=doc.interval_count if doc.scheduled_interval == "Monthly" else 0,
                    years=doc.interval_count if doc.scheduled_interval == "Yearly" else 0,
                )
                doc.save(ignore_permissions=True)
                frappe.db.commit()

        except Exception as e:
            # Don’t update next_execution → will retry next tick
            frappe.log_error(
                f"Scheduled Agent {agent['name']} failed: {frappe.get_traceback()}",
                "Scheduled Agent Error"
            )
