# Voice Agent Abstraction Layer

A unified abstraction layer for voice agent providers (ElevenLabs, Gemini, OpenAI, etc.) that maintains backward compatibility while enabling easy addition of new providers.

## Architecture

The abstraction layer consists of:

1. **Base Class** (`base.py`): `VoiceAgentBase` - Abstract interface that all providers must implement
2. **Router** (`router.py`): `VoiceAgentRouter` - Routes requests to appropriate provider implementations
3. **Providers** (`providers/`): Provider-specific implementations

## Supported Providers

- **ElevenLabs**: Full implementation with webhook support
- **Gemini**: WebSocket-based real-time streaming via LiteLLM
- **OpenAI**: Placeholder for future implementation

## Usage

### Getting a Signed URL / Connection Info

```python
from huf.ai.voice.router import VoiceAgentRouter

# Get connection info for voice conversation
connection_info = VoiceAgentRouter.get_signed_url(
    provider_name="ElevenLabs",
    agent_name="My Voice Agent"
)

# For ElevenLabs: returns {"signedUrl": "..."}
# For Gemini: returns {"ws_url": "...", "headers": {...}, ...}
```

### Handling Webhooks

```python
from huf.ai.voice.router import VoiceAgentRouter

# Handle webhook callback
result = VoiceAgentRouter.handle_webhook(
    provider_name="ElevenLabs",
    agent_name="My Voice Agent",  # Optional, will be inferred if not provided
    request_data=webhook_payload,
    headers=request_headers
)
```

### Real-time Streaming (Gemini/OpenAI)

```python
import asyncio
from huf.ai.voice.router import VoiceAgentRouter

async def stream_audio():
    provider = VoiceAgentRouter.get_provider("Gemini", "My Voice Agent")
    
    async def audio_generator():
        # Yield audio chunks
        yield audio_chunk_1
        yield audio_chunk_2
    
    async for event in provider.stream_realtime(
        audio_input=audio_generator(),
        session_config={
            "language": "en-US",
            "transcription_mode": "fast"
        }
    ):
        if event["type"] == "audio.delta":
            # Handle audio output
            play_audio(event["delta"])
        elif event["type"] == "transcript.delta":
            # Handle transcript
            print(event["delta"])
```

## Adding a New Provider

1. Create a new file in `huf/ai/voice/providers/` (e.g., `myprovider.py`)

2. Implement the `VoiceAgent` class inheriting from `VoiceAgentBase`:

```python
from huf.ai.voice.base import VoiceAgentBase
from typing import Dict, Any, Optional, AsyncGenerator

class VoiceAgent(VoiceAgentBase):
    def get_signed_url(self, **kwargs) -> Dict[str, Any]:
        # Return connection info
        pass
    
    def validate_webhook_signature(self, payload, signature, secret) -> bool:
        # Validate webhook signatures
        pass
    
    def handle_webhook(self, request_data, headers) -> Dict[str, Any]:
        # Handle webhook callbacks
        pass
    
    async def stream_realtime(self, audio_input, session_config=None):
        # Stream real-time audio (if supported)
        pass
```

3. Add provider mapping to `router.py`:

```python
provider_map = {
    "myprovider": "huf.ai.voice.providers.myprovider",
    # ...
}
```

## Backward Compatibility

The existing ElevenLabs endpoints (`huf/ai/providers/elevenlabs_convai_api.py`) have been updated to use the router while maintaining full backward compatibility. All existing API calls will continue to work without changes.

## Provider-Specific Notes

### ElevenLabs

- Uses signed URLs and webhooks (not direct WebSocket)
- Requires `Elevenlabs Settings` DocType configuration
- Webhook format: `{type: "post_call_transcription", data: {...}}`

### Gemini

- Uses WebSocket via LiteLLM proxy
- Requires `LITELLM_PROXY_URL` environment variable or site config
- Supports real-time bidirectional streaming
- Model format: `google/gemini-2.0-flash` or `gemini-2.0-flash`

### OpenAI

- Placeholder for future implementation
- Will use OpenAI Realtime API WebSocket
