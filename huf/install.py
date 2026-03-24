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
    """
    Called after app installation.
    """
    create_huf_roles()
    create_demo_ai_providers()
    create_demo_ai_models()
    create_image_generation_tool()
    create_transcribe_audio_tool()
    create_generate_audio_tool()
    create_ocr_document_tool()
    create_flow_tools()
    create_odoo_tools()
    create_odoo_agents()
    frappe.db.commit()

    try:
        import litellm
        frappe.msgprint("✅ LiteLLM is installed and ready to use.")
    except ImportError:
        frappe.msgprint(
            "⚠️ LiteLLM package not found. "
            "Please run 'bench setup requirements' to install dependencies, "
            "then restart your site with 'bench restart'.",
            indicator="orange",
            title="Dependency Missing",
        )

    try:
        from huf.ai.knowledge.backends.sqlite_vec_backend import check_sqlite_vec_available
        if check_sqlite_vec_available():
            frappe.msgprint("✅ sqlite_vec (vector search) is ready.")
        else:
            frappe.msgprint(
                "⚠️ sqlite_vec (vector search) is not available. Install pysqlite3-binary: pip install pysqlite3-binary. Use sqlite_fts for keyword search.",
                indicator="orange",
                title="Vector Search",
            )
    except Exception:
        pass


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
        create_ocr_document_tool()
        create_flow_tools()
        create_odoo_tools()
        create_odoo_agents()
        from huf.ai.tool_registry import sync_discovered_tools
        result = sync_discovered_tools()
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
        {"doctype": "AI Model", "model_name": "openai/gpt-4o-mini", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "google/gemini-2.5-flash", "provider": "OpenRouter"},
        {"doctype": "AI Model", "model_name": "o1-preview", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "o1-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "whisper-1", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-3-small", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "text-embedding-3-large", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4o", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4o-mini", "provider": "OpenAI"},
        {"doctype": "AI Model", "model_name": "gpt-4-turbo", "provider": "OpenAI"},
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
    if frappe.db.exists("Agent Tool Function", {"tool_name": tool_name}):
        return
    if not frappe.db.exists("Agent Tool Type","Generation"):
        tool_type_doc=frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1="Generation"
        tool_type_doc.insert(ignore_permissions=True)
    
    parameters = [
        {"label": "Prompt", "fieldname": "prompt", "type": "string", "required": 1, "description": "Text description of image."},
        {"label": "Size", "fieldname": "size", "type": "string", "required": 0, "description": "Image dimensions.", "options": "auto"},
        {"label": "Quality", "fieldname": "quality", "type": "string", "required": 0, "description": "Image quality.", "options": "auto"},
        {"label": "Number of Images", "fieldname": "n", "type": "integer", "required": 0, "description": "Number of images."},
        {"label": "Response Format", "fieldname": "response_format", "type": "string", "required": 0, "description": "Response format.", "options": "url\nb64_json"}
    ]
    
    tool_doc = frappe.get_doc({
        "doctype": "Agent Tool Function",
        "tool_name": tool_name,
        "description": "Generate an image from a text description using AI.",
        "types": "Custom Function",
        "function_path": "huf.ai.sdk_tools.handle_generate_image",
        "pass_parameters_as_json": 1,
        "parameters": parameters,
        "tool_type": "Generation"
    })
    try:
        tool_doc.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Error creating image generation tool: {str(e)}", "Image Generation Tool Creation")


def create_ocr_document_tool():
    """Create or update the ocr_document tool."""
    tool_name = "ocr_document"
    if not frappe.db.exists("Agent Tool Type", "OCR"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "OCR"
        tool_type_doc.insert(ignore_permissions=True)
    
    parameters = [
        {"label": "File ID", "fieldname": "file_id", "type": "string", "required": 0, "description": "Frappe File ID."},
        {"label": "File URL", "fieldname": "file_url", "type": "string", "required": 0, "description": "File URL."},
        {"label": "Pages", "fieldname": "pages", "type": "string", "required": 0, "description": "Pages (e.g., '0,1')."},
        {"label": "Include Images", "fieldname": "include_images", "type": "boolean", "required": 0, "description": "Extract images."},
        {"label": "Model", "fieldname": "model", "type": "string", "required": 0, "description": "OCR model override."}
    ]
    
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
    if tool_exists:
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        tool_doc.set("parameters", [])
        for p in parameters: tool_doc.append("parameters", p)
        tool_doc.save(ignore_permissions=True)
    else:
        tool_doc = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": tool_name,
            "description": "Extract text from documents and images using OCR.",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_ocr_document",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "OCR"
        })
        tool_doc.insert(ignore_permissions=True)

