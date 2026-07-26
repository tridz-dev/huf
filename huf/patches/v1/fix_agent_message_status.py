import frappe

def execute():
    # Fix 'Queues' typo to 'Queued'
    frappe.db.sql("""
        UPDATE `tabAgent Message`
        SET status = 'Queued'
        WHERE status = 'Queues'
    """)
