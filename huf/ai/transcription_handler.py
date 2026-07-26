# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Legacy provider-specific speech-to-text dispatcher.

This module is retained for backward compatibility of imports only. All
audio transcription logic has moved to the canonical audio service
(``huf.ai.audio_service``) and the public API (``huf.ai.audio_api``).

Do not add new code here. Use ``audio_service.transcribe_audio_file`` or
``huf.ai.sdk_tools.handle_transcribe_audio`` instead.
"""

import warnings

import frappe


def execute_provider_capability(
    provider: str,
    capability_method: str,
    *args,
    **kwargs
) -> dict:
    """
    Deprecated. Provider-specific capability dispatch has been replaced by
    the unified audio service.
    """
    warnings.warn(
        "transcription_handler.execute_provider_capability is deprecated. "
        "Use huf.ai.audio_service.transcribe_audio_file instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return {
        "success": False,
        "error": (
            "Provider-specific transcription settings are deprecated. "
            "Configure an AI Provider with an API key and use "
            "huf.ai.audio_api.transcribe or the transcribe_audio agent tool."
        ),
    }


def handle_speech_to_text(
    file_id: str = None,
    file_url: str = None,
    language: str = None,
    translate: bool = False,
    provider: str = None,
    api_key: str = None,
    conversation: str = None,
    reference_doctype: str = None,
    document_id: str = None,
    message_id: str = None,
    **kwargs
):
    """
    Deprecated. Use ``huf.ai.audio_service.transcribe_audio_file`` or the
    ``huf.ai.audio_api.transcribe`` whitelisted API instead.
    """
    warnings.warn(
        "transcription_handler.handle_speech_to_text is deprecated. "
        "Use huf.ai.audio_service.transcribe_audio_file instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return {
        "success": False,
        "error": (
            "handle_speech_to_text is deprecated. "
            "Use huf.ai.audio_api.transcribe or the transcribe_audio agent tool."
        ),
    }