def create_odoo_agents():
    """Seed pre-built Odoo Agents."""
    from huf.ai.odoo.agents_seed import create_odoo_agents as seed_agents
    seed_agents()

def create_generate_audio_tool():
    """Create or update the generate_audio tool."""
    tool_name = "generate_audio"
    if not frappe.db.exists("Agent Tool Type", "Audio Generation"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "Audio Generation"
        tool_type_doc.insert(ignore_permissions=True)
    
    parameters = [
        {"label": "Input Text", "fieldname": "input", "type": "string", "required": 1, "description": "Text to convert to speech."},
        {"label": "Voice", "fieldname": "voice", "type": "string", "required": 0, "description": "Voice identifier."},
        {"label": "Model", "fieldname": "model", "type": "string", "required": 0, "description": "TTS model override."},
        {"label": "Speed", "fieldname": "speed", "type": "number", "required": 0, "description": "Speed (0.25 to 4.0)."},
        {"label": "Response Format", "fieldname": "response_format", "type": "string", "required": 0, "description": "Audio format.", "options": "mp3\nopus\naac\nflac\nwav\npcm"}
    ]
    
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
    if tool_exists:
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        tool_doc.set("parameters", [])
        for p in parameters: tool_doc.append("parameters", p)
        tool_doc.save(ignore_permissions=True)
    else:
        tool_doc = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": tool_name,
            "description": "Generate audio (speech) from text using AI text-to-speech.",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_generate_audio",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "Audio Generation"
        })
        tool_doc.insert(ignore_permissions=True)

def create_transcribe_audio_tool():
    """Create or update the transcribe_audio tool."""
    tool_name = "transcribe_audio"
    if not frappe.db.exists("Agent Tool Type", "Transcription"):
        tool_type_doc = frappe.new_doc("Agent Tool Type")
        tool_type_doc.name1 = "Transcription"
        tool_type_doc.insert(ignore_permissions=True)
    
    parameters = [
        {"label": "File ID", "fieldname": "file_id", "type": "string", "required": 0, "description": "Frappe File ID."},
        {"label": "File URL", "fieldname": "file_url", "type": "string", "required": 0, "description": "File URL."},
        {"label": "Language", "fieldname": "language", "type": "string", "required": 0, "description": "ISO 639-1 code."},
        {"label": "Model", "fieldname": "model", "type": "string", "required": 0, "description": "Transcription model."}
    ]
    
    tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
    if tool_exists:
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        tool_doc.set("parameters", [])
        for p in parameters: tool_doc.append("parameters", p)
        tool_doc.save(ignore_permissions=True)
    else:
        tool_doc = frappe.get_doc({
            "doctype": "Agent Tool Function",
            "tool_name": tool_name,
            "description": "Transcribe audio files to text using AI.",
            "types": "Custom Function",
            "function_path": "huf.ai.sdk_tools.handle_transcribe_audio",
            "pass_parameters_as_json": 1,
            "parameters": parameters,
            "tool_type": "Transcription"
        })
        tool_doc.insert(ignore_permissions=True)

def create_huf_roles():
	"""Ensures Huf roles exist."""
	for r in ["Huf Manager", "Huf User", "Huf Viewer"]:
		if not frappe.db.exists("Role", r):
			frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 1}).insert(ignore_permissions=True)

def create_flow_tools():
    """Create flow management tools."""
    if not frappe.db.exists("Agent Tool Type", "Workflow Tools"):
        frappe.get_doc({"doctype": "Agent Tool Type", "name1": "Workflow Tools"}).insert(ignore_permissions=True)
        
    from huf.ai.flow_tools import flow_tool_definitions
    for tool_def in flow_tool_definitions:
        tool_name = tool_def["tool_name"]
        tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
        
        params = []
        for p in tool_def.get("parameters", []):
            params.append({
                "label": p.get("parameter_name", "").replace("_", " ").title(),
                "fieldname": p.get("parameter_name", ""),
                "param_type": p.get("type", "Data"),
                "required": int(p.get("required", False)),
                "description": p.get("description", "")
            })
            
        if tool_exists:
            tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
            tool_doc.set("parameters", [])
            for p in params: tool_doc.append("parameters", p)
            tool_doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({
                "doctype": "Agent Tool Function",
                "tool_name": tool_name,
                "description": tool_def.get("description", ""),
                "types": "Custom Function",
                "function_path": tool_def.get("function_path", ""),
                "pass_parameters_as_json": 1,
                "parameters": params,
                "tool_type": "Workflow Tools"
            }).insert(ignore_permissions=True)

