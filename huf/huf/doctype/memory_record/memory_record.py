# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, now, now_datetime


SCOPE_TYPES_REQUIRING_KEY = {"Conversation", "User", "Role", "Agent", "Workspace", "Site", "Global"}


class MemoryRecord(Document):
    """Canonical scoped memory/data record."""

    def validate(self):
        self.set_defaults()
        self.validate_scope()
        self.validate_status()
        self.validate_projection_settings()

    def set_defaults(self):
        if not self.status:
            self.status = "Draft"
        if not self.source_type:
            self.source_type = "Manual"
        if not self.projection_status:
            self.projection_status = "Not Indexed"
        if not self.visibility:
            self.visibility = "Private"
        if not self.record_type:
            self.record_type = "Fact"
        if self.scope_type == "Global" and not self.scope_key:
            self.scope_key = "global"
        elif self.scope_type == "Site" and not self.scope_key:
            self.scope_key = frappe.local.site
        elif self.scope_type == "User" and not self.scope_key:
            self.scope_key = frappe.session.user
        elif self.scope_type == "Agent" and not self.scope_key and self.agent:
            self.scope_key = self.agent
        elif self.scope_type == "Conversation" and not self.scope_key and self.conversation:
            self.scope_key = self.conversation
        if self.ttl_days and not self.effective_until:
            self.effective_until = add_days(now_datetime(), int(self.ttl_days))

    def validate_scope(self):
        if self.scope_type in SCOPE_TYPES_REQUIRING_KEY and not self.scope_key:
            frappe.throw(_("Scope Key is required for scope type {0}").format(self.scope_type))
        if self.scope_type == "Conversation" and self.conversation and self.scope_key != self.conversation:
            frappe.throw(_("For Conversation scope, Scope Key must match Conversation"))
        if self.scope_type == "Agent" and self.agent and self.scope_key != self.agent:
            frappe.throw(_("For Agent scope, Scope Key must match Agent"))

    def validate_status(self):
        if self.status == "Active" and not self.summary_text:
            frappe.throw(_("Summary Text is required before activating a memory record"))

    def validate_projection_settings(self):
        if self.promote_to_knowledge and not self.knowledge_source:
            frappe.throw(_("Knowledge Source is required when Promote to Knowledge is enabled"))
        if not self.promote_to_knowledge and self.projection_status == "Queued":
            self.projection_status = "Not Indexed"

    def on_update(self):
        if self.promote_to_knowledge and self.knowledge_source and self.status == "Active":
            if self.has_value_changed("summary_text") or self.has_value_changed("data_json") or not self.knowledge_input:
                self.queue_knowledge_projection()

    @frappe.whitelist()
    def queue_knowledge_projection(self):
        self.db_set("projection_status", "Queued", update_modified=False)
        self.db_set("projection_error", None, update_modified=False)
        frappe.enqueue("huf.huf.doctype.memory_record.memory_record.project_memory_to_knowledge", queue="default", memory_record=self.name, job_id=f"project_memory_to_knowledge_{self.name}", deduplicate=True, enqueue_after_commit=True)
        return {"status": "queued", "memory_record": self.name}

    @frappe.whitelist()
    def remove_knowledge_projection(self):
        if self.knowledge_input and frappe.db.exists("Knowledge Input", self.knowledge_input):
            frappe.delete_doc("Knowledge Input", self.knowledge_input, ignore_permissions=False)
        self.db_set("knowledge_input", None, update_modified=False)
        self.db_set("projection_status", "Removed", update_modified=False)
        self.db_set("last_projected_at", now(), update_modified=False)
        self.db_set("projection_error", None, update_modified=False)
        return {"status": "removed", "memory_record": self.name}


def _memory_to_knowledge_text(doc: MemoryRecord) -> str:
    parts = [f"# {doc.title}", "", f"Type: {doc.record_type}", f"Scope: {doc.scope_type} / {doc.scope_key}"]
    if doc.agent:
        parts.append(f"Agent: {doc.agent}")
    if doc.tags:
        parts.append(f"Tags: {doc.tags}")
    parts.extend(["", doc.summary_text or ""])
    if doc.data_json:
        try:
            data = json.loads(doc.data_json) if isinstance(doc.data_json, str) else doc.data_json
            parts.extend(["\n## Structured Data\n", json.dumps(data, ensure_ascii=False, indent=2, default=str)])
        except Exception:
            parts.extend(["\n## Structured Data\n", str(doc.data_json)])
    return "\n".join(parts).strip()


@frappe.whitelist()
def project_memory_to_knowledge(memory_record: str):
    doc = frappe.get_doc("Memory Record", memory_record)
    if not frappe.has_permission("Memory Record", "read", doc.name):
        frappe.throw(_("Not permitted to read Memory Record {0}").format(doc.name))
    if doc.status != "Active":
        frappe.throw(_("Only Active memory records can be projected to knowledge"))
    if not doc.promote_to_knowledge or not doc.knowledge_source:
        frappe.throw(_("Memory Record is not configured for knowledge projection"))
    try:
        text = _memory_to_knowledge_text(doc)
        if doc.knowledge_input and frappe.db.exists("Knowledge Input", doc.knowledge_input):
            knowledge_input = frappe.get_doc("Knowledge Input", doc.knowledge_input)
            knowledge_input.text = text
            knowledge_input.status = "Pending"
            knowledge_input.error_message = None
            knowledge_input.save(ignore_permissions=False)
            knowledge_input.queue_processing()
        else:
            knowledge_input = frappe.get_doc({"doctype": "Knowledge Input", "knowledge_source": doc.knowledge_source, "input_type": "Text", "text": text})
            knowledge_input.insert(ignore_permissions=False)
            doc.db_set("knowledge_input", knowledge_input.name, update_modified=False)
        doc.db_set("projection_status", "Projected", update_modified=False)
        doc.db_set("last_projected_at", now(), update_modified=False)
        doc.db_set("projection_error", None, update_modified=False)
        return {"status": "projected", "memory_record": doc.name, "knowledge_input": knowledge_input.name, "knowledge_source": doc.knowledge_source}
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "Memory Knowledge Projection Error")
        doc.db_set("projection_status", "Error", update_modified=False)
        doc.db_set("projection_error", str(exc), update_modified=False)
        raise


@frappe.whitelist()
def queue_memory_knowledge_projection(memory_record: str):
    doc = frappe.get_doc("Memory Record", memory_record)
    return doc.queue_knowledge_projection()


@frappe.whitelist()
def remove_memory_knowledge_projection(memory_record: str):
    doc = frappe.get_doc("Memory Record", memory_record)
    return doc.remove_knowledge_projection()
