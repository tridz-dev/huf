import frappe
from .connector import OdooConnector
from frappe.utils import now_datetime, add_minutes


def run_polling_sync():
    """
    Scheduled task to check for updates in Odoo.
    Finds all active Odoo connections and checks their registered triggers.
    """
    active_connections = frappe.get_all(
        "Odoo Connection", 
        filters={"is_active": 1, "connection_status": "Connected"},
        fields=["name", "last_sync_datetime"]
    )
    
    for conn in active_connections:
        frappe.enqueue(
            "huf.ai.odoo.polling.sync_connection",
            connection_name=conn.name,
            last_sync=conn.last_sync_datetime
        )


def sync_connection(connection_name: str, last_sync: str = None):
    """
    Polls Odoo for changes in models that have 'Odoo Event' triggers.
    """
    # 1. Find all models we need to poll for this connection
    triggers = frappe.get_all(
        "Agent Trigger",
        filters={
            "trigger_type": "Odoo Event",
            "disabled": 0,
            "odoo_connection": connection_name
        },
        fields=["reference_doctype"]
    )
    
    models_to_poll = list(set([t.reference_doctype for t in triggers]))
    if not models_to_poll:
        return

    connector = OdooConnector(connection_name)
    new_sync_time = now_datetime()
    
    # If no last_sync, only look for things in the last 5 minutes to avoid a flood
    if not last_sync:
        last_sync = add_minutes(new_sync_time, -5)

    for model in models_to_poll:
        try:
            # 2. Search for records modified since last_sync
            domain = [["write_date", ">", last_sync]]
            # Odoo search expects strings for datetimes
            records = connector.search_read(model, domain=domain, fields=["id"], limit=50)
            
            if records:
                # 3. Trigger agents via background job
                from .webhook import run_odoo_triggered_agents
                ids = [r["id"] for r in records]
                
                # Enqueue instead of direct call to avoid blocking the worker
                frappe.enqueue(
                    "huf.ai.odoo.webhook.run_odoo_triggered_agents",
                    connection=connection_name,
                    model=model,
                    ids=ids[:50],  # Cap to avoid overwhelming the queue
                    event="polling_update",
                    payload={"source": "polling"},
                    queue="long",
                )
        except Exception as e:
            frappe.log_error(f"Polling failed for {model} on {connection_name}: {str(e)}")

    # Update last_sync_datetime
    frappe.db.set_value("Odoo Connection", connection_name, "last_sync_datetime", new_sync_time)
    frappe.db.commit()
