import frappe
from frappe.utils.password import set_encrypted_password

PATCH_TITLE = "Migrate agent secrets from Data to Password fields"

# (doctype, fieldname, is_child_table)
_FIELDS = (
    ("MCP Server Header", "header_value", True),
    ("Agent Tool HTTP Header", "value", True),
    ("Automation Trigger", "webhook_key", False),
    ("Agent Trigger", "webhook_key", False),
)


def execute():
    """Re-encrypt four secret fields that were converted from Data to
    Password in this release. Idempotent: rows whose value already looks
    like a dummy password (all '*') are skipped, so re-running the patch
    (e.g. after a partial failure) is a no-op for already-migrated rows.
    """
    for doctype, fieldname, is_child in _FIELDS:
        if not frappe.db.table_exists(doctype):
            continue
        rows = frappe.get_all(doctype, fields=["name", fieldname], filters={fieldname: ["!=", ""]})
        for row in rows:
            plaintext = row.get(fieldname)
            if not plaintext:
                continue
            if set(plaintext) <= {"*"}:
                # Already a dummy password — either already migrated, or a
                # stray dummy value with nothing behind it. Either way there
                # is no plaintext left to encrypt; skip.
                continue

            set_encrypted_password(doctype, row.name, plaintext, fieldname)
            # Mirror what BaseDocument._save_passwords leaves behind on a
            # normal save, so the column is never empty/falsy (an empty
            # value is what triggers remove_encrypted_password on the next
            # .save() of this row — see base_document.py:1141-1142).
            frappe.db.set_value(doctype, row.name, fieldname, "*" * len(plaintext), update_modified=False)

    frappe.db.commit()
