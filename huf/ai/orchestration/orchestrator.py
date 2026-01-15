# huf/ai/orchestration/orchestrator.py

import frappe
from frappe.utils import now_datetime
from huf.ai.orchestration.planning import run_planning
from huf.ai.agent_integration import run_agent_sync


def create_orchestration(agent_name, user_prompt, parent_run_id=None, conversation_id=None, override_plan=None):
    """
    Creates orchestration document.
    Requirement 3: Reuses existing 'default_plan' from Agent if available.
    """
    agent_doc = frappe.get_doc("Agent", agent_name)
    
    orch = frappe.new_doc("Agent Orchestration")
    orch.agent = agent_name
    orch.status = "Planned"
    orch.current_step = 0
    if parent_run_id:
        orch.parent_run = parent_run_id
    
    if conversation_id:
        orch.conversation = conversation_id

    if override_plan:
        for idx, step in enumerate(override_plan, start=1):
            orch.append("agent_orchestration_plan", {
                "step_index": idx,
                "instruction": step,
                "status": "pending"
            })

    elif agent_doc.default_plan:
        for step in agent_doc.default_plan:
            orch.append("agent_orchestration_plan", {
                "step_index": step.step_index,
                "instruction": step.instruction,
                "status": "pending"
            })
    else:
        plan_output = run_planning(
            agent_name=agent_name,
            user_prompt=user_prompt,
            provider=agent_doc.provider,
            model=agent_doc.model,
            conversation_id=conversation_id
        )
        steps = parse_plan_steps(plan_output)
        for idx, step in enumerate(steps, start=1):
            orch.append("agent_orchestration_plan", {
                "step_index": idx,
                "instruction": step,
                "status": "pending"
            })
            
    if not orch.agent_orchestration_plan:
        orch.status = "Failed"
        orch.error_log = "Planning failed: No steps available from Agent or Generator"
        orch.save()
        frappe.db.commit()
        return orch.name

    orch.status = "Running"
    orch.save()
    frappe.db.commit()

    return orch.name

@frappe.whitelist()
def recreate_orchestration_plan(orch_name):
    """
    Requirement 3 (Button): Recreates the plan based on current Agent instructions.
    """
    orch = frappe.get_doc("Agent Orchestration", orch_name)
    agent_doc = frappe.get_doc("Agent", orch.agent)
    
    plan_output = run_planning(orch.agent, agent_doc.instructions, agent_doc.provider, agent_doc.model)
    steps = parse_plan_steps(plan_output)
    
    if steps:
        orch.set("agent_orchestration_plan", [])
        for idx, step in enumerate(steps, start=1):
            orch.append("agent_orchestration_plan", {
                "step_index": idx,
                "instruction": step,
                "status": "pending"
            })
        orch.status = "Running"
        orch.current_step = 0
        orch.save()
        return True
    return False

def parse_plan_steps(text):
    """Convert numbered list to python list."""
    if not text:
        return []
    
    lines = text.split("\n")
    steps = []
    for line in lines:
        line = line.strip()
        if line and line[0].isdigit():
            for sep in [".", ")", ":"]:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2 and parts[0].strip().isdigit():
                        step_text = parts[1].strip()
                        if step_text:
                            steps.append(step_text)
                        break
    return steps

@frappe.whitelist()
def stop_orchestration(orch_name):
    """
    Stops the orchestration by setting status to 'Cancelled'.
    The scheduler will ignore 'Cancelled' orchestrations.
    """
    if not frappe.has_permission("Agent Orchestration", "write"):
        frappe.throw("Not allowed to stop orchestration")

    orch = frappe.get_doc("Agent Orchestration", orch_name)
    if orch.status in ["Completed", "Failed", "Cancelled"]:
        return 

    orch.status = "Cancelled"
    orch.save()
    orch.add_comment("Comment", "Orchestration manually stopped by user.")
    return True

def execute_next_step(orch=None, orch_name=None):
    if orch_name and not orch:
        orch = frappe.get_doc("Agent Orchestration", orch_name)
    
    if not orch:
        frappe.log_error("No orchestration provided to execute_next_step", "Orchestrator Error")
        return "failed"
        
    if orch.status == "Cancelled":
        return "cancelled"
    
    next_step = None

    for step in orch.agent_orchestration_plan:
        if step.status == "pending":
            next_step = step
            break

    if not next_step:
        orch.status = "Completed"
        orch.last_run_at = now_datetime()
        orch.save(ignore_permissions=True)
        if orch.parent_run:
            frappe.db.set_value("Agent Run", orch.parent_run, {
                "status": "Success",
                "end_time": now_datetime(),
                "response": f"Orchestration completed successfully. Scratchpad summary:\n{orch.scratchpad or 'No output.'}"
            })
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
            channel_id="orchestration",
            parent_run_id=orch.parent_run,
            orchestration_id=orch.name,
            conversation_id=orch.conversation
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
            if orch.parent_run:
                frappe.db.set_value("Agent Run", orch.parent_run, "status", "Failed")
            pass

    except Exception as e:
        next_step.status = "failed"
        orch.error_log = (orch.error_log or "") + f"\nStep {next_step.step_index} exception: {str(e)}"
        orch.status = "Failed"
        frappe.log_error(frappe.get_traceback(), "Orchestration Step Error")

    orch.save(ignore_permissions=True)
    frappe.db.commit()

    return "ok" if next_step.status == "done" else "failed"
