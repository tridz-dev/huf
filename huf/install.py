# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for Huf app
"""

import frappe
from huf.utils import is_frappe_16

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
    create_demo_ai_providers()
    create_demo_ai_models()
    create_image_generation_tool()
    create_transcribe_audio_tool()
    create_generate_audio_tool()
    remove_deprecated_gemini_audio_tools()
    create_ocr_document_tool()
    create_flow_tools()
    register_integration_services()
    sync_tool_types()
    from huf.ai.tool_registry import sync_discovered_tools
    sync_discovered_tools(use_cache=False)
    frappe.db.commit()
    """
	Called after app installation.
	Checks if litellm is installed and provides helpful message if not.
	"""
    try:
        import litellm
        frappe.msgprint("✅ LiteLLM is installed and ready to use.")
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
	setup_desktop_icon_as_workspace("huf")
	try:
		create_image_generation_tool()
		create_transcribe_audio_tool()
		create_generate_audio_tool()
		remove_deprecated_gemini_audio_tools()
		create_ocr_document_tool()
		create_flow_tools()
		from huf.ai.tool_registry import sync_discovered_tools
		result = sync_discovered_tools()  # Full scan (apps_to_scan=None)
		frappe.log_error(
			f"Synced tools after migrate: {result.get('total_tools', 0)} tools from {len(result.get('synced_apps', []))} apps",
			"Tool Sync"
		)
	except Exception as e:
		frappe.log_error(
			f"Failed to sync tools after migrate: {str(e)}",
			"Tool Sync Error"
		)

def create_demo_ai_providers():
    providers = [
        # {"doctype": "AI Provider", "provider_name": "xAI", "slug": "xai", "chef": "xAI", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Mistral", "slug": "mistral", "chef": "Mistral", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Alibaba", "slug": "alibaba", "chef": "Alibaba", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "DashScope", "slug": "dashscope", "chef": "Alibaba", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Meta", "slug": "meta", "chef": "Meta", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "TogetherAI", "slug": "togetherai", "chef": "TogetherAI", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Azure OpenAI", "slug": "azure", "chef": "Microsoft", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "AWS Bedrock", "slug": "bedrock", "chef": "Amazon", "api_key": ""},
        # {"doctype": "AI Provider", "provider_name": "Ollama", "slug": "ollama", "chef": "Ollama", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "ElevenLabs", "slug": "elevenlabs", "chef": "ElevenLabs", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Groq", "slug": "groq", "chef": "xAI", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "DeepSeek", "slug": "deepseek", "chef": "DeepSeek", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Huggingface", "slug": "huggingface", "chef": "HuggingFace", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Cohere", "slug": "cohere", "chef": "Cohere", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Perplexity", "slug": "perplexity", "chef": "Perplexity", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Google", "slug": "google", "chef": "Google", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "Anthropic", "slug": "anthropic", "chef": "Anthropic", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "OpenRouter", "slug": "openrouter", "chef": "OpenRouter", "api_key": ""},
        {"doctype": "AI Provider", "provider_name": "OpenAI", "slug": "openai", "chef": "OpenAI", "api_key": ""},
        
        
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
        {"doctype": "AI Model", "model_name": "gemini-3-pro-preview", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.5-pro", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.5-flash", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.5-flash-lite", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemma-3-27b-it", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemma-3-9b-it", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "nano-banana-pro", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "text-embedding-004", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.0-flash-001", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "gemini-2.0-flash-lite-preview", "provider": "Google"},
        {"doctype": "AI Model", "model_name": "claude-sonnet-4.5", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-opus-4", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-opus-4.1", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-haiku-4.5", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-3.7-sonnet", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-3.5-sonnet", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-3.5-haiku", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-opus-4.5", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-2", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "claude-sonnet-4-20250514", "provider": "Anthropic"},
        {"doctype": "AI Model", "model_name": "openai/gpt-5", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-5-mini", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-5-nano", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-4.1-mini", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-4.1-nano", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "openai/gpt-4o-mini", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemini-2.5-flash", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemini-2.5-flash-lite-preview-06-17", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemini-2.0-flash-exp:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemma-3-27b-it:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "anthropic/claude-4.5-sonnet-20250929", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "deepseek/deepseek-chat-v3-0324", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "deepseek/deepseek-chat-v3.1", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "qwen/qwen3-vl-235b-a22b-instruct", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "qwen/qwen3-coder:free", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "minimax/minimax-m2", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "o1-preview", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "o1-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "whisper-1", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-3-small", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-3-large", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-ada-002", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-image-1", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "Alternate", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "dall-e-3", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4.1", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-3.5-turbo", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4.1-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4.1-nano", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4o", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4o-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4-turbo", "provider": "OpenAI"},
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
        frappe.log_error(f"Error creating image generation tool: {str(e)}", "Image Generation Tool Creation")


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
        tool_doc.description = "Extract text from documents and images using OCR. Supports PDFs, images, and scanned documents. Uses vision models for images and OCR for multi-page documents."
        tool_doc.function_path = "huf.ai.sdk_tools.handle_ocr_document"
        tool_doc.tool_type = "OCR"
        try:
            tool_doc.save()
        except Exception as e:
            frappe.log_error(f"Error updating ocr_document tool: {str(e)}", "OCR Document Tool Update")
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
            "description": "Extract text from documents and images using OCR. Supports PDFs, images, and scanned documents. Uses vision models for images and OCR for multi-page documents.",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_ocr_document",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "OCR"
        })
        
        try:
            tool_doc.insert()
        except Exception as e:
            frappe.log_error(f"Error creating ocr_document tool: {str(e)}", "OCR Document Tool Creation")

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
            frappe.log_error(f"Error updating generate_audio tool: {str(e)}", "Generate Audio Tool Update")
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
            frappe.log_error(f"Error creating generate_audio tool: {str(e)}", "Generate Audio Tool Creation")

def create_transcribe_audio_tool():
    """Create or update the transcribe_audio tool in Agent Tool Function DocType."""
    tool_name = "transcribe_audio"
    
    # Ensure Transcription tool type exists
    if not frappe.db.exists("Agent Tool Type", "Transcription"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "Transcription"
        tool_type_doc.insert()
    
    # Check if tool already exists
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
    
    if tool_exists:
        # Update existing tool
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        # Update description and function path if needed
        tool_doc.description = "Transcribe audio files to text using AI. Use this when the user uploads an audio file or asks to transcribe audio. Supports multiple providers via LiteLLM (OpenAI, Groq, Deepgram, etc.)."
        tool_doc.function_path = "huf.ai.sdk_tools.handle_transcribe_audio"
        tool_doc.tool_type = "Transcription"
        try:
            tool_doc.save()
        except Exception as e:
            frappe.log_error(f"Error updating transcribe_audio tool: {str(e)}", "Transcribe Audio Tool Update")
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
                "description": "File URL/path (alternative to file_id). Example: /files/audio.mp3"
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
            frappe.log_error(f"Error creating transcribe_audio tool: {str(e)}", "Transcribe Audio Tool Creation")

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
                frappe.log_error(f"Error updating {tool_name} tool: {str(e)}", "Flow Tool Update")
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
                frappe.log_error(f"Error creating {tool_name} tool: {str(e)}", "Flow Tool Creation")



def remove_deprecated_gemini_audio_tools():
    """Remove deprecated Gemini-native audio tools replaced by unified generate/transcribe tools."""
    deprecated_tools = ["gemini_generate_audio", "gemini_transcribe_audio"]

    for tool_name in deprecated_tools:
        tool_docname = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "name")
        if tool_docname:
            try:
                frappe.delete_doc("Agent Tool Function", tool_docname, ignore_permissions=True, force=True)
            except Exception as e:
                frappe.log_error(
                    f"Error removing deprecated tool {tool_name}: {str(e)}",
                    "Deprecated Tool Cleanup"
                )


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
			frappe.log_error(f"Failed to register integration service {service_data['service_name']}: {e}")
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
			frappe.log_error(f"Failed to create tool type {category}: {e}")
			continue
	
	frappe.db.commit()
