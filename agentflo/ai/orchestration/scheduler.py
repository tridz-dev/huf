# agentflo/ai/orchestration/scheduler.py

import frappe
from agentflo.ai.orchestration.orchestrator import execute_next_step

def process_orchestrations():
    """Called every minute via scheduler."""
    orchestrations = frappe.get_all(
        "Agent Orchestration",
        filters={"status": ["in", ["Planned", "Running"]]},
        fields=["name"]
    )

    for o in orchestrations:
        orch = frappe.get_doc("Agent Orchestration", o.name)
        execute_next_step(orch)
