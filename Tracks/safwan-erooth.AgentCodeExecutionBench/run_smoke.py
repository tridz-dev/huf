import json

import frappe


SITE = "huf-agentnav.localhost"


def main():
    frappe.init(site=SITE, sites_path="/workspace/development/16_agentnav/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    frappe.conf["huf_python_execution_enabled"] = True

    from huf.install import create_huf_roles
    from huf.ai.tools.code_execution import run_python

    create_huf_roles()
    frappe.db.commit()

    created = {
        "profiles": [],
        "agents": [],
        "todos": [],
        "calls": [],
        "approvals": [],
    }

    def cleanup():
        frappe.set_user("Administrator")
        for name in reversed(created["approvals"]):
            try:
                frappe.delete_doc(
                    "Agent Execution Approval", name, ignore_permissions=True, force=True
                )
            except Exception:
                pass
        for name in reversed(created["calls"]):
            try:
                frappe.delete_doc("Agent Tool Call", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        for name in reversed(created["agents"]):
            try:
                frappe.delete_doc("Agent", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        for name in reversed(created["profiles"]):
            try:
                frappe.delete_doc(
                    "Execution Profile", name, ignore_permissions=True, force=True
                )
            except Exception:
                pass
        for name in reversed(created["todos"]):
            try:
                frappe.delete_doc("ToDo", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.db.commit()

    def ensure_provider_model():
        provider = frappe.db.get_value("AI Provider", {}, "name")
        if not provider:
            provider_doc = frappe.get_doc(
                {
                    "doctype": "AI Provider",
                    "provider_name": f"Exec Smoke Provider {frappe.generate_hash(length=6)}",
                    "api_key": "test-key-not-used",
                    "provider_brand": "openai",
                }
            )
            provider_doc.insert(ignore_permissions=True)
            provider = provider_doc.name
        model = frappe.db.get_value("AI Model", {"provider": provider}, "name")
        if not model:
            model_doc = frappe.get_doc(
                {
                    "doctype": "AI Model",
                    "model_name": f"exec-smoke-model-{frappe.generate_hash(length=6)}",
                    "provider": provider,
                }
            )
            model_doc.insert(ignore_permissions=True)
            model = model_doc.name
        return provider, model

    provider, model = ensure_provider_model()

    def make_profile(name, approval_mode, filesystem_policy, permissions=None):
        doc = frappe.get_doc(
            {
                "doctype": "Execution Profile",
                "profile_name": name,
                "approval_mode": approval_mode,
                "filesystem_policy": filesystem_policy,
                "max_wall_time_s": 30,
                "max_cpu_seconds": 30,
                "max_memory_mb": 256,
                "max_output_bytes": 1048576,
                "permissions": permissions or [],
            }
        )
        doc.insert(ignore_permissions=True)
        created["profiles"].append(doc.name)
        return doc.name

    def make_agent(name, profile_name):
        doc = frappe.get_doc(
            {
                "doctype": "Agent",
                "agent_name": name,
                "provider": provider,
                "model": model,
                "instructions": "Smoke test agent for code execution",
                "allow_code_execution": 1,
                "execution_profile": profile_name,
            }
        )
        doc.insert(ignore_permissions=True)
        created["agents"].append(doc.name)
        return doc

    def fetch_call(call_id):
        row = frappe.db.get_value(
            "Agent Tool Call",
            {"call_id": call_id},
            [
                "name",
                "status",
                "exit_status",
                "error_message",
                "stdout",
                "stderr",
                "resource_usage",
            ],
            as_dict=True,
        )
        if not row:
            raise RuntimeError(f"missing Agent Tool Call for {call_id}")
        created["calls"].append(row.name)
        return row

    calc_profile = make_profile("Smoke Auto Calc", "Auto Approve", "None")
    calc_agent = make_agent("Smoke Calc Agent", calc_profile)

    data_profile = make_profile(
        "Smoke Auto Data",
        "Auto Approve",
        "None",
        permissions=[
            {"capability": "doc.create", "reference_doctype": "ToDo", "is_read_only": 0},
            {"capability": "doc.get_list", "reference_doctype": "ToDo", "is_read_only": 1},
            {"capability": "doc.read", "reference_doctype": "ToDo", "is_read_only": 1},
        ],
    )
    data_agent = make_agent("Smoke Data Agent", data_profile)

    ask_profile = make_profile("Smoke Ask Approval", "Ask Every Time", "None")
    ask_agent = make_agent("Smoke Ask Agent", ask_profile)

    block_profile = make_profile("Smoke Never Allow", "Never Allow", "None")
    block_agent = make_agent("Smoke Block Agent", block_profile)

    frappe.db.commit()

    code_calc = (
        "nums = [3, 5, 8, 13]\\n"
        "print('total=' + str(sum(nums)))\\n"
        "print('mean=' + str(round(sum(nums) / len(nums), 2)))\\n"
    )
    result_calc = run_python(code_calc, agent_doc=calc_agent, call_id="calc-smoke")
    call_calc = fetch_call("calc-smoke")

    code_data = (
        "created = []\\n"
        "for idx, label in enumerate(['alpha', 'beta', 'alpha', 'gamma']):\\n"
        "    created.append(doc.create('ToDo', {'description': f'exec-smoke-{label}-{idx}'}))\\n"
        "rows = doc.get_list('ToDo', filters={'description': ['like', 'exec-smoke-%']}, fields=['name', 'description'], limit=20)\\n"
        "print('rows=' + str(len(rows)))\\n"
        "try:\\n"
        "    import pandas as pd\\n"
        "    frame = pd.DataFrame(rows)\\n"
        "    print('pandas=True')\\n"
        "    print('shape=' + str(frame.shape))\\n"
        "    print('sum_names=' + str(frame['name'].str.len().sum()))\\n"
        "except Exception as exc:\\n"
        "    print('pandas=False')\\n"
        "    print('pandas_error=' + type(exc).__name__ + ':' + str(exc))\\n"
        "    counts = {}\\n"
        "    for row in rows:\\n"
        "        key = row['description'].split('-')[2]\\n"
        "        counts[key] = counts.get(key, 0) + 1\\n"
        "    print('fallback=' + str(sorted(counts.items())))\\n"
    )
    result_data = run_python(code_data, agent_doc=data_agent, call_id="data-smoke")
    call_data = fetch_call("data-smoke")

    created_todos = frappe.get_all(
        "ToDo", filters={"description": ["like", "exec-smoke-%"]}, pluck="name"
    )
    created["todos"].extend(created_todos)

    code_ask = "print('awaiting approval path')\\n"
    result_ask = run_python(code_ask, agent_doc=ask_agent, call_id="ask-smoke")
    call_ask = fetch_call("ask-smoke")
    approval_name = result_ask.get("approval")
    approval_doc = None
    if approval_name:
        approval_doc = frappe.get_doc("Agent Execution Approval", approval_name)
        created["approvals"].append(approval_doc.name)

    code_block = "print('should be blocked')\\n"
    block_error = None
    try:
        result_block = run_python(code_block, agent_doc=block_agent, call_id="block-smoke")
    except Exception as exc:
        block_error = f"{type(exc).__name__}: {exc}"
        result_block = None
    call_block = fetch_call("block-smoke")

    summary = {
        "site": SITE,
        "results": {
            "calc": {
                "tool_result": result_calc,
                "status": call_calc.status,
                "exit_status": call_calc.exit_status,
                "stdout": call_calc.stdout,
                "stderr": call_calc.stderr,
                "usage": call_calc.resource_usage,
            },
            "data": {
                "tool_result": result_data,
                "status": call_data.status,
                "exit_status": call_data.exit_status,
                "stdout": call_data.stdout,
                "stderr": call_data.stderr,
                "usage": call_data.resource_usage,
            },
            "ask": {
                "tool_result": result_ask,
                "status": call_ask.status,
                "exit_status": call_ask.exit_status,
                "approval": approval_name,
                "approval_status": approval_doc.status if approval_doc else None,
                "stdout": call_ask.stdout,
                "stderr": call_ask.stderr,
            },
            "block": {
                "tool_result": result_block,
                "error": block_error,
                "status": call_block.status,
                "exit_status": call_block.exit_status,
                "stdout": call_block.stdout,
                "stderr": call_block.stderr,
            },
        },
        "cleanup": created,
    }

    print(json.dumps(summary, indent=2, default=str))
    cleanup()
    frappe.destroy()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        frappe.destroy()
        raise