def create_odoo_tools():
    """Create or update the Odoo integration tools."""
    if not frappe.db.exists("Agent Tool Type", "Odoo Integration"):
        frappe.get_doc({"doctype": "Agent Tool Type", "name1": "Odoo Integration"}).insert(ignore_permissions=True)
    
    tools = [
        {
            "tool_name": "odoo_search_read",
            "description": "Search and read records from an Odoo ERP model.",
            "types": "Odoo Search Read",
            "parameters": [
                {"parameter_name": "model", "type": "Data", "required": 1, "description": "Odoo model name (e.g., res.partner)"},
                {"parameter_name": "domain", "type": "Code", "required": 0, "description": "JSON domain filter"},
                {"parameter_name": "fields", "type": "Data", "required": 0, "description": "Comma-separated fields"},
                {"parameter_name": "limit", "type": "Int", "required": 0, "description": "Max records (max 100)"},
                {"parameter_name": "offset", "type": "Int", "required": 0, "description": "Records to skip"},
                {"parameter_name": "order", "type": "Data", "required": 0, "description": "Sort order"}
            ]
        },
        {
            "tool_name": "odoo_read",
            "description": "Read specific records from Odoo.",
            "types": "Odoo Read",
            "parameters": [
                {"parameter_name": "model", "type": "Data", "required": 1},
                {"parameter_name": "ids", "type": "Data", "required": 1},
                {"parameter_name": "fields", "type": "Data", "required": 0}
            ]
        },
        {
            "tool_name": "odoo_create",
            "description": "Create a new record in Odoo.",
            "types": "Odoo Create",
            "parameters": [
                {"parameter_name": "model", "type": "Data", "required": 1},
                {"parameter_name": "values", "type": "JSON", "required": 1}
            ]
        },
        {
            "tool_name": "odoo_write",
            "description": "Update existing records in Odoo.",
            "types": "Odoo Write",
            "parameters": [
                {"parameter_name": "model", "type": "Data", "required": 1},
                {"parameter_name": "ids", "type": "Data", "required": 1},
                {"parameter_name": "values", "type": "JSON", "required": 1}
            ]
        },
        {
            "tool_name": "odoo_unlink",
            "description": "Delete records from Odoo.",
            "types": "Odoo Delete",
            "parameters": [
                {"parameter_name": "model", "type": "Data", "required": 1},
                {"parameter_name": "ids", "type": "Data", "required": 1}
            ]
        },
        {
            "tool_name": "odoo_execute",
            "description": "Execute a specific ORM method on Odoo records.",
            "types": "Odoo Execute",
            "parameters": [
                {"parameter_name": "model", "type": "Data", "required": 1},
                {"parameter_name": "method", "type": "Data", "required": 1},
                {"parameter_name": "ids", "type": "Data", "required": 0},
                {"parameter_name": "args", "type": "JSON", "required": 0}
            ]
        },
        {
            "tool_name": "odoo_fields_get",
            "description": "Get field metadata for an Odoo model.",
            "types": "Odoo Fields Get",
            "parameters": [{"parameter_name": "model", "type": "Data", "required": 1}]
        },
        {
            "tool_name": "odoo_list_models",
            "description": "List all available models in Odoo.",
            "types": "Odoo List Models",
            "parameters": []
        }
    ]
    
    for tool_def in tools:
        tool_name = tool_def["tool_name"]
        tool_exists = frappe.db.exists("Agent Tool Function", {"tool_name": tool_name})
        
        params = []
        for p in tool_def.get("parameters", []):
            params.append({
                "label": p.get("parameter_name", "").replace("_", " ").title(),
                "fieldname": p.get("parameter_name", ""),
                "param_type": p.get("type", "Data"),
                "required": int(p.get("required", False)),
                "description": p.get("description", "")
            })

        if tool_exists:
            tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
            tool_doc.set("parameters", [])
            for p in params: tool_doc.append("parameters", p)
            tool_doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({
                "doctype": "Agent Tool Function",
                "tool_name": tool_name,
                "description": tool_def["description"],
                "types": tool_def["types"],
                "pass_parameters_as_json": 1,
                "parameters": params,
                "tool_type": "Odoo Integration"
            }).insert(ignore_permissions=True)
