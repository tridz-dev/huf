"""
Base Abstract Class for Voice Agents

Defines the interface that all voice agent providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, AsyncGenerator, Any
import frappe


class VoiceAgentBase(ABC):
    """
    Abstract base class for voice agent providers.
    
    All voice agent implementations (ElevenLabs, Gemini, OpenAI, etc.) must
    inherit from this class and implement all abstract methods.
    """

    def __init__(self, provider_name: str, agent_name: str):
        """
        Initialize voice agent.
        
        Args:
            provider_name: Name of the AI Provider DocType
            agent_name: Name of the Agent DocType
        """
        self.provider_name = provider_name
        self.agent_name = agent_name
        self._validate_config()

    def _validate_config(self):
        """Validate that provider and agent exist and are configured."""
        if not frappe.db.exists("AI Provider", self.provider_name):
            frappe.throw(f"AI Provider '{self.provider_name}' not found")
        
        if not frappe.db.exists("Agent", self.agent_name):
            frappe.throw(f"Agent '{self.agent_name}' not found")

    @abstractmethod
    def get_signed_url(self, **kwargs) -> Dict[str, Any]:
        """
        Get a signed URL or connection endpoint for initiating a voice conversation.
        
        Returns:
            Dictionary containing connection information (e.g., signed_url, ws_url, etc.)
        """
        pass

    @abstractmethod
    def handle_webhook(self, request_data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Handle webhook callbacks from the voice provider.
        
        Args:
            request_data: Parsed request body data
            headers: Request headers for validation
            
        Returns:
            Dictionary with status and any relevant data
        """
        pass

    @abstractmethod
    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """
        Validate webhook signature for security.
        
        Args:
            payload: Raw request body bytes
            signature: Signature from headers
            secret: Secret key for validation
            
        Returns:
            True if signature is valid, False otherwise
        """
        pass

    @abstractmethod
    async def stream_realtime(
        self,
        audio_input: AsyncGenerator[bytes, None],
        session_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream real-time audio for bidirectional voice conversation.
        
        Args:
            audio_input: Async generator yielding audio chunks (bytes)
            session_config: Optional session configuration (language, transcription mode, etc.)
            
        Yields:
            Dictionary with event type and data (e.g., {'type': 'audio.delta', 'audio': base64_string})
        """
        pass

    def get_provider_settings(self) -> Dict[str, Any]:
        """
        Get provider-specific settings from DocType.
        
        Returns:
            Dictionary with provider settings
        """
        provider = frappe.get_doc("AI Provider", self.provider_name)
        api_key = provider.get_password("api_key")
        
        return {
            "api_key": api_key,
            "provider_name": getattr(provider, "provide_name", None) or provider.name,
        }

    def get_agent_config(self) -> Dict[str, Any]:
        """
        Get agent configuration.
        
        Returns:
            Dictionary with agent settings
        """
        agent = frappe.get_doc("Agent", self.agent_name)
        model = frappe.get_doc("AI Model", agent.model) if agent.model else None
        
        return {
            "agent_name": agent.name,
            "instructions": agent.instructions,
            "model": model.model_name if model else None,
            "provider": agent.provider,
        }
