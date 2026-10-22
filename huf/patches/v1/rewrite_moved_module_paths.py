"""Rewrite stored dotted paths of modules that moved into feature packages.

Several huf/ai modules moved into packages (flow_api -> flow/api, tool_registry ->
tools/registry, ...). Rows that store a dotted path to them would otherwise break:
user-created Agent Tool Function rows (function_path), HUF App.permission_method and
Scheduled Job Type.method (the last is also re-synced from hooks.py on migrate; it is
rewritten here so a stale duplicate cannot linger). Only exact module-prefix matches are
rewritten, so the patch is idempotent and leaves unrelated values untouched.
"""

import frappe

# old dotted prefix (module + trailing dot) -> new dotted prefix
MAPPING = {
	"huf.ai.agent_access.": "huf.ai.agent.access.",
	"huf.ai.agent_chat.": "huf.ai.agent.chat.",
	"huf.ai.agent_config_api.": "huf.ai.agent.config_api.",
	"huf.ai.agent_conversation_analytics_api.": "huf.ai.agent.conversation_analytics_api.",
	"huf.ai.agent_hooks.": "huf.ai.agent.hooks.",
	"huf.ai.agent_integration.": "huf.ai.agent.integration.",
	"huf.ai.agent_run_analytics.": "huf.ai.agent.run_analytics.",
	"huf.ai.agent_run_analytics_api.": "huf.ai.agent.run_analytics_api.",
	"huf.ai.agent_run_context_api.": "huf.ai.agent.run_context_api.",
	"huf.ai.agent_scheduler.": "huf.ai.agent.scheduler.",
	"huf.ai.agent_stream_renderer.": "huf.ai.agent.stream_renderer.",
	"huf.ai.automation_api.": "huf.ai.automation.api.",
	"huf.ai.automation_app_event.": "huf.ai.automation.app_event.",
	"huf.ai.automation_hooks.": "huf.ai.automation.hooks.",
	"huf.ai.automation_runner.": "huf.ai.automation.runner.",
	"huf.ai.automation_runtime_flag.": "huf.ai.automation.runtime_flag.",
	"huf.ai.automation_scheduler.": "huf.ai.automation.scheduler.",
	"huf.ai.automation_service.": "huf.ai.automation.service.",
	"huf.ai.automation_webhook.": "huf.ai.automation.webhook.",
	"huf.ai.desktop_executor.": "huf.ai.desktop.executor.",
	"huf.ai.desktop_mcp.": "huf.ai.desktop.mcp.",
	"huf.ai.desktop_policy.": "huf.ai.desktop.policy.",
	"huf.ai.desktop_sessions.": "huf.ai.desktop.sessions.",
	"huf.ai.flow_api.": "huf.ai.flow.api.",
	"huf.ai.flow_create_doc.": "huf.ai.flow.create_doc.",
	"huf.ai.flow_engine.": "huf.ai.flow.engine.",
	"huf.ai.flow_eval.": "huf.ai.flow.eval.",
	"huf.ai.flow_orchestrator.": "huf.ai.flow.orchestrator.",
	"huf.ai.flow_state.": "huf.ai.flow.state.",
	"huf.ai.flow_tool_executor.": "huf.ai.flow.tool_executor.",
	"huf.ai.flow_tools.": "huf.ai.flow.tools.",
	"huf.ai.procedure_approval_api.": "huf.ai.procedure.approval_api.",
	"huf.ai.procedure_conversion.": "huf.ai.procedure.conversion.",
	"huf.ai.procedure_lock.": "huf.ai.procedure.lock.",
	"huf.ai.procedure_proposal.": "huf.ai.procedure.proposal.",
	"huf.ai.procedure_validation_api.": "huf.ai.procedure.validation_api.",
	"huf.ai.procedure_versioning.": "huf.ai.procedure.versioning.",
	"huf.ai.tool_doctype_guard.": "huf.ai.tools.doctype_guard.",
	"huf.ai.tool_functions.": "huf.ai.tools.functions.",
	"huf.ai.tool_invocation.": "huf.ai.tools.invocation.",
	"huf.ai.tool_registry.": "huf.ai.tools.registry.",
	"huf.ai.tool_serializer.": "huf.ai.tools.serializer.",
	"huf.ai.tool_types.": "huf.ai.tools.types.",
	"huf.ai.whatsapp_account_events.": "huf.ai.whatsapp.account_events.",
	"huf.ai.whatsapp_health.": "huf.ai.whatsapp.health.",
	"huf.ai.whatsapp_management.": "huf.ai.whatsapp.management.",
	"huf.ai.whatsapp_outbound_policy.": "huf.ai.whatsapp.outbound_policy.",
	"huf.ai.whatsapp_send_file.": "huf.ai.whatsapp.send_file.",
	"huf.ai.whatsapp_send_keys.": "huf.ai.whatsapp.send_keys.",
	"huf.ai.whatsapp_send_scope.": "huf.ai.whatsapp.send_scope.",
	"huf.ai.whatsapp_token_check.": "huf.ai.whatsapp.token_check.",
	"huf.ai.whatsapp_voice_reply.": "huf.ai.whatsapp.voice_reply.",
}

# (doctype, fieldname) pairs that hold a dotted Python path
TARGETS = (
	("Agent Tool Function", "function_path"),
	("HUF App", "permission_method"),
	("Scheduled Job Type", "method"),
)


def rewrite_path(value):
	"""Return value with a moved module prefix rewritten, or value unchanged."""
	if not value:
		return value
	for old, new in MAPPING.items():
		if value.startswith(old):
			return new + value[len(old) :]
	return value


def execute():
	for doctype, fieldname in TARGETS:
		if not frappe.db.exists("DocType", doctype):
			continue
		rows = frappe.get_all(doctype, filters={fieldname: ["like", "huf.ai.%"]}, fields=["name", fieldname])
		for row in rows:
			current = row.get(fieldname)
			updated = rewrite_path(current)
			if updated == current:
				continue
			if doctype == "Scheduled Job Type" and frappe.db.exists(doctype, {fieldname: updated}):
				# hooks.py sync already created the row for the new path: drop the stale duplicate.
				frappe.delete_doc(doctype, row["name"], force=True, ignore_permissions=True)
				continue
			frappe.db.set_value(doctype, row["name"], fieldname, updated, update_modified=False)
