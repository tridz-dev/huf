import frappe

def execute():
    """Clear all modalities from existing AI Model records."""
    # Update all AI Model records to have NULL modalities
    frappe.db.sql("UPDATE `tabAI Model` SET modalities = NULL")
    
    frappe.db.commit()
    print("✅ Successfully cleared modalities for all existing AI Models.")