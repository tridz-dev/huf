"""What a tool does to the outside world: ``reads``, ``changes`` or ``sends``.

The one table the test run consults. A tool that is not listed here (a custom tool, an MCP tool, a tool added
later) counts as ``changes``, so forgetting to classify a tool can only make a test run skip it, never run it.

* ``reads``: only looks things up. A test run runs it for real.
* ``changes``: creates, updates or deletes something (a record, a file, a calendar event, a table row).
* ``sends``: reaches a person (email, chat message, notification).

A few tools do both depending on the call: ``http_request`` reads on GET and changes otherwise, and the
multi-action tools (CRM, ERPNext, Telegram ...) are classified by their ``action``.
"""

from __future__ import annotations

READS = "reads"
CHANGES = "changes"
SENDS = "sends"
EFFECTS = (READS, CHANGES, SENDS)
DEFAULT_EFFECT = CHANGES

_READS = (
	# chat and code hosts
	"slack_list_channels slack_get_channel_history slack_search_messages slack_list_users "
	"discord_get_messages discord_list_channels "
	"github_list_repos github_get_repo github_get_file github_search_code "
	# Frappe and ERPNext
	"erpnext_run_report erpnext_list_reports frappe_get_doctype_meta frappe_list_records frappe_get_record "
	"render_frappe_view get_integration_recipient resolve_recent_resource "
	# Google
	"gmail_get_emails gsheets_read gcalendar_list_events "
	"gmaps_search_places gmaps_get_directions gmaps_geocode gmaps_reverse_geocode "
	"gplaces_text_search gplaces_place_details gplaces_place_photo gplaces_autocomplete gplaces_nearby_search "
	"gdrive_list_files gdrive_get_file gdrive_search_files "
	# web research
	"serp_hotel_search serp_hotel_details serp_hotel_details_batch serp_google_maps_reviews "
	"serp_google_hotel_reviews serp_tripadvisor_search serp_tripadvisor_reviews serp_yelp_search "
	"serp_yelp_reviews serp_youtube_search youtube_transcript "
	# tables, agents and apps (lookups only)
	"list_table_rows list_provider_options list_agents find_existing_agents discover_site_capabilities "
	"get_agent list_apps get_app list_document_artifacts list_app_components render_app_component "
	"render_mermaid render_chart show_artifact list_tool_groups search_tools describe_tool_group load_tools "
	"ask_user "
	# Frappe Cloud lookups
	"fc_list_benches fc_get_bench fc_bench_options fc_list_sites fc_site_options fc_site_plans "
	"fc_list_webhooks fc_available_webhook_events fc_list_ssh_keys fc_list_servers fc_get_server "
	"fc_get_server_overview fc_server_options fc_server_plans fc_server_usage fc_list_server_benches "
	"fc_list_server_jobs fc_list_server_plays fc_list_bench_jobs fc_list_marketplace_apps "
	# desktop lookups
	"desktop_workspace_info desktop_list_files desktop_read_file desktop_search_files desktop_skill_list "
	"desktop_skill_read desktop_process_list desktop_process_logs desktop_mcp_find"
).split()

_SENDS = (
	"slack_send_message slack_send_thread_reply discord_send_message google_chat_send_message "
	"google_chat_send_card telegram whatsapp messenger gmail_send_email google_meet_create_event "
	"gateway_send gateway_reply handoff_to_solution"
).split()

