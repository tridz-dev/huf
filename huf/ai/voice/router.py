"""
Voice Agent Router

Routes voice agent requests to the appropriate provider implementation,
similar to RunProvider for text-based agents.
"""

import frappe
from frappe import _
from typing import Dict, Any, Optional
from huf.ai.voice.base import VoiceAgentBase


class VoiceAgentRouter:
    """
    Central routing layer for voice agent providers.
    
    Routes requests to appropriate provider implementations (ElevenLabs, Gemini, etc.)
    while maintaining backward compatibility.
    """

    @staticmethod
    def get_provider(provider_name: str, agent_name: str) -> VoiceAgentBase:
        """
        Get voice agent provider instance.
        
        Args:
            provider_name: Name of the AI Provider DocType
            agent_name: Name of the Agent DocType
            
        Returns:
            VoiceAgentBase instance for the provider
        """
        provider_lower = provider_name.lower()
        
        # Map provider names to implementation modules
        provider_map = {
            "elevenlabs": "huf.ai.voice.providers.elevenlabs",
            "gemini": "huf.ai.voice.providers.gemini",
            "google": "huf.ai.voice.providers.gemini",  # Gemini is Google's voice API
            "openai": "huf.ai.voice.providers.openai",
        }
        
        # Try to get provider module
        module_path = provider_map.get(provider_lower)
        
        if not module_path:
            # Try to auto-detect from provider name
            try:
                module_path = f"huf.ai.voice.providers.{provider_lower}"
                module = frappe.get_module(module_path)
            except ImportError:
                frappe.throw(
                    _(
                        f"Voice agent provider '{provider_name}' not found. "
                        f"Supported providers: {', '.join(provider_map.keys())}"
                    )
                )
        else:
            module = frappe.get_module(module_path)
        
        # Get provider class (should be named VoiceAgent)
        if not hasattr(module, "VoiceAgent"):
            frappe.throw(
                _(
                    f"Provider module {module_path} is missing VoiceAgent class"
                )
            )
        
        VoiceAgentClass = getattr(module, "VoiceAgent")
        
        # Instantiate and return
        return VoiceAgentClass(provider_name, agent_name)

    @staticmethod
    def get_signed_url(provider_name: str, agent_name: str, **kwargs) -> Dict[str, Any]:
        """
        Get signed URL for voice conversation.
        
        Args:
            provider_name: Name of the AI Provider DocType
            agent_name: Name of the Agent DocType
            **kwargs: Provider-specific parameters
            
        Returns:
            Dictionary with connection information
        """
        provider = VoiceAgentRouter.get_provider(provider_name, agent_name)
        return provider.get_signed_url(**kwargs)

    @staticmethod
    def handle_webhook(
        provider_name: str,
        agent_name: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Handle webhook from voice provider.
        
        Args:
            provider_name: Name of the AI Provider DocType
            agent_name: Optional agent name (may be inferred from webhook data)
            request_data: Parsed request body (may include type, data, event_timestamp for ElevenLabs)
            headers: Request headers
            
        Returns:
            Dictionary with status and data
        """
        request = frappe.request
        
        # Use provided data or get from request
        if request_data is None:
            try:
                request_data = request.get_json() or {}
            except Exception:
                request_data = {}
        
        if headers is None:
            headers = dict(request.headers)
        
        # Handle ElevenLabs webhook format (type, data, event_timestamp)
        # Extract actual webhook data if wrapped
        webhook_type = request_data.get("type")
        webhook_data = request_data.get("data", request_data)
        
        # If agent_name not provided, try to infer from provider settings
        if not agent_name:
            agent_name = frappe.db.get_value(
                "Agent", {"provider": provider_name}, "name"
            )
            if not agent_name:
                frappe.throw(
                    f"No agent found for provider '{provider_name}'",
                    frappe.ValidationError
                )
        
        provider = VoiceAgentRouter.get_provider(provider_name, agent_name)
        
        # Pass webhook data in format expected by provider
        # ElevenLabs expects: {type, data, ...}
        # Other providers may expect just the data dict
        return provider.handle_webhook(webhook_data, headers)
