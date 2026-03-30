"""
Migration: Add Vector Store fields to Knowledge Source DocType

Adds fields to support multi-vector-database backends:
- vector_store_profile: Link to Vector Store Profile
- backend_type: Select field for backend type override
"""

import frappe


def execute():
    """Execute the migration."""
    add_vector_store_profile_field()
    add_backend_type_field()
    

def add_vector_store_profile_field():
    """Add Vector Store Profile link field to Knowledge Source."""
    if not frappe.db.field_exists("Knowledge Source", "vector_store_profile"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Knowledge Source",
            "fieldname": "vector_store_profile",
            "fieldtype": "Link",
            "label": "Vector Store Profile",
            "options": "Vector Store Profile",
            "insert_after": "storage_mode",
            "description": "Vector store backend configuration for this knowledge source",
            "depends_on": "eval:doc.knowledge_type === 'sqlite_vec'"
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("Added 'vector_store_profile' field to Knowledge Source")


def add_backend_type_field():
    """Add Backend Type select field to Knowledge Source."""
    if not frappe.db.field_exists("Knowledge Source", "backend_type"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Knowledge Source",
            "fieldname": "backend_type",
            "fieldtype": "Select",
            "label": "Backend Type",
            "options": "\npgvector\nchroma\nweaviate\npinecone\nqdrant\nredis",
            "insert_after": "vector_store_profile",
            "description": "Override the default backend type for this knowledge source",
            "depends_on": "eval:doc.knowledge_type === 'sqlite_vec'"
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("Added 'backend_type' field to Knowledge Source")
