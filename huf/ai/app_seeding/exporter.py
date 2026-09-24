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

@frappe.whitelist()
def export_decision_policy_to_seed(policy_name: str) -> dict:
    """Export a Decision Policy's editable definition for portability.

    Exports the policy definition only (definition_json, schema_version, purpose,
    default_model, description, enabled, allow_api_access, max_candidates) -- never
    the source site's Decision Policy Version history or fingerprints
    (`current_version`, `fingerprint`), which are site-computed and immutable.
    The import side (`upsert_decision_policy`) re-publishes the imported definition
    locally via `Decision Policy.publish_version()`, so the target site always
    produces its own current_version and fingerprint rather than inheriting the
    source site's. Decision Deployments and AI Provider keys are never exported;
    they are site-specific and are not part of the policy document.
    """
    doc = frappe.get_doc("Decision Policy", policy_name)
    skip_fields = [
        "name", "creation", "modified", "modified_by", "owner",
        "docstatus", "idx", "source_app", "source_file",
        "current_version", "fingerprint",
    ]
    return _export_doc(doc, "policy_name", skip_fields)
