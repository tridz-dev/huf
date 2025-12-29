"""
Gemini Voice Agent Provider

Implements VoiceAgentBase for Google Gemini Realtime API via LiteLLM.
Supports WebSocket-based real-time bidirectional voice conversations.
"""

import asyncio
import json
import base64
import websockets
from typing import Dict, Any, Optional, AsyncGenerator
import frappe
from huf.ai.voice.base import VoiceAgentBase
from huf.ai.conversation_manager import ConversationManager


class VoiceAgent(VoiceAgentBase):
    """Gemini voice agent implementation using LiteLLM Realtime API."""

    def __init__(self, provider_name: str, agent_name: str):
        super().__init__(provider_name, agent_name)
        self._litellm_proxy_url = None
        self._setup_proxy_url()

    def _setup_proxy_url(self):
        """Setup LiteLLM proxy URL from environment or settings."""
        # Try to get from environment variable or settings
        import os
        proxy_url = os.getenv("LITELLM_PROXY_URL") or frappe.conf.get("litellm_proxy_url")
        
        if not proxy_url:
            frappe.throw(
                "LiteLLM proxy URL not configured. "
                "Set LITELLM_PROXY_URL environment variable or litellm_proxy_url in site config."
            )
        
        # Ensure URL doesn't have trailing slash
        self._litellm_proxy_url = proxy_url.rstrip("/")

    def get_signed_url(self, **kwargs) -> Dict[str, Any]:
        """
        Get WebSocket URL for Gemini Realtime API.
        
        Args:
            model: Optional model name (defaults to agent's model)
            
        Returns:
            Dictionary with ws_url and connection info
        """
        agent_config = self.get_agent_config()
        provider_settings = self.get_provider_settings()
        
        model = kwargs.get("model") or agent_config.get("model") or "gemini-2.0-flash"
        
        # Normalize model name for LiteLLM
        if not model.startswith("google/"):
            model = f"google/{model}"
        
        # Construct WebSocket URL
        ws_url = f"{self._litellm_proxy_url}/v1/realtime?model={model}"
        
        # Use wss:// for secure connections if proxy URL uses https://
        if ws_url.startswith("http://"):
            ws_url = ws_url.replace("http://", "ws://", 1)
        elif ws_url.startswith("https://"):
            ws_url = ws_url.replace("https://", "wss://", 1)
        
        return {
            "ws_url": ws_url,
            "model": model,
            "api_key": provider_settings.get("api_key"),
            "headers": {
                "Authorization": f"Bearer {provider_settings.get('api_key')}",
                "OpenAI-Beta": "realtime=v1"
            }
        }

    def validate_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """
        Validate webhook signature (if Gemini supports webhooks).
        
        Note: Gemini Realtime API primarily uses WebSocket connections,
        so webhook validation may not be applicable.
        """
        # Gemini Realtime API uses WebSocket, not webhooks
        # This is a placeholder for future webhook support
        return True

    def handle_webhook(
        self, request_data: Dict[str, Any], headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Handle webhook (if Gemini supports webhooks).
        
        Note: Gemini Realtime API primarily uses WebSocket connections.
        This method is a placeholder for future webhook support.
        """
        # Gemini Realtime API uses WebSocket, not webhooks
        return {"status": "ignored", "message": "Gemini uses WebSocket, not webhooks"}

    async def stream_realtime(
        self,
        audio_input: AsyncGenerator[bytes, None],
        session_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream real-time audio for bidirectional Gemini conversation.
        
        Args:
            audio_input: Async generator yielding audio chunks (bytes)
            session_config: Optional session configuration:
                - language: Language code (default: "en-US")
                - transcription_mode: "fast" or "accurate" (default: "fast")
                - modalities: List of modalities (default: ["text"])
                - conversation_id: Optional conversation ID
                
        Yields:
            Dictionary with event type and data:
                - {'type': 'response.audio.delta', 'delta': base64_audio}
                - {'type': 'response.audio_transcript.delta', 'delta': text}
                - {'type': 'response.done', ...}
                - {'type': 'error', 'error': ...}
        """
        connection_info = self.get_signed_url()
        ws_url = connection_info["ws_url"]
        headers = connection_info["headers"]
        
        # Default session config
        config = session_config or {}
        language = config.get("language", "en-US")
        transcription_mode = config.get("transcription_mode", "fast")
        modalities = config.get("modalities", ["text"])
        conversation_id = config.get("conversation_id", "default")
        
        try:
            async with websockets.connect(
                ws_url,
                additional_headers=headers
            ) as ws:
                # Send session update
                session_update = {
                    "type": "session.update",
                    "session": {
                        "conversation_id": conversation_id,
                        "language": language,
                        "transcription_mode": transcription_mode,
                        "modalities": modalities
                    }
                }
                await ws.send(json.dumps(session_update))
                
                # Start listening for responses in background
                async def listen_for_responses():
                    try:
                        while True:
                            response = await ws.recv()
                            message_json = json.loads(response)
                            
                            # Yield different event types
                            if message_json.get("type") == "response.audio.delta":
                                yield {
                                    "type": "audio.delta",
                                    "delta": message_json.get("delta"),
                                    "full_response": message_json.get("full_response")
                                }
                            elif message_json.get("type") == "response.audio_transcript.delta":
                                yield {
                                    "type": "transcript.delta",
                                    "delta": message_json.get("delta"),
                                    "full_transcript": message_json.get("full_transcript")
                                }
                            elif message_json.get("type") == "response.done":
                                yield {
                                    "type": "done",
                                    "data": message_json
                                }
                                break
                            elif message_json.get("type") == "error":
                                yield {
                                    "type": "error",
                                    "error": message_json.get("error")
                                }
                                break
                    except Exception as e:
                        yield {
                            "type": "error",
                            "error": str(e)
                        }
                
                # Process audio input and stream responses concurrently
                async def send_audio():
                    try:
                        async for audio_chunk in audio_input:
                            # Encode audio chunk to base64
                            base64_audio = base64.b64encode(audio_chunk).decode('utf-8')
                            
                            audio_message = {
                                "type": "input_audio_buffer.append",
                                "audio": base64_audio
                            }
                            await ws.send(json.dumps(audio_message))
                            
                            # Small delay to simulate real-time streaming
                            await asyncio.sleep(0.1)
                        
                        # Send end of audio stream
                        await ws.send(json.dumps({"type": "input_audio_buffer.end"}))
                    except Exception as e:
                        yield {
                            "type": "error",
                            "error": f"Audio send error: {str(e)}"
                        }
                
                # Run both tasks concurrently
                async for event in listen_for_responses():
                    yield event
                    
        except Exception as e:
            yield {
                "type": "error",
                "error": f"WebSocket connection error: {str(e)}"
            }

    async def process_voice_call(
        self,
        audio_file_path: Optional[str] = None,
        audio_stream: Optional[AsyncGenerator[bytes, None]] = None,
        session_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a complete voice call and return conversation results.
        
        This is a convenience method that handles the full conversation flow,
        including conversation management and message storage.
        
        Args:
            audio_file_path: Path to audio file (WAV format)
            audio_stream: Alternative: async generator of audio chunks
            session_config: Session configuration
            
        Returns:
            Dictionary with conversation_id, messages, and status
        """
        agent_config = self.get_agent_config()
        provider_settings = self.get_provider_settings()
        
        # Create conversation
        cm = ConversationManager(
            agent_name=self.agent_name,
            channel="gemini_voice",
            external_id=session_config.get("conversation_id") if session_config else None
        )
        
        conversation = cm.get_or_create_conversation(
            title=f"Voice Call: {self.agent_name}"
        )
        
        # Prepare audio input
        if audio_file_path:
            import wave
            async def audio_generator():
                with wave.open(audio_file_path, 'rb') as wav_file:
                    chunk_size = 1024
                    while True:
                        chunk = wav_file.readframes(chunk_size)
                        if not chunk:
                            break
                        yield chunk
                        await asyncio.sleep(0.1)
            audio_input = audio_generator()
        elif audio_stream:
            audio_input = audio_stream
        else:
            frappe.throw("Either audio_file_path or audio_stream must be provided")
        
        # Stream conversation
        messages = []
        full_transcript = ""
        
        async for event in self.stream_realtime(audio_input, session_config):
            if event["type"] == "transcript.delta":
                full_transcript += event.get("delta", "")
            elif event["type"] == "done":
                # Save final transcript as agent message
                if full_transcript:
                    cm.add_message(
                        conversation=conversation,
                        role="agent",
                        content=full_transcript,
                        provider=provider_settings.get("provider_name"),
                        model=agent_config.get("model"),
                        agent=self.agent_name,
                    )
                break
            elif event["type"] == "error":
                frappe.log_error(
                    f"Gemini voice error: {event.get('error')}",
                    "Gemini Voice Error"
                )
                break
        
        frappe.db.commit()
        
        return {
            "conversation_id": conversation.name,
            "transcript": full_transcript,
            "status": "success"
        }
