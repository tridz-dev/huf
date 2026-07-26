# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIProvider(Document):
	pass

@frappe.whitelist()
def get_provider_settings(provider_name):
    """
    Finds Single DocTypes that match the pattern '{Provider} % Settings'
    """
    if not provider_name:
        return []
    
    candidates = frappe.db.sql("""
        SELECT name FROM `tabDocType`
        WHERE issingle = 1 
        AND name LIKE %s
        AND name LIKE '%%Settings'
    """, (f"%{provider_name}%",), as_dict=True)
    
    return [c.name for c in candidates]