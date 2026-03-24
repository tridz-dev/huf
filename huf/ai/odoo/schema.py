import frappe
import json
from .connector import OdooConnector
from frappe.utils import now_datetime

@frappe.whitelist()
def discover_schema(connection_name: str):
    """Entry point for background schema discovery."""
    frappe.enqueue(
        "huf.ai.odoo.schema.run_discovery",
        connection_name=connection_name,
        now=frappe.flags.in_test
    )
    return {"status": "Queued"}


def run_discovery(connection_name: str):
    """
    Introspect all models in Odoo and cache their field metadata.
    This provides the LLM with the context it needs to build queries.
    """
    try:
        connector = OdooConnector(connection_name)
        
        # 1. Get all models
        models = connector.get_models()
        
        for idx, model_info in enumerate(models):
            model_name = model_info["model"]
            model_label = model_info["name"]
            
            try:
                # 2. Get fields for this model
                fields = connector.fields_get(model_name)
            except Exception:
                # Some models (abstract, transient) may not support fields_get
                frappe.log_error(
                    f"Schema discovery skipped for {model_name}",
                    "Odoo Schema Discovery"
                )
                continue
            
            # 3. Cache the results
            cache_name = f"{connection_name}-{model_name}"
            if frappe.db.exists("Odoo Schema Cache", cache_name):
                doc = frappe.get_doc("Odoo Schema Cache", cache_name)
            else:
                doc = frappe.new_doc("Odoo Schema Cache")
                doc.name = cache_name
            
            doc.connection = connection_name
            doc.model_name = model_name
            doc.model_label = model_label
            doc.fields_json = json.dumps(fields)
            doc.last_synced = now_datetime()
            doc.save(ignore_permissions=True)
            
            # Commit every 10 models to avoid long-running transaction issues
            if (idx + 1) % 10 == 0:
                frappe.db.commit()

        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Odoo Schema Discovery Failed: {connection_name}")
        raise e
