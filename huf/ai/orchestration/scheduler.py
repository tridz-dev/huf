# huf/ai/orchestration/scheduler.py

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds
from huf.ai.orchestration.orchestrator import execute_next_step

JOB_TIMEOUT_SECONDS = 900 # 15 minutes

def process_orchestrations():
    """
    Called every minute via scheduler to process active orchestrations.
    1. Checks for stuck jobs (timed out).
    2. Enqueues next steps for idle orchestrations.
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
            
            is_running = False
            for step in orch.agent_orchestration_plan:
                if step.status == "in_progress":
                    last_update = step.modified
                    if not last_update:
                        last_update = orch.modified
                        
                    if time_diff_in_seconds(now_datetime(), last_update) > JOB_TIMEOUT_SECONDS:
                        frappe.log_error(f"Orchestration {o.name} Step {step.step_index} timed out. Marking failed.", "Orchestration Scheduler")
                        step.status = "failed"
                        orch.error_log = (orch.error_log or "") + f"\nStep {step.step_index} timed out (stuck for > 15m)."
                        orch.status = "Failed"
                        orch.save(ignore_permissions=True)
                        frappe.db.commit()
                        is_running = False
                    else:
                        is_running = True
                    
                    break
            
            if is_running:
                continue

            frappe.enqueue(
                "huf.ai.orchestration.orchestrator.execute_next_step",
                queue="default",
                timeout=1200,
                orch=orch,
                orch_name=orch.name
            )

        except Exception as e:
            frappe.log_error(
                f"Error processing orchestration {o.name}: {str(e)}\n{frappe.get_traceback()}",
                "Orchestration Scheduler Error"
            )
