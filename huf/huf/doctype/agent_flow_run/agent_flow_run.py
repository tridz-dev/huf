import frappe
from frappe.model.document import Document


class AgentFlowRun(Document):
	pass


def on_doctype_update():
	# the wait sweeper filters on status and ranges over resume_at; add_index skips an existing index
	frappe.db.add_index("Agent Flow Run", ["status", "resume_at"], "idx_agent_flow_run_status_resume_at")
