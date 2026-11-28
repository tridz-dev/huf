"""Permission hook maps for huf (read by Frappe through ``huf.hooks``).

Moved out of ``huf/hooks.py`` to keep it under the file-size guard. ``huf/hooks.py`` re-exports
both names, so ``frappe.get_hooks`` and the dotted path ``huf.hooks.<name>`` stay valid.
"""

permission_query_conditions = {
    "Agent": "huf.huf.doctype.agent.agent.get_permission_query_conditions",
    "Agent Conversation": "huf.ai.agent.integration.get_conversation_permission_conditions",
    "Agent Message": "huf.ai.agent.integration.get_message_permission_conditions",
    "Agent Run": "huf.ai.agent.integration.get_run_permission_conditions",
    "Agent Context Artifact": "huf.ai.agent.integration.get_context_artifact_permission_conditions",
    "Agent Tool Call": "huf.ai.agent.integration.get_tool_call_permission_conditions",
    "Agent Run Prompt Snapshot": "huf.ai.agent.integration.get_prompt_snapshot_permission_conditions",
    "Huf API Key": "huf.huf.doctype.huf_api_key.huf_api_key.get_api_key_permission_conditions",
    "Flow Definition": "huf.huf.doctype.flow_definition.flow_definition.get_permission_query_conditions",
    "Agent Flow Run": "huf.ai.flow.app_scope.access.get_run_permission_query_conditions",
    "Flow Member State": "huf.ai.flow.app_scope.access.get_member_state_permission_query_conditions",
    "Agent Procedure": "huf.huf.doctype.agent_procedure.agent_procedure.get_permission_query_conditions",
    "Agent Procedure Binding": "huf.huf.doctype.agent_procedure_binding.agent_procedure_binding.get_permission_query_conditions",
    "Agent Procedure Run": "huf.huf.doctype.agent_procedure_run.agent_procedure_run.get_permission_query_conditions",
    "Agent Run Feedback": "huf.ai.record_access.get_feedback_permission_conditions",
    "Gateway": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Gateway Access Entry": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Gateway Event": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Gateway Binding": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Integration Settings": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Integration Service": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Integration Credential": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Solution": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Conversation Assignment": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "Template Usage": "huf.ai.gateway_webhook.get_permission_query_conditions_gateway_family",
    "HUF Document": "huf.huf.doctype.huf_document.huf_document.get_permission_query_conditions",
    "HUF Document Comment": "huf.huf.doctype.huf_document_comment.huf_document_comment.get_permission_query_conditions",
}

has_permission = {
	"Flow Definition": "huf.ai.flow.app_scope.access.has_permission_flow_definition",
	"Agent Flow Run": "huf.ai.flow.app_scope.access.has_permission_flow_run",
	"Flow Member State": "huf.ai.flow.app_scope.access.has_permission_member_state",
	"Agent Run": "huf.ai.hooks.has_permission_agent_run",
	"Agent Message": "huf.ai.hooks.has_permission_agent_message",
	"Agent Conversation": "huf.ai.hooks.has_permission_agent_conversation",
	"Agent Tool Call": "huf.ai.hooks.has_permission_agent_tool_call",
	"Agent Context Artifact": "huf.ai.hooks.has_permission_agent_context_artifact",
	"Gateway": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Gateway Access Entry": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Gateway Event": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Gateway Binding": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Integration Settings": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Integration Service": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Integration Credential": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Solution": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Conversation Assignment": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"Template Usage": "huf.ai.gateway_webhook.has_permission_gateway_family",
	"HUF Document": "huf.huf.doctype.huf_document.huf_document.has_permission",
	"HUF Document Comment": "huf.huf.doctype.huf_document_comment.huf_document_comment.has_permission",
}
