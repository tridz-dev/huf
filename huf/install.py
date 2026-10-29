# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for Huf app
"""

import json

import frappe

from huf.utils import is_frappe_16

logger = frappe.logger("huf")

def _resolve_workspace_link_type():
	"""Pick a link_type whose target actually resolves for link_to="Huf".

	Frappe validates Desktop Icon.link_to against the doctype named by
	link_type. "Workspace Sidebar" does not always carry a "Huf" record at
	after_app_install time (on a fresh site it does not exist yet), which made
	frappe raise LinkValidationError and abort the whole install. Fall back to
	"Workspace", which the fixture sync has already created by this point.
	"""
	for link_type in ("Workspace Sidebar", "Workspace"):
		if not frappe.db.table_exists(f"tab{link_type}"):
			continue
		if frappe.db.exists(link_type, "Huf"):
			return link_type
	return None


def setup_desktop_icon_as_workspace(app_name):
	"""
	Replace the External App desktop icon with a Workspace Sidebar icon.
	Runs after Frappe creates desktop icons, so we fix the Huf icon to use Workspace Sidebar.
	Only applies on Frappe version 16 and above.

	This is cosmetic: any failure here is logged and swallowed rather than
	aborting `bench install-app huf`.
	"""
	if not is_frappe_16() or app_name != "huf":
		return

	try:
		_setup_desktop_icon_as_workspace()
	except Exception:
		frappe.db.rollback()
		logger.warning("huf: skipped desktop icon setup", exc_info=True)
		frappe.log_error(
			title="Huf: desktop icon setup skipped",
			message=frappe.get_traceback(with_context=True),
		)


def _setup_desktop_icon_as_workspace():
	link_type = _resolve_workspace_link_type()
	if not link_type:
		logger.warning("huf: no resolvable workspace link target; skipping desktop icon")
		return

	# Delete the App icon (External type) - we want Workspace Sidebar instead
	app_icons = frappe.get_all(
		"Desktop Icon",
		filters={"label": "Huf", "icon_type": "App", "app": "huf"},
		pluck="name",
	)
	for name in app_icons:
		frappe.delete_doc("Desktop Icon", name, force=True)
		frappe.db.commit()

	# Ensure the Huf workspace icon exists and is visible (Workspace Sidebar type)
	workspace_icon = frappe.db.exists(
		"Desktop Icon",
		{"label": "Huf", "icon_type": "Link"},
	)
	if workspace_icon:
		doc = frappe.get_doc("Desktop Icon", workspace_icon)
		doc.link_type = link_type
		doc.link_to = "Huf"
		doc.hidden = 0
		doc.parent_icon = None
		doc.standard = 1
		doc.logo_url = "/assets/huf/Images/huf.png"
		doc.save()
	else:
		# Create if workspace icon doesn't exist (e.g. workspace created later)
		workspace = frappe.db.get_value("Workspace", "Huf", ["name", "icon"], as_dict=True)
		if workspace:
			icon = frappe.new_doc("Desktop Icon")
			icon.label = "Huf"
			icon.icon_type = "Link"
			icon.link_type = link_type
			icon.link_to = "Huf"
			icon.icon = workspace.get("icon") or "header"
			icon.standard = 1
			icon.logo_url = "/assets/huf/Images/huf.png"
			icon.insert()

	frappe.db.commit()


def after_install():
    create_huf_roles()
    create_demo_ai_providers()
    create_demo_ai_models()
    create_hub_orchestrator_agent()
    create_design_system_skill()
    create_meeting_summary_agent()
    create_meeting_recorder_app()
    create_whatsapp_app()
    create_image_generation_tool()
    create_transcribe_audio_tool()
    create_generate_audio_tool()
    remove_deprecated_gemini_audio_tools()
    create_ocr_document_tool()
    create_flow_tools()
    create_memory_tools()
    create_code_execution_tools()
    create_default_memory_policies()
    create_default_execution_profiles()
    register_integration_services()
    sync_tool_types()
    sync_default_tool_categories()
    seed_skill_categories()
    from huf.ai.tools.registry import sync_discovered_tools
    sync_discovered_tools(use_cache=False)
    frappe.db.commit()
    """
	Called after app installation.
	Checks if litellm is installed and provides helpful message if not.
	"""
    try:
        from importlib.metadata import version as get_installed_version

        import litellm

        litellm_version = get_installed_version("litellm")
        compromised_versions = {"1.82.7", "1.82.8"}

        if litellm_version in compromised_versions:
            frappe.msgprint(
                "🚨 Compromised LiteLLM version detected "
                f"({litellm_version}). Rotate credentials and reinstall a safe version immediately.",
                indicator="red",
                title="Critical Security Alert",
            )
        else:
            frappe.msgprint(f"✅ LiteLLM is installed and ready to use (v{litellm_version}).")
    except ImportError:
    	frappe.msgprint(
			"⚠️ LiteLLM package not found. "
			"Please run 'bench setup requirements' to install dependencies, "
			"then restart your site with 'bench restart'.",
			indicator="orange",
			title="Dependency Missing"
		)


#: Frappe's scheduler wakes every ``scheduler_tick_interval`` seconds (default 240). Flow approval
#: timeouts and "every minute" schedules are only as precise as that tick, so Huf wants 60.
FLOW_SCHEDULER_TICK_SECONDS = 60


def ensure_scheduler_tick():
	"""Set ``scheduler_tick_interval`` to 60 s when the bench has not chosen a value.

	Frappe reads the tick in the bench-wide scheduler process, which has no site context, so only
	``common_site_config.json`` is honoured: a value in a site's ``site_config.json`` is ignored.
	An explicit value already in the common config is respected. The running ``bench schedule``
	process reads the value at start, so it must be restarted once for a change to apply.
	"""
	try:
		import json
		import os

		from frappe.installer import update_site_config

		path = os.path.join(frappe.local.sites_path or "sites", "common_site_config.json")
		with open(path) as fh:
			if json.load(fh).get("scheduler_tick_interval"):
				return
		update_site_config("scheduler_tick_interval", FLOW_SCHEDULER_TICK_SECONDS, site_config_path=path)
		frappe.logger("huf").info(
			"Set scheduler_tick_interval=%s in common_site_config.json (restart the scheduler to apply)",
			FLOW_SCHEDULER_TICK_SECONDS,
		)
	except Exception:
		frappe.log_error(title="huf after_migrate: scheduler_tick_interval not set", message=frappe.get_traceback())


def after_migrate():
	"""
	Called after app migration.
	Syncs all discovered tools from all installed apps.
	"""
	create_huf_roles()
	ensure_scheduler_tick()
	try:
		from huf.ai.document_search import ensure_fulltext_indexes

		ensure_fulltext_indexes()
	except Exception:
		frappe.log_error(title="huf after_migrate: HUF Document FULLTEXT index failed")
	create_demo_ai_providers()
	try:
		create_demo_ai_models()
	except Exception:
		# Seeding walks every catalogue row and saves through full AI Model
		# validation, so a single unexpected row must not abort the desktop
		# icon, tool creation and everything else below.
		frappe.log_error(title="huf after_migrate: AI Model seeding failed", message=frappe.get_traceback())
	try:
		setup_desktop_icon_as_workspace("huf")
	except frappe.LinkValidationError:
		pass
	try:
		create_image_generation_tool()
		create_transcribe_audio_tool()
		create_generate_audio_tool()
		remove_deprecated_gemini_audio_tools()
		create_ocr_document_tool()
		create_flow_tools()
		create_memory_tools()
		create_code_execution_tools()
		create_default_memory_policies()
		create_default_execution_profiles()
		register_integration_services()
		sync_tool_types()
		sync_default_tool_categories()
		seed_skill_categories()
		from huf.ai.tools.registry import sync_discovered_tools
		result = sync_discovered_tools(use_cache=False)  # Full scan (apps_to_scan=None)
		logger.info(
			f"Synced tools after migrate: {result.get('total_tools', 0)} tools from {len(result.get('synced_apps', []))} apps"
		)
		if result.get("error_count"):
			# A tool that fails import/validation is silently skipped by the sync,
			# so a new registry block (e.g. telegram_admin) would just not appear.
			frappe.log_error(
				title="Tool sync after migrate had errors",
				message="\n".join(result.get("errors", [])),
			)
	except Exception as e:
		logger.warning(f"Failed to sync tools after migrate: {e!s}")

	try:
		from huf.huf.erpnext_knowledge_seed import seed_erpnext_knowledge
		seed_erpnext_knowledge()
	except Exception as e:
		logger.warning(f"Failed to seed ERPNext docs knowledge after migrate: {e!s}")

	try:
		from huf.ai.app_seeding.seeder import seed_all
		results = list(seed_all())
		seed_logger = frappe.logger("app_seeding")
		_log_seed_results(results, seed_logger)
	except Exception as e:
		logger.warning(f"App seeding failed: {e!s}")

	try:
		create_hub_orchestrator_agent()
	except Exception as e:
		logger.warning(f"Failed to seed Hub Orchestrator agent after migrate: {e!s}")

	try:
		create_design_system_skill()
	except Exception as e:
		logger.warning(f"Failed to seed HUF Design System Reference skill after migrate: {e!s}")

	try:
		create_meeting_summary_agent()
	except Exception as e:
		logger.warning(f"Failed to seed Meeting Summary agent after migrate: {e!s}")

	try:
		create_meeting_recorder_app()
	except Exception as e:
		logger.warning(f"Failed to seed Meeting Recorder HUF App after migrate: {e!s}")

	try:
		create_whatsapp_app()
	except Exception as e:
		logger.warning(f"Failed to seed WhatsApp HUF App after migrate: {e!s}")

	ensure_whatsapp_message_indexes()

	try:
		from huf.ai.app_seeding.apps_loader import sync_huf_apps
		summary = sync_huf_apps()
		logger.info(
			f"Synced HUF Apps after migrate: {summary.get('synced', 0)} synced, "
			f"{summary.get('invalid', 0)} invalid, {summary.get('deleted', 0)} deleted"
		)
	except Exception as e:
		logger.warning(f"HUF Apps sync failed: {e!s}")


def _log_seed_results(results, logger):
	"""Emit WARNING-level structured logs for skipped seed records and per-app summaries."""
	for r in results:
		for rec in r.skipped_records:
			logger.warning(json.dumps({
				"app": rec["app"],
				"file": rec["file"],
				"record": rec["record"],
				"missing_refs": rec.get("missing_refs", [])
			}))
		logger.warning(json.dumps({
			"app": r.app,
			"skipped_count": r.skipped,
			"seeded_count": r.seeded
		}))

def create_demo_ai_providers():
    providers = [
        # {"doctype": "AI Provider", "provider_name": "Meta", "provider_brand": "meta", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "TogetherAI", "provider_brand": "togetherai", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Azure OpenAI", "provider_brand": "azure", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Ollama", "provider_brand": "ollama", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "xAI", "provider_brand": "xai", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Mistral", "provider_brand": "mistral", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Alibaba", "provider_brand": "alibaba", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "AWS Bedrock", "provider_brand": "amazon-bedrock", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Vertex AI", "provider_brand": "google-vertex", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "ElevenLabs", "provider_brand": "elevenlabs", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Groq", "provider_brand": "groq", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "DeepSeek", "provider_brand": "deepseek", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Huggingface", "provider_brand": "huggingface", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Cohere", "provider_brand": "cohere", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Perplexity", "provider_brand": "perplexity", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Moonshot", "provider_brand": "moonshot", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Google", "provider_brand": "google", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Anthropic", "provider_brand": "anthropic", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "OpenRouter", "provider_brand": "openrouter", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "OpenAI", "provider_brand": "openai", "api_key": ""},
        
        
    ]

    for p in providers:
        if not frappe.db.exists("AI Provider", p["provider_name"]):
            doc = frappe.get_doc(p)
            doc.flags.ignore_mandatory = True
            doc.flags.ignore_validate = True
            doc.insert(ignore_permissions=True)

def create_demo_ai_models():
	"""Upsert the AI Model catalogue (additive; never deletes or repoints).

	huf.ai.model_catalogue (generated by scripts/gen_model_catalogue.py) is the
	single source of truth for seeded models.
	"""
	from huf.ai.model_catalogue_sync import upsert_models

	upsert_models()


def seed_voice_engines():
	"""Ensure a Voice Engine row exists for every engine discovered by the registry.

	Idempotent and safe to call on after_migrate even when zero engines are
	registered (the current state, since the registry starts empty). Existing
	rows are left alone except for backfilling a missing label/kind, so user
	edits are preserved.
	"""
	try:
		from huf.ai.voice import get_engine, supported_engines

		for engine_key in supported_engines():
			engine = get_engine(engine_key)
			label = getattr(engine, "label", engine_key)
			kind = getattr(engine, "kind", None)

			if not frappe.db.exists("Voice Engine", engine_key):
				doc = frappe.new_doc("Voice Engine")
				doc.engine_key = engine_key
				doc.label = label
				doc.kind = kind
				doc.enabled = 1
				doc.insert(ignore_permissions=True)
				continue

			existing = frappe.get_doc("Voice Engine", engine_key)
			dirty = False
			if not existing.get("label") and label:
				existing.label = label
				dirty = True
			if not existing.get("kind") and kind:
				existing.kind = kind
				dirty = True
			if dirty:
				existing.save(ignore_permissions=True)
	except Exception as e:
		logger.warning(f"Failed to seed voice engines: {e!s}")


def create_hub_orchestrator_agent():
	"""
	Idempotent: seed the "Hub Orchestrator" system agent that powers hub chat.
	Safe to call on both after_install and after_migrate.
	"""
	from huf.ai.app_seeding.hub_orchestrator import create_hub_orchestrator_agent as _create

	try:
		_create()
	except Exception as e:
		logger.warning(f"Failed to seed Hub Orchestrator agent: {e!s}")


def create_design_system_skill():
	"""
	Idempotent: seed the "HUF Design System Reference" Skill (list_app_components /
	render_app_component reference) and attach it to Hub Orchestrator.
	Safe to call on both after_install and after_migrate.
	"""
	from huf.ai.app_seeding.design_system_skill import create_design_system_skill as _create

	try:
		_create()
	except Exception as e:
		logger.warning(f"Failed to seed HUF Design System Reference skill: {e!s}")


from huf.setup_data.meeting_summary import (  # noqa: F401
	MEETING_SUMMARY_AGENT_NAME,
	MEETING_SUMMARY_INSTRUCTIONS,
	MEETING_SUMMARY_PREFERRED_MODELS,
)


def _meeting_summary_model():
	"""First AI Model on the Google provider, preferring the light chat models."""
	if not frappe.db.exists("AI Provider", "Google"):
		return None

	models = frappe.get_all(
		"AI Model",
		filters={"provider": "Google"},
		pluck="name",
		order_by="creation asc",
	)
	for preferred in MEETING_SUMMARY_PREFERRED_MODELS:
		if preferred in models:
			return preferred
	return models[0] if models else None


def create_meeting_summary_agent():
	"""
	Idempotent: seed the "Meeting Summary Agent" system agent used to turn a
	finalized Meeting transcript into a structured Markdown summary (see
	huf.ai.meetings.meeting_summary.run_meeting_summary).

	This agent's name is also hardcoded by Phase 4's meeting_transcription.py
	(TRANSCRIPTION_AGENT) to resolve STT config for chunk transcription, so
	its name must stay exactly "Meeting Summary Agent".

	Provider/model default to the Google/Gemini AI Model records seeded by
	create_demo_ai_models(), following the same "pick a sensible default,
	never hardcode a key" convention as create_hub_orchestrator_agent(). If
	no Google AI Model is configured yet, the agent is seeded disabled so it
	does not block install; it can be reconfigured from the Agent list once
	a provider/model is available.

	Safe to call on both after_install and after_migrate.
	"""
	fields = {
		"agent_name": MEETING_SUMMARY_AGENT_NAME,
		"description": "Summarizes a finalized Meeting transcript into headline, key points, and action items.",
		"prompt_mode": "Local",
		"instructions": MEETING_SUMMARY_INSTRUCTIONS,
		"is_system": 1,
		"allow_chat": 0,
		"persist_conversation": 0,
		"run_immediately": 1,
		"allow_guest": 0,
	}

	model = _meeting_summary_model()
	if model:
		fields["provider"] = "Google"
		fields["model"] = model
		fields["disabled"] = 0
	else:
		fields["disabled"] = 1

	previous_in_seeding = getattr(frappe.flags, "in_seeding", False)
	frappe.flags.in_seeding = True
	try:
		if frappe.db.exists("Agent", MEETING_SUMMARY_AGENT_NAME):
			doc = frappe.get_doc("Agent", MEETING_SUMMARY_AGENT_NAME)
			for fieldname, value in fields.items():
				doc.set(fieldname, value)
			doc.save(ignore_permissions=True)
			return

		doc = frappe.get_doc({"doctype": "Agent", **fields})
		if not model:
			doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
	finally:
		frappe.flags.in_seeding = previous_in_seeding


def create_meeting_recorder_app():
	"""
	Idempotent: seed the "Meeting Recorder" HUF App manifest entry.

	Meeting Recorder is a first-party huf feature, not a third-party app
	manifest discovered via huf.ai.app_seeding.apps_loader (that scanner
	explicitly skips the "huf" app itself), so it is seeded directly here
	following the same get_value-check-then-insert-or-update pattern used
	for the other install.py-seeded primitives (e.g. create_hub_orchestrator_agent).
	Safe to call on both after_install and after_migrate.

	This is also huf's own reference/example app, so it seeds alias/is_public/
	agent/delivery to demonstrate Phase 1's public guest portal
	(/huf/apps/meeting-recorder) and Phase 4's delivery metadata out of the
	box, matching what apps_loader.upsert_huf_app does for third-party
	manifests (see huf.ai.app_seeding.apps_loader.upsert_huf_app and
	doc/features/apps/delivery-portal-vs-desk.md).

	"route" stays "/huf/meetings" -- the classic SPA deep-link route -- since
	Phase 4 deliberately kept Desk pages coexisting with the SPA rather than
	replacing it; "delivery": "desk" only controls which surface renders
	/huf/apps/meeting-recorder, it does not retire the SPA route.
	"""
	app_id = "meeting-recorder"
	fields = {
		"title": "Meeting Recorder",
		"description": "Record, transcribe, and summarize meetings.",
		"route": "/huf/meetings",
		"icon": "mic",
		"category": "Productivity",
		"enabled": 1,
		"sync_status": "Active",
		"source_app": "huf",
		"alias": "meeting-recorder",
		"is_public": 1,
		"agent": MEETING_SUMMARY_AGENT_NAME,
		"delivery": "desk",
	}

	existing_name = frappe.db.get_value("HUF App", {"app_id": app_id}, "name")
	if existing_name:
		# Same manual-override carve-out as apps_loader.upsert_huf_app: a
		# System Manager's hand-edit to enabled/alias/is_public/agent should
		# survive re-sync on migrate, so updates never touch those fields.
		update_fields = {
			k: v
			for k, v in fields.items()
			if k not in ("enabled", "alias", "is_public", "agent")
		}
		frappe.db.set_value("HUF App", existing_name, update_fields)
		return

	doc = frappe.get_doc({"doctype": "HUF App", "app_id": app_id, **fields})
	try:
		doc.insert(ignore_permissions=True)
	except Exception as e:
		logger.warning(f"Failed to seed Meeting Recorder HUF App: {e!s}")


WHATSAPP_APP_ID = "whatsapp"


def create_whatsapp_app():
	"""
	Idempotent: seed the first-party "WhatsApp" HUF App tile.

	Mirrors create_meeting_recorder_app: inserted once, then only the managed
	fields are refreshed so an admin's hand-edit of ``enabled`` survives migrate.
	Visibility is decided at request time by ``can_launch_whatsapp_app``.
	"""
	fields = {
		"title": "WhatsApp",
		"description": "Manage WhatsApp templates and see messages handled by your agents.",
		"route": "/huf/whatsapp",
		"icon": "message-circle",
		"category": "Communicate",
		"sort_order": 110,
		"launch_mode": "Route",
		"enabled": 1,
		"sync_status": "Active",
		"source_app": "huf",
		"permission_method": "huf.ai.whatsapp.management.can_launch_whatsapp_app",
	}

	existing_name = frappe.db.get_value("HUF App", {"app_id": WHATSAPP_APP_ID}, "name")
	if existing_name:
		update_fields = {k: v for k, v in fields.items() if k != "enabled"}
		frappe.db.set_value("HUF App", existing_name, update_fields)
		return

	doc = frappe.get_doc({"doctype": "HUF App", "app_id": WHATSAPP_APP_ID, **fields})
	try:
		doc.insert(ignore_permissions=True)
	except Exception as e:
		logger.warning(f"Failed to seed WhatsApp HUF App: {e!s}")


WHATSAPP_MESSAGE_INDEXES = (
	("idx_huf_wa_msg_account_creation", ["whatsapp_account", "creation"]),
	("idx_huf_wa_msg_message_id", ["message_id"]),
)


def ensure_whatsapp_message_indexes():
	"""Idempotent Huf-owned indexes for the message log on frappe_whatsapp's ``WhatsApp Message``.

	No-op when the DocType is absent (direct mode). Never raises.
	"""
	import time

	try:
		if not frappe.db.exists("DocType", "WhatsApp Message"):
			return
		table = "tabWhatsApp Message"
		for name, columns in WHATSAPP_MESSAGE_INDEXES:
			started = time.monotonic()
			try:
				if frappe.db.has_index(table, name):
					continue
				frappe.db.add_index("WhatsApp Message", columns, name)
				logger.info(f"Added index {name} on {table} in {time.monotonic() - started:.2f}s")
			except Exception as e:
				if "Duplicate key name" not in str(e):
					logger.warning(f"Could not add index {name} on {table}: {e!s}")
	except Exception as e:
		logger.warning(f"WhatsApp Message index setup skipped: {e!s}")


def create_image_generation_tool():
    """Create the image generation tool in Agent Tool Function DocType."""
    tool_name = "generate_image"
    # Check if tool already exists
    if frappe.db.exists("Agent Tool Function", {"tool_name": tool_name}):
        return
    if not frappe.db.exists("Agent Tool Type","Generation"):
        tool_type_doc=frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1="Generation"
        tool_type_doc.insert()
    # Define tool parameters (child table entries)
    parameters = [
        {
            "label": "Prompt",
            "fieldname": "prompt",
            "type": "string",
            "required": 1,
            "description": "A detailed text description of the image to generate. Be specific about style, colors, composition, and subject matter."
        },
        {
            "label": "Size",
            "fieldname": "size",
            "type": "string",
            "required": 0,
            "description": "Image dimensions. Default: 'auto'. Options vary by model. <a href='https://docs.litellm.ai/docs/image_generation#optional-litellm-fields'>Documentation</a>",
            "options": "auto"
        },
        {
            "label": "Quality",
            "fieldname": "quality",
            "type": "string",
            "required": 0,
            "description": "Image quality. Default 'auto'. Options vary by model. <a href='https://docs.litellm.ai/docs/image_generation#optional-litellm-fields'>Documentation</a>",
            "options": "auto"
        },
        {
            "label": "Number of Images",
            "fieldname": "n",
            "type": "integer",
            "required": 0,
            "description": "Number of images to generate. Default: 1. Some models only support n=1."
        },
        {
            "label": "Response Format",
            "fieldname": "response_format",
            "type": "string",
            "required": 0,
            "description": "Response format. Default 'url'",
            "options": "url\nb64_json."
        }
    ]
    
    # Create tool document
    tool_doc = frappe.get_doc({
        "doctype": "Agent Tool Function",
        "tool_name": tool_name,
        "description": "Generate an image from a text description using AI. Use this when the user asks for image creation, visualization, or artwork generation. Do not show the image URL in the output message.",
        "types": "Custom Function",
        "function_path": "huf.ai.sdk_tools.handle_generate_image",
        "pass_parameters_as_json": 1,
        "parameters": parameters,
        "tool_type": "Generation"
    })
    try:
        tool_doc.insert()
    except Exception as e:
        logger.warning(f"Error creating image generation tool: {e!s}")


def create_ocr_document_tool():
    """Create or update the ocr_document tool in Agent Tool Function DocType."""
    tool_name = "ocr_document"
    
    # Ensure OCR tool type exists
    if not frappe.db.exists("Agent Tool Type", "OCR"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "OCR"
        tool_type_doc.insert()
    
    # Check if tool already exists
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
    
    if tool_exists:
        # Update existing tool
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        tool_doc.description = "Extract text from documents and images using OCR. Supports PDFs, images, scanned documents, Word/Excel/PowerPoint documents (DOCX/XLSX/PPTX), text files (TXT/MD/CSV/JSON/XML/LOG), and HTML. Uses local extractors when possible, vision models for images, and OCR endpoints or vision models for PDFs."
        tool_doc.function_path = "huf.ai.sdk_tools.handle_ocr_document"
        tool_doc.tool_type = "OCR"
        try:
            tool_doc.save()
        except Exception as e:
            logger.warning(f"Error updating ocr_document tool: {e!s}")
    else:
        # Create new tool
        parameters = [
            {
                "label": "File ID",
                "fieldname": "file_id",
                "type": "string",
                "required": 0,
                "description": "File document ID from Frappe (preferred). File must exist in the system."
            },
            {
                "label": "File URL",
                "fieldname": "file_url",
                "type": "string",
                "required": 0,
                "description": "File URL/path (alternative to file_id). Example: /files/document.pdf"
            },
            {
                "label": "Pages",
                "fieldname": "pages",
                "type": "string",
                "required": 0,
                "description": "Comma-separated page numbers to process (e.g., '0,1,2'). Leave empty for all pages. Only for PDFs."
            },
            {
                "label": "Include Images",
                "fieldname": "include_images",
                "type": "boolean",
                "required": 0,
                "description": "Extract images from document as base64. Only for PDFs with OCR endpoint."
            },
            {
                "label": "Model",
                "fieldname": "model",
                "type": "string",
                "required": 0,
                "description": "Optional OCR/Vision model override. Defaults based on provider and file type."
            }
        ]
        
        tool_doc = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": tool_name,
            "description": "Extract text from documents and images using OCR. Supports PDFs, images, scanned documents, Word/Excel/PowerPoint documents (DOCX/XLSX/PPTX), text files (TXT/MD/CSV/JSON/XML/LOG), and HTML. Uses local extractors when possible, vision models for images, and OCR endpoints or vision models for PDFs.",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_ocr_document",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "OCR"
        })
        
        try:
            tool_doc.insert()
        except Exception as e:
            logger.warning(f"Error creating ocr_document tool: {e!s}")

def create_generate_audio_tool():
    """Create or update the generate_audio tool in Agent Tool Function DocType."""
    tool_name = "generate_audio"

    parameters = [
        {
            "label": "Input Text",
            "fieldname": "input",
            "type": "string",
            "required": 1,
            "description": "The text to convert to speech. Maximum length varies by provider."
        },
        {
            "label": "Voice",
            "fieldname": "voice",
            "type": "string",
            "required": 0,
            "description": (
                "Voice identifier for the TTS provider. "
                "IMPORTANT: Leave this blank - the voice is automatically determined by the agent's TTS configuration (tts_voice field). Only set this if the user has explicitly asked for a specific voice AND provided the exact voice ID for the active TTS provider."
            )
        },
        {
            "label": "Model",
            "fieldname": "model",
            "type": "string",
            "required": 0,
            "description": (
                "TTS model override."
                "IMPORTANT: Leave this blank — the model is automatically determined by the agent's TTS configuration (tts_model field). Only set this if the user has explicitly asked to use a specific TTS model."
            )
        },
        {
            "label": "Speed",
            "fieldname": "speed",
            "type": "number",
            "required": 0,
            "description": "Speech speed from 0.25 to 4.0. Default: 1.0."
        },
        {
            "label": "Response Format",
            "fieldname": "response_format",
            "type": "string",
            "required": 0,
            "description": "Audio format. Default: 'mp3'. Options: mp3, opus, aac, flac, wav, pcm.",
            "options": "mp3\nopus\naac\nflac\nwav\npcm"
        }
    ]

    # Ensure Audio Generation tool type exists
    if not frappe.db.exists("Agent Tool Type", "Audio Generation"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "Audio Generation"
        tool_type_doc.insert()

    # Check if tool already exists
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})


    if tool_exists:
        # Update existing tool - add missing parameters if needed
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        tool_doc.description = "Generate audio (speech) from text using AI text-to-speech. Use this when the user asks to convert text to speech, create voice narration, or generate audio. Supports multiple providers via LiteLLM (OpenAI, Gemini, ElevenLabs, etc.)."
        tool_doc.function_path = "huf.ai.sdk_tools.handle_generate_audio"
        tool_doc.tool_type = "Audio Generation"
        tool_doc.set("parameters", [])
        for p in parameters:
            tool_doc.append("parameters", p)
        try:
            tool_doc.save()
        except Exception as e:
            logger.warning(f"Error updating generate_audio tool: {e!s}")
    else:
        # Create new tool
        tool_doc = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": tool_name,
            "description": "Generate audio (speech) from text using AI text-to-speech. Use this when the user asks to convert text to speech, create voice narration, or generate audio. Supports multiple providers via LiteLLM (OpenAI, Gemini, ElevenLabs, etc.).",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_generate_audio",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "Audio Generation"
        })
        
        try:
            tool_doc.insert()
        except Exception as e:
            logger.warning(f"Error creating generate_audio tool: {e!s}")

def create_transcribe_audio_tool():
    """Create or update the transcribe_audio tool in Agent Tool Function DocType."""
    tool_name = "transcribe_audio"
    
    parameters = [
        {
            "label": "File ID",
            "fieldname": "file_id",
            "type": "string",
            "required": 0,
            "description": "File document ID from Frappe (preferred). File must exist in the system."
        },
        {
            "label": "File URL",
            "fieldname": "file_url",
            "type": "string",
            "required": 0,
            "description": "File URL/path (alternative to file_id). Example: /files/audio.mp3"
        },
        {
            "label": "File Path",
            "fieldname": "file_path",
            "type": "string",
            "required": 0,
            "description": "Absolute server path inside an allowed audio import directory"
        },
        {
            "label": "Language",
            "fieldname": "language",
            "type": "string",
            "required": 0,
            "description": "Optional language code in ISO 639-1 format (e.g., 'en', 'es', 'fr', 'de'). If omitted, language is auto-detected."
        },
        {
            "label": "Model",
            "fieldname": "model",
            "type": "string",
            "required": 0,
            "description": "Optional transcription model. Defaults based on provider: OpenAI uses 'gpt-transcribe', Groq uses 'groq/whisper-large-v3-turbo', Google uses 'gemini/gemini-flash-latest', Deepgram uses 'deepgram/nova-3'."
        }
    ]

    # Ensure Transcription tool type exists
    if not frappe.db.exists("Agent Tool Type", "Transcription"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "Transcription"
        tool_type_doc.insert()
    
    # Check if tool already exists
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
    
    if tool_exists:
        # Update existing tool - add missing parameters if needed
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        # Update description and function path if needed
        tool_doc.description = "Transcribe audio files to text using AI. Use this when the user uploads an audio file or asks to transcribe audio. Supports multiple providers via LiteLLM (OpenAI, Groq, Deepgram, etc.)."
        tool_doc.function_path = "huf.ai.sdk_tools.handle_transcribe_audio"
        tool_doc.tool_type = "Transcription"
        tool_doc.set("parameters", [])
        for p in parameters:
            tool_doc.append("parameters", p)
        try:
            tool_doc.save()
        except Exception as e:
            logger.warning(f"Error updating transcribe_audio tool: {e!s}")
    else:
        # Create new tool
        tool_doc = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": tool_name,
            "description": "Transcribe audio files to text using AI. Use this when the user uploads an audio file or asks to transcribe audio. Supports multiple providers via LiteLLM (OpenAI, Groq, Deepgram, etc.).",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_transcribe_audio",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "Transcription"
        })
        
        try:
            tool_doc.insert()
        except Exception as e:
            logger.warning(f"Error creating transcribe_audio tool: {e!s}")

def create_huf_roles():
	"""
	Idempotent: create the four default Huf Roles and their backing Frappe
	Roles, then ensure Administrator has the Huf Admin role.

	Safe to call on both after_install and after_migrate.
	"""
	from huf.permissions import DEFAULT_ROLE_CAPABILITIES, HUF_ROLE_FRAPPE_ROLE_MAP

	# 1. Ensure Frappe Role records exist for Huf-managed roles.
	for frappe_role_name in ["Huf Manager", "Huf User", "Huf Viewer", "Huf Gateway User"]:
		if not frappe.db.exists("Role", frappe_role_name):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": frappe_role_name,
				"desk_access": 0 if frappe_role_name == "Huf Gateway User" else 1,
			}).insert(ignore_permissions=True)


	# 2. Create (or update) the four Huf Role documents.
	role_meta = [
		{
			"role_name": "Huf Admin",
			"description": "Full system control. Can manage providers, users, roles, agents, tools, flows, and knowledge.",
			"is_system_role": 1,
			"frappe_role": "System Manager",
			"role_weight": 100,
		},
		{
			"role_name": "Huf Manager",
			"description": "Operational control. Can create and manage agents, flows, and knowledge. Cannot manage users or system settings.",
			"is_system_role": 1,
			"frappe_role": "Huf Manager",
			"role_weight": 80,
		},
		{
			"role_name": "Huf User",
			"description": "End user. Can use agents, chat, and flows. Cannot create or configure them.",
			"is_system_role": 1,
			"frappe_role": "Huf User",
			"role_weight": 50,
		},
		{
			"role_name": "Huf Viewer",
			"description": "Read-only access. Can view agents and own conversations only.",
			"is_system_role": 1,
			"frappe_role": "Huf Viewer",
			"role_weight": 10,
		},
		{
			"role_name": "Huf Gateway User",
			"description": "Service role for gateway execution users. Can run agents only; cannot create or configure anything.",
			"is_system_role": 1,
			"frappe_role": "Huf Gateway User",
			"role_weight": 5,
		},
	]

	for meta in role_meta:
		caps = DEFAULT_ROLE_CAPABILITIES.get(meta["role_name"], [])
		if not frappe.db.exists("Huf Role", meta["role_name"]):
			doc = frappe.get_doc({"doctype": "Huf Role", **meta})
			for cap in caps:
				doc.append("permissions", {"capability": cap})
			doc.insert(ignore_permissions=True)
		else:
			# Ensure capability rows are present (idempotent update).
			doc = frappe.get_doc("Huf Role", meta["role_name"])
			existing_caps = {row.capability for row in doc.permissions}
			changed = False
			for cap in caps:
				if cap not in existing_caps:
					doc.append("permissions", {"capability": cap})
					changed = True
			if doc.role_weight != meta.get("role_weight", 0):
				doc.role_weight = meta.get("role_weight", 0)
				changed = True
			if changed:
				doc.save(ignore_permissions=True)

	# 4. Ensure Administrator has the Huf Admin role.
	if not frappe.db.exists("Huf User Role", {"user": "Administrator"}):
		frappe.get_doc({
			"doctype": "Huf User Role",
			"user": "Administrator",
			"huf_role": "Huf Admin",
			"enabled": 1,
		}).insert(ignore_permissions=True)

	# 5. Migration path: assign existing System Managers to Huf Admin if they
	#    don't already have a Huf User Role record.
	_migrate_existing_system_managers()

	# 6. Every System User gets Huf's default roles (Huf Manager + Huf Gateway User), never a downgrade.
	from huf.huf.doctype.huf_user_role.huf_user_role import grant_default_roles_to_system_users

	grant_default_roles_to_system_users()

	frappe.db.commit()


def _migrate_existing_system_managers():
	"""
	One-time migration: give existing System Manager users the Huf Admin
	role so they keep access after the new check_app_permission goes live.
	"""
	system_managers = frappe.get_all(
		"Has Role",
		filters={"role": "System Manager", "parenttype": "User"},
		fields=["parent"],
		ignore_permissions=True,
	)
	for row in system_managers:
		user = row.parent
		if user in ("Administrator", "Guest"):
			continue
		if not frappe.db.exists("Huf User Role", {"user": user}):
			try:
				frappe.get_doc({
					"doctype": "Huf User Role",
					"user": user,
					"huf_role": "Huf Admin",
					"enabled": 1,
				}).insert(ignore_permissions=True)
			except Exception:
				pass  # Non-fatal; user can be assigned manually




def create_flow_tools():
    """Create the flow management tools in Agent Tool Function DocType."""
    
    # Ensure Flow Engine tool type exists
    if not frappe.db.exists("Agent Tool Type", "Workflow Tools"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "Workflow Tools"
        tool_type_doc.insert()
        
    from huf.ai.flow.tools import flow_tool_definitions
    
    for tool_def in flow_tool_definitions:
        tool_name = tool_def["tool_name"]
        
        # Check if tool already exists
        tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
        
        # Structure the parameters properly
        parameters = []
        for p in tool_def.get("parameters", []):
            parameters.append({
                "label": p.get("parameter_name", "").replace("_", " ").title(),
                "fieldname": p.get("parameter_name", ""),
                "param_type": p.get("type", "Data"),
                "required": int(p.get("required", False)),
                "description": p.get("description", "")
            })
            
        if tool_exists:
            # Update existing tool
            tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
            tool_doc.description = tool_def.get("description", "")
            tool_doc.function_path = tool_def.get("function_path", "")
            tool_doc.tool_type = "Workflow Tools"
            tool_doc.types = "Custom Function"
            tool_doc.pass_parameters_as_json = 1
            
            # Update parameters (clear existing and add new)
            tool_doc.set("parameters", [])
            for p in parameters:
                tool_doc.append("parameters", p)
            
            try:
                tool_doc.save(ignore_permissions=True)
            except Exception as e:
                logger.warning(f"Error updating {tool_name} tool: {e!s}")
        else:
            # Create new tool
            tool_doc = frappe.get_doc({
                "doctype": "Agent Tool Function",
                "tool_name": tool_name,
                "description": tool_def.get("description", ""),
                "types": "Custom Function",
                "function_path": tool_def.get("function_path", ""),
                "pass_parameters_as_json": 1,
                "parameters": parameters,
                "tool_type": "Workflow Tools"
            })
            
            try:
                tool_doc.insert(ignore_permissions=True)
            except Exception as e:
                logger.warning(f"Error creating {tool_name} tool: {e!s}")

def remove_deprecated_gemini_audio_tools():
    """Remove deprecated Gemini-native audio tools replaced by unified generate/transcribe tools."""
    deprecated_tools = ["gemini_generate_audio", "gemini_transcribe_audio"]

    for tool_name in deprecated_tools:
        tool_docname = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "name")
        if tool_docname:
            try:
                frappe.delete_doc("Agent Tool Function", tool_docname, ignore_permissions=True, force=True)
            except Exception as e:
                logger.warning(f"Error removing deprecated tool {tool_name}: {e!s}")

def _adapter_required_credentials(provider_id, extra_fields=None):
	"""Build a service's required_credentials list from its gateway adapter's own
	credential_schema, so install.py's seed can never drift from what
	Gateway._validate_required_credentials() (and the adapter itself) actually enforce.

	`extra_fields` covers credentials that are validated outside the adapter's
	credential_schema entirely (e.g. Slack's signing_secret, which is checked by
	Gateway._validate_slack_signing_secret()/slack_events.py, not SlackGatewayAdapter).
	"""
	from huf.ai.gateway_adapters.registered import get_adapter_class

	adapter_cls = get_adapter_class(provider_id)
	fields = []
	for f in adapter_cls.credential_schema.fields:
		item = {"key": f.key, "label": f.label, "required": f.required}
		if not f.secret:
			item["secret"] = False
		if f.description:
			item["description"] = f.description
		fields.append(item)
	fields.extend(extra_fields or [])
	return fields


# Credentials required outside of a gateway adapter's own credential_schema.
# Slack's signing_secret is validated by Gateway._validate_slack_signing_secret()
# (see huf/huf/doctype/gateway/gateway.py) and consumed by slack_events.py, not by
# SlackGatewayAdapter itself, so it can't be discovered from credential_schema alone.
_EXTRA_REQUIRED_CREDENTIALS = {
	# Optional: no Slack tool uses it; only needed to receive Slack events (Gateway still enforces it).
	"slack": [{
		"key": "signing_secret",
		"label": "Slack Signing Secret",
		"required": False,
		"description": "Only needed to receive Slack events",
	}],
}


def register_integration_services():
	"""
	Register built-in integration services in the Integration Service DocType.
	These services represent external APIs that agents can interact with.
	"""
	import json

	# Define all built-in services with their required credentials
	services = [
		# Communication Tools
		{
			"service_name": "slack",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Slack messaging and channel management",
			"required_credentials": _adapter_required_credentials("slack", _EXTRA_REQUIRED_CREDENTIALS["slack"])
		},

		{
			"service_name": "telegram",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Telegram bot for messaging",
			"required_credentials": _adapter_required_credentials("telegram")
		},
		{
			"service_name": "whatsapp",
			"category": "Communication",
			"surface": "Gateway",
			"description": "WhatsApp Business messaging via the Meta Cloud API",
			"required_credentials": _adapter_required_credentials("whatsapp")
		},
		{
			"service_name": "messenger",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Facebook Messenger for Page messaging",
			"required_credentials": _adapter_required_credentials("messenger")
		},
		{
			"service_name": "instagram",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Instagram Direct messaging via the Meta Graph API",
			"required_credentials": _adapter_required_credentials("instagram")
		},
		{
			"service_name": "email",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Inbound/outbound email messaging",
			"required_credentials": _adapter_required_credentials("email")
		},

		{
			"service_name": "google_chat",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Google Chat space messaging via Bearer-JWT verified HTTP endpoint",
			# GW-14: derived from GoogleChatGatewayAdapter.credential_schema
			# (huf/ai/gateway_adapters/google_chat.py), single source of truth --
			# `verification_token` (the retired body-token mechanism, see G1) is
			# intentionally gone, since no current Google Chat app configuration
			# can produce that field.
			"required_credentials": _adapter_required_credentials("google_chat")
		},
		{
			"service_name": "microsoft_teams",
			"category": "Communication",
			"surface": "Gateway",
			"description": "Microsoft Teams bot for messaging",
			"required_credentials": _adapter_required_credentials("microsoft_teams")
		},


		# Developer Tools
		{
			"service_name": "github",
			"category": "Developer",
			"surface": "Integration",
			"description": "GitHub API for repository and issue management",
			"required_credentials": [{"key": "access_token", "label": "GitHub Access Token", "required": True}]
		},

		# Google Workspace Tools
		{
			"service_name": "gmail",
			"category": "Google",
			"surface": "Integration",
			"description": "Gmail email management",
			"required_credentials": [
				{"key": "client_id", "label": "Google Client ID", "required": True},
				{"key": "client_secret", "label": "Google Client Secret", "required": True},
				{"key": "refresh_token", "label": "OAuth Refresh Token", "required": True}
			]
		},
		{
			"service_name": "google_calendar",
			"category": "Google",
			"surface": "Integration",
			"description": "Google Calendar event management",
			"required_credentials": [
				{"key": "client_id", "label": "Google Client ID", "required": True},
				{"key": "client_secret", "label": "Google Client Secret", "required": True},
				{"key": "refresh_token", "label": "OAuth Refresh Token", "required": True}
			]
		},
		{
			"service_name": "google_drive",
			"category": "Google",
			"surface": "Integration",
			"description": "Google Drive file management",
			"required_credentials": [
				{"key": "client_id", "label": "Google Client ID", "required": True},
				{"key": "client_secret", "label": "Google Client Secret", "required": True},
				{"key": "refresh_token", "label": "OAuth Refresh Token", "required": True}
			]
		},
		{
			"service_name": "google_sheets",
			"category": "Google",
			"surface": "Integration",
			"description": "Google Sheets management",
			"required_credentials": [
				{"key": "client_id", "label": "Google Client ID", "required": True},
				{"key": "client_secret", "label": "Google Client Secret", "required": True},
				{"key": "refresh_token", "label": "OAuth Refresh Token", "required": True}
			]
		},
		{
			"service_name": "google_maps",
			"category": "Google",
			"surface": "Integration",
			"description": "Google Maps directions and geocoding",
			"required_credentials": [
				{"key": "api_key", "label": "Google Maps API Key", "required": True}
			]
		},
		{
			"service_name": "google_meet",
			"category": "Google",
			"surface": "Integration",
			"description": "Google Meet meeting space creation",
			"required_credentials": [
				{"key": "client_id", "label": "Google Client ID", "required": True},
				{"key": "client_secret", "label": "Google Client Secret", "required": True},
				{"key": "refresh_token", "label": "OAuth Refresh Token", "required": True}
			]
		},
		{
			"service_name": "serpapi",
			"category": "Google",
			"surface": "Integration",
			"description": "SerpApi search data: hotels, reviews (Google Maps, TripAdvisor, Yelp), and YouTube",
			"required_credentials": [
				{"key": "api_key", "label": "SerpApi API Key", "required": True}
			]
		},
	]
	
	# Create or update each service
	for service_data in services:
		try:
			# Check if service already exists
			if frappe.db.exists("Integration Service", service_data["service_name"]):
				# Update existing service
				doc = frappe.get_doc("Integration Service", service_data["service_name"])
				doc.category = service_data["category"]
				doc.surface = service_data.get("surface", "Integration")
				doc.description = service_data["description"]
				doc.required_credentials = json.dumps(service_data["required_credentials"])
				doc.is_builtin = 1
				doc.save()
			else:
				# Create new service
				doc = frappe.get_doc({
					"doctype": "Integration Service",
					"service_name": service_data["service_name"],
					"category": service_data["category"],
					"surface": service_data.get("surface", "Integration"),
					"description": service_data["description"],
					"required_credentials": json.dumps(service_data["required_credentials"]),
					"is_builtin": 1
				})
				doc.insert()
				
		except Exception as e:
			logger.warning(f"Failed to register integration service {service_data['service_name']}: {e!s}")
			continue
	
	frappe.db.commit()


def sync_tool_types():
	"""
	Ensure that all tool type categories from the registry exist as Agent Tool Type documents.
	"""
	from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS
	
	# Extract unique categories
	categories = set()
	for tool in ALL_INTEGRATION_TOOLS:
		category = tool.get("category", "Other")
		categories.add(category)
	
	# Create or verify each category exists as Agent Tool Type
	for category in categories:
		try:
			if not frappe.db.exists("Agent Tool Type", category):
				doc = frappe.get_doc({
					"doctype": "Agent Tool Type",
					"name1": category
				})
				doc.insert()
		except Exception as e:
			logger.warning(f"Failed to create tool type {category}: {e!s}")
			continue
	
	frappe.db.commit()


# General-purpose categories for user-authored tools. Seeded alongside the
# app-integration categories from sync_tool_types(); purely additive — existing
# Agent Tool Type records are never renamed or touched.
DEFAULT_TOOL_CATEGORIES = [
	"Data Operations",
	"Integrations",
	"Automation & Workflow",
	"Communication",
	"AI & Generation",
	"Miscellaneous",
]


def sync_default_tool_categories():
	"""
	Ensure the curated general-purpose tool categories exist as Agent Tool Type
	documents. Idempotent: creates missing records only, never duplicates or
	modifies existing ones. Safe to run on every migrate.
	"""
	for category in DEFAULT_TOOL_CATEGORIES:
		try:
			if not frappe.db.exists("Agent Tool Type", category):
				doc = frappe.get_doc({
					"doctype": "Agent Tool Type",
					"name1": category
				})
				doc.insert()
		except Exception as e:
			logger.warning(f"Failed to create default tool category {category}: {e!s}")
			continue

	frappe.db.commit()


def seed_skill_categories():
	"""
	Ensure default Skill Category records exist.
	Called during after_install and after_migrate.
	"""
	categories = ["General", "CRM", "Support"]
	for category in categories:
		try:
			if not frappe.db.exists("Skill Category", category):
				doc = frappe.get_doc({
					"doctype": "Skill Category",
					"category_name": category,
				})
				doc.insert(ignore_permissions=True)
		except Exception as e:
			logger.warning(f"Failed to create skill category {category}: {e!s}")
			continue

	frappe.db.commit()


def create_memory_tools():
	"""Create or update scoped-memory Agent Tool Function records."""
	if not frappe.db.exists("Agent Tool Type", "Memory"):
		tool_type_doc = frappe.new_doc("Agent Tool Type")
		tool_type_doc.name1 = "Memory"
		tool_type_doc.insert(ignore_permissions=True)

	memory_tools = [
		(
			"save_memory_record",
			"Save a scoped memory record for future recall.",
			"huf.ai.memory_tools.handle_save_memory_record",
			"Save Memory Record",
			[
				("Title", "title", "Data", 1, "Short descriptive title for this memory."),
				("Summary Text", "summary_text", "Long Text", 1, "Detailed content of this memory."),
				("Record Type", "record_type", "Data", 0, "Fact, Preference, Research Note, Decision, Extracted Data, State, Summary, Policy Hint, Observation, Insight, or Custom."),
				("Scope Type", "scope_type", "Data", 0, "Conversation, User, Agent, Site, or Global."),
				("Scope Key", "scope_key", "Data", 0, "Scope identifier. Auto-resolved if empty."),
				("Data JSON", "data_json", "JSON", 0, "Optional structured data payload."),
				("Status", "status", "Data", 0, "Draft or Active."),
				("Visibility", "visibility", "Data", 0, "Private, Shared with Agent, Site, or Global."),
				("Tags", "tags", "Data", 0, "Comma-separated tags."),
				("Confidence", "confidence", "Float", 0, "Confidence score from 0 to 1."),
				("Importance Score", "importance_score", "Float", 0, "Importance score from 0 to 1."),
			],
		),
		(
			"search_memory_records",
			"Search saved memory records by text, type, scope, and status.",
			"huf.ai.memory_tools.handle_search_memory_records",
			"Search Memory Records",
			[
				("Query", "query", "Data", 0, "Search query."),
				("Record Type", "record_type", "Data", 0, "Optional record type filter."),
				("Scope Type", "scope_type", "Data", 0, "Optional scope type filter."),
				("Status", "status", "Data", 0, "Optional status filter. Defaults to Active."),
				("Limit", "limit", "Int", 0, "Max results, 1-50."),
			],
		),
		(
			"get_memory_record",
			"Get a specific memory record by ID.",
			"huf.ai.memory_tools.handle_get_memory_record",
			"Get Memory Record",
			[("Memory Record", "memory_record", "Data", 1, "Memory record name.")],
		),
		(
			"archive_memory_record",
			"Archive a memory record that is no longer active.",
			"huf.ai.memory_tools.handle_archive_memory_record",
			"Archive Memory Record",
			[("Memory Record", "memory_record", "Data", 1, "Memory record name.")],
		),
		(
			"promote_memory_to_knowledge",
			"Promote a memory record into a Knowledge Source for indexed retrieval.",
			"huf.ai.memory_tools.handle_promote_memory_to_knowledge",
			"Promote Memory to Knowledge",
			[
				("Memory Record", "memory_record", "Data", 1, "Memory record name."),
				("Knowledge Source", "knowledge_source", "Data", 0, "Optional Knowledge Source."),
			],
		),
	]

	for _, _, _, tool_type, _ in memory_tools:
		if not frappe.db.exists("Agent Tool Type", tool_type):
			doc = frappe.new_doc("Agent Tool Type")
			doc.name1 = tool_type
			doc.insert(ignore_permissions=True)

	for tool_name, description, function_path, tool_type, parameters in memory_tools:
		parameter_rows = [
			{
				"label": label,
				"fieldname": fieldname,
				"param_type": param_type,
				"required": required,
				"description": description,
			}
			for label, fieldname, param_type, required, description in parameters
		]
		docname = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
		tool_doc = frappe.get_doc("Agent Tool Function", docname) if docname else frappe.new_doc("Agent Tool Function")
		tool_doc.tool_name = tool_name
		tool_doc.description = description
		tool_doc.function_path = function_path
		tool_doc.types = tool_type
		tool_doc.tool_type = "Memory"
		tool_doc.pass_parameters_as_json = 1
		tool_doc.set("parameters", parameter_rows)
		if docname:
			tool_doc.save(ignore_permissions=True)
		else:
			tool_doc.insert(ignore_permissions=True)

	frappe.db.commit()


def create_code_execution_tools():
	"""Create or update the sandboxed ``run_python`` Agent Tool Function.

	The model-visible schema carries only ``code``. ``agent_doc`` is injected from
	the agent whose tools are being built, and ``conversation`` / ``agent_run`` from
	the run context (sdk_tools), so none of them are parameters here. Offer-time
	(``_allows_code_execution``) and dispatch-time (``run_python``) gates decide who
	may use it; Guest access is explicitly off. Idempotent.
	"""
	if not frappe.db.exists("Agent Tool Type", "Code Execution"):
		type_doc = frappe.new_doc("Agent Tool Type")
		type_doc.name1 = "Code Execution"
		type_doc.insert(ignore_permissions=True)

	parameter_rows = [
		{
			"label": "Code",
			"fieldname": "code",
			"type": "string",
			"required": 1,
			"description": (
				"The Python source to execute. Never persisted verbatim; only its "
				"SHA-256 digest is stored on the audit record."
			),
		},
	]

	tool_name = "run_python"
	docname = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
	tool_doc = frappe.get_doc("Agent Tool Function", docname) if docname else frappe.new_doc("Agent Tool Function")
	tool_doc.tool_name = tool_name
	tool_doc.description = (
		"Execute Python code in a sandboxed, resource-limited environment. "
		"Availability and approval flow are controlled by the calling agent's "
		"Execution Profile -- this tool may be disabled, auto-approved, or parked "
		"behind a human approval step."
	)
	tool_doc.function_path = "huf.ai.tools.code_execution.run_python"
	tool_doc.types = "Code Execution"
	tool_doc.tool_type = "Code Execution"
	tool_doc.allowed_for_guest = 0
	tool_doc.pass_parameters_as_json = 1
	tool_doc.set("parameters", parameter_rows)
	if docname:
		tool_doc.save(ignore_permissions=True)
	else:
		tool_doc.insert(ignore_permissions=True)

	frappe.db.commit()


def create_default_memory_policies():
	"""Create default Memory Policy presets."""
	presets = [
		{"policy_name": "Conservative", "description": "Nothing is captured automatically. Memory is written only via explicit tool calls and always needs human approval before it's used, so it's a safe default for agents handling sensitive or high-stakes conversations.", "scope_type": "Agent", "capture_mode": "Manual", "approval_required": 1, "default_status": "Draft", "inject_mode": "Relevant Only", "max_records": 5, "token_budget": 1500, "auto_promote_to_knowledge": 0, "allow_agent_write": 0},
		{"policy_name": "Conversational", "description": "For chat agents that should remember users across sessions with minimal friction. Every run is reviewed in the background and captured facts/preferences are injected into every future conversation automatically, no approval step.", "scope_type": "Agent", "capture_mode": "Automatic", "approval_required": 0, "default_status": "Draft", "inject_mode": "Always", "max_records": 10, "token_budget": 2000, "auto_promote_to_knowledge": 0, "allow_agent_write": 1},
		{"policy_name": "Research", "description": "For agents doing extended research or knowledge work. The agent proposes what's worth remembering after each run, retrieval is narrowed to what's relevant to the current turn, and a larger token budget supports longer-running context.", "scope_type": "Agent", "capture_mode": "Agent Suggested", "approval_required": 0, "default_status": "Active", "inject_mode": "Relevant Only", "max_records": 20, "token_budget": 4000, "auto_promote_to_knowledge": 0, "promotion_min_confidence": 0.5, "promotion_min_importance": 0.5, "allow_agent_write": 1},
		{"policy_name": "Operational", "description": "For task/ops agents where memory should stay out of the way. Nothing is captured or injected automatically — the agent can write memory via a tool call and pull it back only when it explicitly searches for it.", "scope_type": "Agent", "capture_mode": "Manual", "approval_required": 0, "default_status": "Active", "inject_mode": "Tool Only", "max_records": 10, "token_budget": 1000, "auto_promote_to_knowledge": 0, "allow_agent_write": 1},
	]
	for preset in presets:
		if frappe.db.exists("Memory Policy", preset["policy_name"]):
			continue
		try:
			doc = frappe.new_doc("Memory Policy")
			doc.update(preset)
			doc.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(
				title="Memory Policy Creation",
				message=f"Error creating memory policy {preset['policy_name']}: {str(e)}",
			)

	frappe.db.commit()


def create_default_execution_profiles():
	"""Create default Execution Profile presets shipped with Huf."""
	profiles = [
		{
			"profile_name": "Restricted",
			"approval_mode": "Ask Every Time",
			"is_builtin": 1,
			"filesystem_policy": "Scratch Only",
			"max_wall_time_s": 30,
			"max_cpu_seconds": 30,
			"max_memory_mb": 256,
			"max_output_bytes": 1048576,
		},
		{
			"profile_name": "Trusted",
			"approval_mode": "Auto Approve",
			"is_builtin": 1,
			"filesystem_policy": "Scratch Only",
			"max_wall_time_s": 60,
			"max_cpu_seconds": 60,
			"max_memory_mb": 512,
			"max_output_bytes": 2097152,
		},
		{
			# The profile an "Execute code" Flow step starts with: runs on its own (nobody has to
			# approve each run), a private scratch folder, no network, small fixed limits.
			"profile_name": "Flow Scratch",
			"approval_mode": "Auto Approve",
			"is_builtin": 1,
			"filesystem_policy": "Scratch Only",
			"max_wall_time_s": 30,
			"max_cpu_seconds": 30,
			"max_memory_mb": 256,
			"max_output_bytes": 262144,
		},
		{
			"profile_name": "Blocked",
			"approval_mode": "Never Allow",
			"is_builtin": 1,
			"filesystem_policy": "None",
			"max_wall_time_s": 5,
			"max_cpu_seconds": 5,
			"max_memory_mb": 128,
			"max_output_bytes": 65536,
		},
	]
	for profile in profiles:
		if frappe.db.exists("Execution Profile", profile["profile_name"]):
			continue
		try:
			doc = frappe.new_doc("Execution Profile")
			doc.update(profile)
			doc.insert(ignore_permissions=True)
		except Exception as e:
			logger.warning(
				f"Failed to create default execution profile {profile['profile_name']}: {e!s}"
			)

	frappe.db.commit()
