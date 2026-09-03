import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date
from .agent_integration import run_agent_sync

@frappe.whitelist()
def run_scheduled_agents():
    now = now_datetime().replace(microsecond=0)

    if frappe.session.user != "Administrator" and not frappe.has_permission("Agent Trigger", "write"):
        frappe.throw(_("Permission denied: You cannot run scheduled agents manually."), frappe.PermissionError)

    if not frappe.db.exists("DocType", "Agent Trigger"):
        return

    triggers = frappe.get_all(
        "Agent Trigger",
        filters={
            "trigger_type": "Schedule",
            "disabled": 0,
            "next_execution": ("<=", now),
        },
        fields=["name", "target_type", "agent", "flow", "scheduled_interval", "interval_count", "next_execution", "last_execution"]
    )

    for t in triggers:
        try:
            if not t.get("next_execution") or t.get("next_execution") > now:
                continue

            target_type = t.get("target_type") or "Agent"

            if target_type == "Flow":
                _run_scheduled_flow(t)
            else:
                _run_scheduled_agent(t)

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

            doc.save()
            frappe.db.commit()

        except Exception:
            frappe.log_error(frappe.get_traceback(), "Scheduled Agent Trigger Error")


def _run_scheduled_agent(t):
    """Original behaviour: run the linked Agent synchronously."""
    agent_name = t.get("agent")
    agent = frappe.get_doc("Agent", agent_name)

    from huf.ai.prompt_resolver import resolve_prompt
    prompt = resolve_prompt(agent) or f"Run scheduled agent: {agent_name}"
    run_agent_sync(agent_name, prompt, agent.provider, agent.model)


def _run_scheduled_flow(t):
    """Start a Flow Run for a Flow-targeted Schedule trigger.

    Mirrors huf.ai.flow_api.execute_scheduled_flow, but is driven by an
    Agent Trigger row instead of a Scheduled Job Type, so the same
    Active-flow check and payload shape apply.
    """
    flow_id = t.get("flow")
    if not flow_id:
        frappe.log_error(f"Agent Trigger {t.get('name')} targets Flow but has no flow set", "Scheduled Flow Trigger Error")
        return

    if not frappe.db.exists("Flow Definition", flow_id):
        frappe.log_error(f"Scheduled flow '{flow_id}' not found (trigger {t.get('name')})", "Scheduled Flow Trigger Error")
        return

    defn_doc = frappe.get_doc("Flow Definition", flow_id)
    if defn_doc.status != "Active":
        frappe.log_error(
            f"Flow '{flow_id}' is not active (status: {defn_doc.status}); skipping trigger {t.get('name')}",
            "Scheduled Flow Trigger Error",
        )
        return

    from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow

    payload = {
        "_triggered_by": "schedule",
        "_timestamp": str(now_datetime()),
        "_agent_trigger": t.get("name"),
    }

    flow_run = create_flow_run(
        flow_id=flow_id,
        payload=payload,
        trigger_type="Schedule",
    )
    engine_run_flow(flow_run.name)
