"""Tool type -> function_path map (single source of truth for the resolver)."""

from __future__ import annotations

TYPE_TO_FUNCTION_PATH: dict[str, str] = {
	"Get List": "huf.ai.sdk_tools.handle_get_list",
	"Get Document": "huf.ai.sdk_tools.handle_get_document",
	"Update Document": "huf.ai.sdk_tools.handle_update_document",
	"Create Document": "huf.ai.sdk_tools.handle_create_document",
	"Delete Document": "huf.ai.sdk_tools.handle_delete_document",
	"Get Multiple Documents": "huf.ai.sdk_tools.handle_get_documents",
	"Create Multiple Documents": "huf.ai.sdk_tools.handle_create_documents",
	"Update Multiple Documents": "huf.ai.sdk_tools.handle_update_documents",
	"Delete Multiple Documents": "huf.ai.sdk_tools.handle_delete_documents",
	"Submit Document": "huf.ai.sdk_tools.handle_submit_document",
	"Cancel Document": "huf.ai.sdk_tools.handle_cancel_document",
	"Get Value": "huf.ai.sdk_tools.handle_get_value",
	"Set Value": "huf.ai.sdk_tools.handle_set_value",
	"Get Report Result": "huf.ai.sdk_tools.handle_get_report_result",
	"GET": "huf.ai.http_handler.handle_get_request",
	"POST": "huf.ai.http_handler.handle_post_request",
	"Run Agent": "huf.ai.sdk_tools.handle_run_agent",
	"Code Execution": "huf.ai.tools.code_execution.run_python",
	"Attach File to Document": "huf.ai.sdk_tools.handle_attach_file_to_document",
	"Send Email": "huf.ai.sdk_tools.handle_send_email",
	"Get Conversation Data": "huf.ai.sdk_tools.handle_get_conversation_data",
	"Set Conversation Data": "huf.ai.sdk_tools.handle_set_conversation_data",
	"Load Conversation Data": "huf.ai.sdk_tools.handle_load_conversation_data",
	"Perplexity Search": "huf.ai.tools.perplexity.handle_perplexity_search",
	# Present on the LLM side (A) but absent from the deterministic side (B)
	# before this task -- seam audit §1. A Flow/Procedure node can now reach
	# these the same way the LLM can.
	"Save Memory Record": "huf.ai.memory_tools.handle_save_memory_record",
	"Search Memory Records": "huf.ai.memory_tools.handle_search_memory_records",
	"Get Memory Record": "huf.ai.memory_tools.handle_get_memory_record",
	"Archive Memory Record": "huf.ai.memory_tools.handle_archive_memory_record",
	"Promote Memory to Knowledge": "huf.ai.memory_tools.handle_promote_memory_to_knowledge",
}
