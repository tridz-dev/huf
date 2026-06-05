import json
import frappe

def _export_doc(doc, key_field: str, skip_fields: list = None) -> dict:
    if not skip_fields:
        skip_fields = [
            "name", "creation", "modified", "modified_by", "owner", 
            "docstatus", "idx", "source_app", "source_file"
        ]
        
    data = {}
    for fieldname in doc.as_dict():
        if fieldname in skip_fields or fieldname.startswith("_"):
            continue
            
        value = getattr(doc, fieldname)
        if value is not None and value != "":
            # Handle child tables
            if isinstance(value, list):
                child_list = []
                for child in value:
                    child_dict = _export_doc(child, "name", skip_fields + ["parent", "parentfield", "parenttype"])
                    child_list.append(child_dict)
                data[fieldname] = child_list
            else:
                data[fieldname] = value
                
    return data

@frappe.whitelist()
def export_agent_to_seed(agent_name: str) -> dict:
    doc = frappe.get_doc("Agent", agent_name)
    return _export_doc(doc, "agent_name")

@frappe.whitelist()
def export_tool_to_seed(tool_name: str) -> dict:
    doc = frappe.get_doc("Agent Tool Function", tool_name)
    return _export_doc(doc, "tool_name")

@frappe.whitelist()
def export_prompt_to_seed(prompt_name: str) -> dict:
    doc = frappe.get_doc("Agent Prompt", prompt_name)
    return _export_doc(doc, "title")

@frappe.whitelist()
def export_knowledge_to_seed(source_name: str) -> dict:
    doc = frappe.get_doc("Knowledge Source", source_name)
    return _export_doc(doc, "source_name")

@frappe.whitelist()
def export_trigger_to_seed(trigger_name: str) -> dict:
    doc = frappe.get_doc("Agent Trigger", trigger_name)
    return _export_doc(doc, "trigger_name")