_CHANGES = (
	"github_create_issue github_create_pr discord_delete_message frappe_crm helpdesk raven erpnext "
	"erpnext_crm erpnext_inventory frappe_create_record frappe_update_record http_request "
	"gmail_create_draft gmail_mark_as_read gsheets_update gsheets_create gcalendar_create_event "
	"gcalendar_update_event gcalendar_delete_event run_ssh_command create_huf_table add_table_row "
	"update_table_row delete_table_row draft_agent update_agent_prompt attach_agent_tools publish_agent "
	"create_agent_tool google_meet_create_space draft_app update_app install_app set_app_icon docker_execution "
	"fc_create_bench fc_archive_bench fc_add_app_to_bench fc_create_site fc_drop_site fc_backup_site "
	"fc_download_backup fc_migrate_site fc_clear_cache fc_update_site fc_clone_site fc_add_app_to_site "
	"fc_get_admin_login_link fc_add_webhook fc_update_webhook fc_delete_webhook fc_add_ssh_key "
	"fc_mark_ssh_key_default fc_get_bench_ssh_certificate fc_generate_bench_ssh_certificate fc_create_server "
	"fc_archive_server fc_reboot_server fc_rename_server fc_change_server_plan telegram_admin "
	"export_artifact export_document redline_artifact desktop_write_file desktop_edit_file "
	"desktop_make_directory desktop_move_path desktop_delete_path desktop_run_command desktop_skill_run "
	"desktop_process_start desktop_process_stop desktop_local_mcp desktop_mcp_call desktop_browser "
	"run_flow resume_flow_run approve_flow_run gateway_handoff"
).split()

# Names not in the lists above that still read: flow tools that only look at a run.
_READS += ["get_flow_run"]

TOOL_EFFECTS: dict[str, str] = {
	**dict.fromkeys(_CHANGES, CHANGES),
	**dict.fromkeys(_SENDS, SENDS),
	**dict.fromkeys(_READS, READS),
}

# Agent Tool Function "types" (custom tools) -> effect. Any type not listed counts as ``changes``.
TYPE_EFFECTS: dict[str, str] = {
	**dict.fromkeys(
		(
			"Get Document", "Get Multiple Documents", "Get List", "Get Report Result", "Get Value", "GET",
			"Get Amended Document", "Get Conversation Data", "Load Conversation Data", "Perplexity Search",
			"Search Memory Records", "Get Memory Record",
		),
		READS,
	),
	"Send Email": SENDS,
}

_ACTION_READS = ("list", "get", "search", "find", "read", "describe", "check", "show", "view", "fetch", "query", "stock_balance", "item_prices", "summary", "report")
_ACTION_SENDS = ("send", "reply", "broadcast", "notify", "post_message", "forward")

# Multi-action tools: the ``action`` argument decides, the table above is the fallback.
_ACTION_TOOLS = frozenset(
	"frappe_crm helpdesk raven erpnext erpnext_crm erpnext_inventory telegram whatsapp messenger "
	"docker_execution telegram_admin".split()
)
_READ_METHODS = ("", "GET", "HEAD")


def _action_effect(action) -> str | None:
	text = str(action or "").strip().lower()
	if not text:
		return None
	if text.startswith(_ACTION_SENDS) or any(word in text for word in ("send_", "_send")):
		return SENDS
	if text.startswith(_ACTION_READS):
		return READS
	return CHANGES


def effect_of_type(tool_type) -> str:
	return TYPE_EFFECTS.get(tool_type or "", DEFAULT_EFFECT)


def tool_effect(tool_id: str | None, args: dict | None = None, tool_type: str | None = None) -> str:
	"""``reads``, ``changes`` or ``sends`` for one call of ``tool_id``.

	``args`` refine the answer for the tools that do either: an HTTP request is a read only for GET / HEAD, and a
	multi-action tool by its ``action``. ``tool_type`` (an Agent Tool Function type) classifies custom tools that are
	not in the table. Unknown tools are ``changes``.
	"""
	args = args if isinstance(args, dict) else {}
	name = str(tool_id or "")
	if name == "http_request":
		method = str(args.get("method") or "").strip().upper()
		return READS if method in _READ_METHODS else CHANGES
	if name in _ACTION_TOOLS:
		refined = _action_effect(args.get("action"))
		if refined:
			return refined
	if name in TOOL_EFFECTS:
		return TOOL_EFFECTS[name]
	if tool_type:
		return effect_of_type(tool_type)
	return DEFAULT_EFFECT


def known_tool_names() -> set[str]:
	return set(TOOL_EFFECTS)
