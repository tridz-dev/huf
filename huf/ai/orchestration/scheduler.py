# huf/ai/orchestration/scheduler.py

import frappe
from huf.ai.orchestration.orchestrator import execute_next_step


def process_orchestrations():
    """
    Called every minute via scheduler to process active orchestrations.
    Executes one step per orchestration per run.
    """
    if not frappe.db.exists("DocType", "Agent Orchestration"):
        return

    orchestrations = frappe.get_all(
        "Agent Orchestration",
        filters={"status": ["in", ["Planned", "Running"]]},
        fields=["name"]
    )

    for o in orchestrations:
        try:
            orch = frappe.get_doc("Agent Orchestration", o.name)
            result = execute_next_step(orch)
            
            if result == "failed":
                frappe.log_error(
                    f"Orchestration {o.name} step failed",
                    "Orchestration Scheduler"
                )
        except Exception as e:
            frappe.log_error(
                f"Error processing orchestration {o.name}: {str(e)}\n{frappe.get_traceback()}",
                "Orchestration Scheduler Error"
            )
