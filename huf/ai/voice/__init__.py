"""
Voice Agent Abstraction Layer

Provides a unified interface for voice agent providers (ElevenLabs, Gemini, OpenAI, etc.)
while maintaining backward compatibility with existing implementations.
"""

from huf.ai.voice.router import VoiceAgentRouter

__all__ = ["VoiceAgentRouter"]
