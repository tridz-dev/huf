# agentflo/ai/orchestration/orchestrator.py

import frappe
from agentflo.ai.orchestration.planning import run_planning
from agentflo.ai.agent_integration import run_agent_sync


def create_orchestration(agent, user_prompt):
    """Called when enable_multi_run is true."""
    orch = frappe.new_doc("Agent Orchestration")
    orch.agent = agent
    orch.status = "Planned"
    orch.current_step = 0
    orch.save(ignore_permissions=True)

    # planning step → create plan table
    plan_output = run_planning(agent, user_prompt)
    steps = parse_plan_steps(plan_output)

    for idx, step in enumerate(steps, start=1):
        orch.append("plan", {
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
    lines = text.split("\n")
    steps = []
    for l in lines:
        l = l.strip()
        if l.startswith(tuple("123456789")):
            parts = l.split(".", 1)
            if len(parts) == 2:
                steps.append(parts[1].strip())
    return steps


def execute_next_step(orch):
    """Executes the next pending step."""
    next_step = None

    for s in orch.plan:
        if s.status == "pending":
            next_step = s
            break

    if not next_step:
        orch.status = "Completed"
        orch.save()
        return "completed"

    next_step.status = "in_progress"
    orch.save()

    # call agent for step execution
    response = run_agent_sync(
        agent_name=orch.agent,
        prompt=f"Perform this step:\n{next_step.instruction}\n\nScratchpad:\n{orch.scratchpad or ''}",
        system_message="execution_step"
    )

    # update outputs
    next_step.output_ref = response
    next_step.status = "done"

    # optional: update scratchpad
    orch.scratchpad = (orch.scratchpad or "") + f"\n\n[STEP {next_step.step_index} OUTPUT]\n{response}"

    orch.save(ignore_permissions=True)
    frappe.db.commit()

    return "ok"
