# huf/ai/orchestration/orchestrator.py

import frappe
from frappe.utils import now_datetime
from huf.ai.orchestration.planning import run_planning
from huf.ai.agent_integration import run_agent_sync


def create_orchestration(agent_name, user_prompt):
    """
    Called when enable_multi_run is true.
    Creates orchestration document and generates plan steps.
    """
    agent_doc = frappe.get_doc("Agent", agent_name)
    
    orch = frappe.new_doc("Agent Orchestration")
    orch.agent = agent_name
    orch.status = "Planned"
    orch.current_step = 0
    orch.save(ignore_permissions=True)
    frappe.db.commit()

    # Planning step: generate plan using the agent
    plan_output = run_planning(
        agent_name=agent_name,
        user_prompt=user_prompt,
        provider=agent_doc.provider,
        model=agent_doc.model
    )
    
    steps = parse_plan_steps(plan_output)

    if not steps:
        orch.status = "Failed"
        orch.error_log = "Planning failed: No steps generated"
        orch.save(ignore_permissions=True)
        frappe.db.commit()
        return orch.name

    for idx, step in enumerate(steps, start=1):
        orch.append("agent_orchestration_plan", {
            "step_index": idx,
            "instruction": step,
            "status": "pending"
        })

    orch.status = "Running"
    orch.save(ignore_permissions=True)
    frappe.db.commit()

    return orch.name


def parse_plan_steps(text):
    """Convert numbered list to python list."""
    if not text:
        return []
    
    lines = text.split("\n")
    steps = []
    for line in lines:
        line = line.strip()
        if line and line[0].isdigit():
            # Handle formats like "1. Step" or "1) Step"
            for sep in [".", ")", ":"]:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2 and parts[0].strip().isdigit():
                        step_text = parts[1].strip()
                        if step_text:
                            steps.append(step_text)
                        break
    return steps


def execute_next_step(orch):
    """
    Executes the next pending step in the orchestration plan.
    Returns: "ok", "completed", or "failed"
    """
    next_step = None

    for step in orch.agent_orchestration_plan:
        if step.status == "pending":
            next_step = step
            break

    if not next_step:
        orch.status = "Completed"
        orch.last_run_at = now_datetime()
        orch.save(ignore_permissions=True)
        frappe.db.commit()
        return "completed"

    # Get agent details for provider/model
    agent_doc = frappe.get_doc("Agent", orch.agent)

    next_step.status = "in_progress"
    orch.current_step = next_step.step_index
    orch.last_run_at = now_datetime()
    orch.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        # Build step execution prompt with scratchpad context
        step_prompt = f"""Execute the following step:

Step {next_step.step_index}: {next_step.instruction}

Previous context (scratchpad):
{orch.scratchpad or 'No previous context.'}

Complete this step and provide a clear response."""

        result = run_agent_sync(
            agent_name=orch.agent,
            prompt=step_prompt,
            provider=agent_doc.provider,
            model=agent_doc.model,
            channel_id="orchestration"
        )

        if result.get("success"):
            response = result.get("response", "")
            next_step.output_ref = response
            next_step.status = "done"
            
            # Update scratchpad with step output
            scratchpad_entry = f"\n\n[STEP {next_step.step_index} OUTPUT]\n{response}"
            orch.scratchpad = (orch.scratchpad or "") + scratchpad_entry
        else:
            next_step.status = "failed"
            error_msg = result.get("error", "Unknown error")
            orch.error_log = (orch.error_log or "") + f"\nStep {next_step.step_index} failed: {error_msg}"
            orch.status = "Failed"

    except Exception as e:
        next_step.status = "failed"
        orch.error_log = (orch.error_log or "") + f"\nStep {next_step.step_index} exception: {str(e)}"
        orch.status = "Failed"
        frappe.log_error(frappe.get_traceback(), "Orchestration Step Error")

    orch.save(ignore_permissions=True)
    frappe.db.commit()

    return "ok" if next_step.status == "done" else "failed"
