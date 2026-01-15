import frappe
def execute():
    tool_types = [
        "Create Doc",
        "Fetch Doc",
        "Update Doc",
        "Delete Doc",
        "Custom Function",
        "Client Side Function"
    ]

    for tool_type in tool_types:
        if not frappe.db.exists("Agent Tool Type", tool_type):
            doc = frappe.get_doc({
                "doctype": "Agent Tool Type",
                "name1": tool_type
            })
            doc.flags.ignore_validate = True
            doc.insert(ignore_permissions=True)
