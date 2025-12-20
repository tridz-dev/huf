# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for Huf app
"""

import frappe


def after_install():
    create_demo_ai_providers()
    create_demo_ai_models()
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
	try:
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

