"""
ElevenLabs ConvAI API Integration

This module provides backward-compatible endpoints for ElevenLabs voice agents.
It now uses the unified VoiceAgentRouter abstraction layer while maintaining
full backward compatibility with existing implementations.
"""

import frappe
import requests
from huf.ai.voice.router import VoiceAgentRouter

SETTINGS_DOCTYPE = "Elevenlabs Settings"


def _get_settings():
    """
    Fetch ElevenLabs credentials from Single Settings DocType.
    Maintained for backward compatibility.
    """
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        frappe.throw(f"{SETTINGS_DOCTYPE} DocType not found", frappe.ValidationError)

    settings = frappe.get_single(SETTINGS_DOCTYPE)
    provider = frappe.get_doc("AI Provider", settings.provider)
    api_key = provider.get_password("api_key")
    agent_id = settings.agent_id

    return agent_id, api_key


@frappe.whitelist(allow_guest=True)
def health():
    """Health check endpoint for ElevenLabs configuration."""
    agent_id, api_key = _get_settings()

    return {
        "status": "ok",
        "settings": {
            "hasAgentId": bool(agent_id),
            "hasApiKey": bool(api_key),
            "agentIdLength": len(agent_id) if agent_id else 0,
            "apiKeyLength": len(api_key) if api_key else 0,
        },
    }


@frappe.whitelist(allow_guest=True)
def get_signed_url():
    """
    Get signed URL for ElevenLabs conversation.
    
    Now uses VoiceAgentRouter for unified provider handling.
    Maintains backward compatibility.
    """
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    provider_name = settings.provider
    
    # Get agent name from settings or find by provider
    agent_name = None
    if hasattr(settings, 'agent') and settings.agent:
        agent_name = settings.agent
    else:
        agent_name = frappe.db.get_value("Agent", {"provider": provider_name}, "name")
    
    if not agent_name:
        frappe.throw("No agent found for ElevenLabs provider", frappe.ValidationError)
    
    # Use router to get signed URL
    return VoiceAgentRouter.get_signed_url(provider_name, agent_name)


@frappe.whitelist(allow_guest=True)
def get_agent_id():
    """Get ElevenLabs agent ID from settings."""
    agent_id, _ = _get_settings()
    return {"agentId": agent_id}


@frappe.whitelist(allow_guest=True)
def handle_elevenlabs_webhook(type=None, data=None, event_timestamp=None):
    """
    Handles ElevenLabs Post Call Transcription.
    
    Now uses VoiceAgentRouter for unified provider handling.
    Maintains backward compatibility with existing webhook format.
    """
    request = frappe.request
    
    # Get provider from settings
    el_settings = frappe.get_single("Elevenlabs Settings")
    provider_name = el_settings.provider
    
    # Prepare webhook data in expected format
    webhook_data = {
        "type": type,
        "data": data,
        "event_timestamp": event_timestamp
    }
    
    # Get agent name
    agent_name = frappe.db.get_value("Agent", {"provider": provider_name}, "name")
    
    if not agent_name:
        frappe.log_error(
            "No Huf Agent found with provider 'ElevenLabs'",
            "Huf Webhook"
        )
        return {"status": "error", "message": "Internal Agent not found"}
    
    # Use router to handle webhook
    return VoiceAgentRouter.handle_webhook(
        provider_name=provider_name,
        agent_name=agent_name,
        request_data=webhook_data,
        headers=dict(request.headers)
    )
