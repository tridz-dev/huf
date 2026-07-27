# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for Huf app
"""

import json

import frappe
from huf.utils import is_frappe_16

logger = frappe.logger("huf")

def setup_desktop_icon_as_workspace(app_name):
	"""
	Replace the External App desktop icon with a Workspace Sidebar icon.
	Runs after Frappe creates desktop icons, so we fix the Huf icon to use Workspace Sidebar.
	Only applies on Frappe version 16 and above.
	"""
	if not is_frappe_16() or app_name != "huf":
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
		doc.link_type = "Workspace Sidebar"
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
			icon.link_type = "Workspace Sidebar"
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
    create_image_generation_tool()
    create_transcribe_audio_tool()
    create_generate_audio_tool()
    remove_deprecated_gemini_audio_tools()
    create_ocr_document_tool()
    create_flow_tools()
    create_memory_tools()
    create_default_memory_policies()
    create_default_execution_profiles()
    register_integration_services()
    sync_tool_types()
    sync_default_tool_categories()
    seed_skill_categories()
    from huf.ai.tool_registry import sync_discovered_tools
    sync_discovered_tools(use_cache=False)
    frappe.db.commit()
    """
	Called after app installation.
	Checks if litellm is installed and provides helpful message if not.
	"""
    try:
        import litellm
        from importlib.metadata import version as get_installed_version

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


def after_migrate():
	"""
	Called after app migration.
	Syncs all discovered tools from all installed apps.
	"""
	create_huf_roles()
	setup_desktop_icon_as_workspace("huf")
	try:
		create_image_generation_tool()
		create_transcribe_audio_tool()
		create_generate_audio_tool()
		remove_deprecated_gemini_audio_tools()
		create_ocr_document_tool()
		create_flow_tools()
		create_memory_tools()
		create_default_memory_policies()
		create_default_execution_profiles()
		register_integration_services()
		sync_tool_types()
		sync_default_tool_categories()
		seed_skill_categories()
		from huf.ai.tool_registry import sync_discovered_tools
		result = sync_discovered_tools(use_cache=False)  # Full scan (apps_to_scan=None)
		logger.info(
			f"Synced tools after migrate: {result.get('total_tools', 0)} tools from {len(result.get('synced_apps', []))} apps"
		)
	except Exception as e:
		logger.warning(f"Failed to sync tools after migrate: {e!s}")
		
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
        # {"doctype": "AI Provider", "provider_name": "xAI", "provider_brand": "xai", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Mistral", "provider_brand": "mistral", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Alibaba", "provider_brand": "alibaba", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "DashScope", "provider_brand": "alibaba", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Meta", "provider_brand": "meta", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "TogetherAI", "provider_brand": "togetherai", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Azure OpenAI", "provider_brand": "azure", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "AWS Bedrock", "provider_brand": "amazon-bedrock", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Ollama", "provider_brand": "ollama", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "ElevenLabs", "provider_brand": "elevenlabs", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Groq", "provider_brand": "groq", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "DeepSeek", "provider_brand": "deepseek", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Huggingface", "provider_brand": "huggingface", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Cohere", "provider_brand": "cohere", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Perplexity", "provider_brand": "perplexity", "api_key": ""},
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
    models = [
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-chat-v3-0324", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-v3", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-r1-0528", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-v2.5-1210", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-vl2", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-vl", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-coder-v5.7b-mqa-base", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-v3.1-terminus", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-r1-zero", "provider": "DeepSeek"},
        # {"doctype": "AI Model", "model_name": "deepseek/deepseek-chat-v3-lite", "provider": "DeepSeek"},
        {"doctype": "AI Model", "model_name": "huggingface/meta-llama/Llama-3.2-3B-Instruct", "provider": "Huggingface"},
        {"doctype": "AI Model", "model_name": "command-a-03-2025", "provider": "Cohere"},
        {"doctype": "AI Model", "model_name": "sonar-pro", "provider": "Perplexity"},
        {"doctype": "AI Model", "model_name": "sonar", "provider": "Perplexity"},
        {"doctype": "AI Model", "model_name": "sonar-reasoning", "provider": "Perplexity"},
        {"doctype": "AI Model", "model_name": "sonar-reasoning-pro", "provider": "Perplexity"},
        {"doctype": "AI Model", "model_name": "sonar-deep-research", "provider": "Perplexity"},
        {"doctype": "AI Model", "model_name": "gemini-3.5-flash", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-3.1-pro-preview", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-3.1-flash-lite", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-3-flash-preview", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.5-pro", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.5-flash", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.5-flash-lite", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemma-3-27b-it", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemma-3-9b-it", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "nano-banana-pro", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-3.1-flash-image", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "text-embedding-004", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-embedding-001", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-embedding-2", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "claude-fable-5", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-opus-4.8", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-sonnet-5", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-haiku-4.5", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "openai/gpt-5", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-5-mini", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-5-nano", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-4o-mini", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemini-2.5-flash", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemini-2.5-flash-lite-preview-06-17", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemma-3-27b-it", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "deepseek/deepseek-v4-pro", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "deepseek/deepseek-v4-flash", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "deepseek/deepseek-chat-v3-0324", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "deepseek/deepseek-chat-v3.1", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "z-ai/glm-5.2", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "moonshotai/kimi-k3", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "moonshotai/kimi-k2.7", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "minimax/minimax-m3", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "minimax/minimax-m2.7", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "minimax/minimax-m2", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "microsoft/phi-4", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemma-4-31b-it", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "qwen/qwen3.7-max", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "qwen/qwen3.6-plus", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "qwen/qwen3-vl-235b-a22b-instruct", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "qwen/qwen3-coder", "provider": "OpenRouter"},
        # OpenRouter free-tier variants (verified live 2026-07; model_name keeps the
        # exact ":free" id — that suffix IS the free label and the working route)
        {"doctype": "AI Model", "model_name": "google/gemma-4-31b-it:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemma-4-26b-a4b-it:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-oss-20b:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-3-super-120b-a12b:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-3-ultra-550b-a55b:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-3-nano-30b-a3b:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-nano-12b-v2-vl:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-nano-9b-v2:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "nvidia/nemotron-3.5-content-safety:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "cohere/north-mini-code:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "poolside/laguna-m.1:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "poolside/laguna-xs-2.1:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "tencent/hy3:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "gpt-5.6-sol", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.6-terra", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.6-luna", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.5", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.4", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.4-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.4-nano", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.2", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "whisper-1", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-3-small", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-3-large", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-ada-002", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-image-2", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "Alternate", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4o-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5.1", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5-nano", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-5", "provider": "OpenAI"},
    ]

    for m in models:
        if not frappe.db.exists("AI Model", m["model_name"]):
            doc = frappe.get_doc(m)
            doc.flags.ignore_mandatory = True
            doc.flags.ignore_validate = True
            doc.insert(ignore_permissions=True)

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
            "description": "Number of images to generate. Default: 1. Note: dall-e-3 only supports n=1."
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
            "description": "Optional transcription model. Defaults based on provider: OpenAI/Groq use 'whisper-1', Groq can use 'groq/whisper-large-v3', Deepgram uses 'deepgram/nova-2'."
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
	for frappe_role_name in ["Huf Manager", "Huf User", "Huf Viewer"]:
		if not frappe.db.exists("Role", frappe_role_name):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": frappe_role_name,
				"desk_access": 1,
			}).insert(ignore_permissions=True)


	# 2. Create (or update) the four Huf Role documents.
	role_meta = [
		{
			"role_name": "Huf Admin",
			"description": "Full system control. Can manage providers, users, roles, agents, tools, flows, and knowledge.",
			"is_system_role": 1,
			"frappe_role": "System Manager",
		},
		{
			"role_name": "Huf Manager",
			"description": "Operational control. Can create and manage agents, flows, and knowledge. Cannot manage users or system settings.",
			"is_system_role": 1,
			"frappe_role": "Huf Manager",
		},
		{
			"role_name": "Huf User",
			"description": "End user. Can use agents, chat, and flows. Cannot create or configure them.",
			"is_system_role": 1,
			"frappe_role": "Huf User",
		},
		{
			"role_name": "Huf Viewer",
			"description": "Read-only access. Can view agents and own conversations only.",
			"is_system_role": 1,
			"frappe_role": "Huf Viewer",
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
        
    from huf.ai.flow_tools import flow_tool_definitions
    
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
			"description": "Slack messaging and channel management",
			"required_credentials": [{"key": "token", "label": "Slack Bot Token", "required": True}]
		},
		{
			"service_name": "discord",
			"category": "Communication",
			"description": "Discord bot for messaging and channel management",
			"required_credentials": [{"key": "bot_token", "label": "Discord Bot Token", "required": True}]
		},
		{
			"service_name": "telegram",
			"category": "Communication",
			"description": "Telegram bot for messaging",
			"required_credentials": [{"key": "token", "label": "Telegram Bot Token", "required": True}]
		},
		
		# Developer Tools
		{
			"service_name": "github",
			"category": "Developer",
			"description": "GitHub API for repository and issue management",
			"required_credentials": [{"key": "access_token", "label": "GitHub Access Token", "required": True}]
		},
		
		# Project Management Tools
		{
			"service_name": "jira",
			"category": "Project Management",
			"description": "Jira issue tracking and project management",
			"required_credentials": [
				{"key": "server_url", "label": "Jira Server URL", "required": True},
				{"key": "username", "label": "Username", "required": True},
				{"key": "token", "label": "API Token", "required": True}
			]
		},
		
		# Google Workspace Tools
		{
			"service_name": "gmail",
			"category": "Google",
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
			"description": "Google Maps directions and geocoding",
			"required_credentials": [
				{"key": "api_key", "label": "Google Maps API Key", "required": True}
			]
		},
		{
			"service_name": "google_meet",
			"category": "Google",
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


def create_default_memory_policies():
	"""Create default Memory Policy presets."""
	presets = [
		{"policy_name": "Conservative", "scope_type": "Agent", "capture_mode": "Manual", "approval_required": 1, "default_status": "Draft", "inject_mode": "Relevant Only", "max_records": 5, "token_budget": 1500, "auto_promote_to_knowledge": 0, "allow_agent_write": 0},
		{"policy_name": "Conversational", "scope_type": "Agent", "capture_mode": "Automatic", "approval_required": 0, "default_status": "Draft", "inject_mode": "Always", "max_records": 10, "token_budget": 2000, "auto_promote_to_knowledge": 0, "allow_agent_write": 1},
		{"policy_name": "Research", "scope_type": "Agent", "capture_mode": "Agent Suggested", "approval_required": 0, "default_status": "Active", "inject_mode": "Relevant Only", "max_records": 20, "token_budget": 4000, "auto_promote_to_knowledge": 0, "promotion_min_confidence": 0.5, "promotion_min_importance": 0.5, "allow_agent_write": 1},
		{"policy_name": "Operational", "scope_type": "Agent", "capture_mode": "Manual", "approval_required": 0, "default_status": "Active", "inject_mode": "Tool Only", "max_records": 10, "token_budget": 1000, "auto_promote_to_knowledge": 0, "allow_agent_write": 1},
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
				f"Error creating memory policy {preset['policy_name']}: {str(e)}",
				"Memory Policy Creation",
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

