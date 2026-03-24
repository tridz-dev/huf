import frappe
import json
from .connector import OdooConnector


@frappe.whitelist(allow_guest=True)
def receive_webhook():
    """
    Inbound webhook receiver for Odoo events.
    Expected URL: /api/method/huf.ai.odoo.webhook.receive_webhook?key=SECRET_KEY
    Expected Payload: { "model": "sale.order", "ids": [1], "event": "on_create" }
    """
    key = frappe.request.args.get("key")
    connection_name = frappe.request.args.get("connection")

    if not connection_name or not key:
        frappe.throw("Missing connection or key", frappe.PermissionError)

    # Verify key using get_password (not a plain DB lookup)
    conn_doc = frappe.get_doc("Odoo Connection", connection_name)
    stored_key = conn_doc.get_password("webhook_key", raise_exception=False)
    if not stored_key or stored_key != key:
        frappe.throw("Invalid webhook key", frappe.PermissionError)

    connection = connection_name

    # 2. Extract data (Odoo sends JSON by default if using base.automation 'Execute Code')
    try:
        data = frappe.request.get_json()
    except Exception:
        data = frappe.request.form.to_dict()

    if not data:
        return {"status": "Ignored", "reason": "No data received"}

    model = data.get("model")
    ids = data.get("ids", [])
    event = data.get("event", "on_update")

    if not model or not ids:
        return {"status": "Ignored", "reason": "Missing model or ids"}

    # 3. Trigger Agents
    frappe.enqueue(
        "huf.ai.odoo.webhook.run_odoo_triggered_agents",
        connection=connection,
        model=model,
        ids=ids,
        event=event,
        payload=data,
        now=frappe.flags.in_test
    )

    return {"status": "Accepted", "connection": connection}


def run_odoo_triggered_agents(connection, model, ids, event, payload):
    """
    Matches incoming Odoo events to Agent Triggers and executes them.
    """
    # 1. Find matching triggers
    triggers = frappe.get_all(
        "Agent Trigger",
        filters={
            "trigger_type": "Odoo Event",
            "disabled": 0,
            "odoo_connection": connection,
            "reference_doctype": model  # We reuse reference_doctype to store Odoo model name
        },
        fields=["name", "agent", "condition", "prompt_field"]
    )

    if not triggers:
        return

    # 2. For each triggered ID, run the agents
    # (Note: Usually Odoo webhooks are for a single record, but we handle multiple if sent)
    connector = OdooConnector(connection)
    
    for record_id in ids:
        # Fetch the record from Odoo to provide context
        # We don't fetch everything, just enough for basic context or as requested by Agent
        record_data = connector.execute(model, "read", [record_id])[0]
        
        for trigger in triggers:
            # Check condition if provided
            if trigger.condition:
                try:
                    from frappe.utils.safe_exec import get_safe_globals, safe_eval
                    if not safe_eval(trigger.condition, get_safe_globals(), {"doc": record_data}):
                        continue
                except Exception as e:
                    frappe.log_error(f"Odoo Trigger Condition Error: {str(e)}", trigger.name)
                    continue

            # Run Agent
            from huf.ai.agent_integration import run_agent_sync
            from huf.ai.prompt_resolver import resolve_prompt
            
            agent_doc = frappe.get_doc("Agent", trigger.agent)
            instructions = resolve_prompt(agent_doc)
            
            prompt = f"""
            You are an automation agent triggered by an Odoo event.
            
            Event: {event}
            Model: {model}
            Instance: {connection}
            
            Odoo Record Data (JSON):
            ```json
            {json.dumps(record_data, indent=2, default=str)}
            ```
            
            Use the available Odoo tools and these identifiers:
            connection = "{connection}"
            model = "{model}"
            id = {record_id}
            """
            
            if trigger.prompt_field and record_data.get(trigger.prompt_field):
                prompt += f"\n\nUSER REQUEST FROM ODOO FIELD '{trigger.prompt_field}':\n{record_data[trigger.prompt_field]}"
            else:
                prompt += f"\n\nInstructions:\n{instructions}"

            # Run the agent
            run_agent_sync(
                trigger.agent,
                prompt,
                agent_doc.provider,
                agent_doc.model,
                channel_id="odoo_event",
                external_id=f"odoo:{connection}:{model}:{record_id}"
            )
