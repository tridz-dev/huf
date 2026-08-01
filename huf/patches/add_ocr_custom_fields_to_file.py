import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    custom_fields = {
        "File": [
            {
                "fieldname": "huf_ocr_section",
                "label": "OCR Extraction (HUF)",
                "fieldtype": "Section Break",
                "insert_after": "content_hash",
                "collapsible": 1,
            },
            {
                "fieldname": "huf_ocr_text",
                "label": "Extracted Text",
                "fieldtype": "Text Editor",
                "read_only": 1,
                "insert_after": "huf_ocr_section",
                "no_copy": 1,
            },
            {
                "fieldname": "huf_ocr_file_hash",
                "label": "Source File Hash",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "huf_ocr_text",
                "no_copy": 1,
                "hidden": 1,
            },
            {
                "fieldname": "huf_ocr_strategy",
                "label": "Extraction Strategy",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "huf_ocr_file_hash",
                "no_copy": 1,
            },
            {
                "fieldname": "huf_ocr_model",
                "label": "Extraction Model",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "huf_ocr_strategy",
                "no_copy": 1,
            },
            {
                "fieldname": "huf_ocr_at",
                "label": "Extracted At",
                "fieldtype": "Datetime",
                "read_only": 1,
                "insert_after": "huf_ocr_model",
                "no_copy": 1,
            }
        ]
    }

    create_custom_fields(custom_fields)
