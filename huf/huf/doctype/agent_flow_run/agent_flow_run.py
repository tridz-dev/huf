import frappe
from frappe.model.document import Document


class AgentFlowRun(Document):
	def before_insert(self):
		from huf.ai.flow.app_scope.ownership import owner_app_of
		from huf.ai.flow.runs.write_guard import require_server_write

		require_server_write(self)
		self.owner_app = owner_app_of(self.flow_definition)

	def validate(self):
		from huf.ai.flow.runs.write_guard import require_server_write

		require_server_write(self)

	def before_rename(self, old, new, merge=False):
		from huf.ai.flow.runs.write_guard import refuse

		refuse(self)


def on_doctype_update():
	# the wait sweeper filters on status and ranges over resume_at; add_index skips an existing index
	frappe.db.add_index("Agent Flow Run", ["status", "resume_at"], "idx_agent_flow_run_status_resume_at")
	# app-scoped run summary (H-W7-12) filters on owner_app and status, newest first
	frappe.db.add_index(
		"Agent Flow Run", ["owner_app", "status", "modified"], "idx_agent_flow_run_owner_status_modified"
	)
