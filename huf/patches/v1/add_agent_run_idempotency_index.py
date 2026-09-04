import frappe


def execute():
    if frappe.db.has_column("Agent Run", "idempotency_key"):
        try:
            frappe.db.add_unique(
                "Agent Run", ["conversation", "idempotency_key"], constraint_name="uniq_agent_run_conv_idempotency_key"
            )
        except Exception as error:
            if "Duplicate key name" not in str(error):
                raise
