"""
Single source of truth for mapping tool types to their handler function paths.

Used by both sdk_tools.create_agent_tools() and flow_tool_executor.execute().
Adding a new tool type only requires updating this file.
"""

# Maps Agent Tool Function.types → fully qualified handler function path
TOOL_TYPE_HANDLERS: dict[str, str] = {
	"Get List": "huf.ai.handlers.crud.handle_get_list",
	"Get Document": "huf.ai.handlers.crud.handle_get_document",
	"Update Document": "huf.ai.handlers.crud.handle_update_document",
	"Create Document": "huf.ai.handlers.crud.handle_create_document",
	"Delete Document": "huf.ai.handlers.crud.handle_delete_document",
	"Get Multiple Documents": "huf.ai.handlers.crud.handle_get_documents",
	"Create Multiple Documents": "huf.ai.handlers.crud.handle_create_documents",
	"Update Multiple Documents": "huf.ai.handlers.crud.handle_update_documents",
	"Delete Multiple Documents": "huf.ai.handlers.crud.handle_delete_documents",
	"Submit Document": "huf.ai.handlers.crud.handle_submit_document",
	"Cancel Document": "huf.ai.handlers.crud.handle_cancel_document",
	"Get Value": "huf.ai.handlers.crud.handle_get_value",
	"Set Value": "huf.ai.handlers.crud.handle_set_value",
	"Get Report Result": "huf.ai.handlers.crud.handle_get_report_result",
	"GET": "huf.ai.http_handler.handle_get_request",
	"POST": "huf.ai.http_handler.handle_post_request",
	"Run Agent": "huf.ai.handlers.agent_runner.handle_run_agent",
	"Attach File to Document": "huf.ai.handlers.crud.handle_attach_file_to_document",
	"Get Conversation Data": "huf.ai.handlers.conversation_data.handle_get_conversation_data",
	"Set Conversation Data": "huf.ai.handlers.conversation_data.handle_set_conversation_data",
	"Load Conversation Data": "huf.ai.handlers.conversation_data.handle_load_conversation_data",
}

# Tool types that require a reference_doctype injected as an extra arg
DOCTYPE_BOUND_TYPES: frozenset[str] = frozenset({
	"Get Document",
	"Get Multiple Documents",
	"Get List",
	"Create Document",
	"Create Multiple Documents",
	"Update Document",
	"Update Multiple Documents",
	"Delete Document",
	"Delete Multiple Documents",
	"Attach File to Document",
})
