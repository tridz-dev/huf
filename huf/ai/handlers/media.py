import asyncio
import base64

import frappe
from frappe.utils.file_manager import save_file
try:
    from requests.exceptions import RequestException
except ImportError:
    class RequestException(Exception):
        pass

from huf.ai import audio_service
from huf.ai.transaction import commit_if_background

logger = frappe.logger("huf")


def _get_default_image_model(provider_name: str) -> str:
    """
    Get default image generation model for a provider.

    Based on LiteLLM documentation: https://docs.litellm.ai/docs/image_generation

    Args:
        provider_name: Lowercase provider name (e.g., "openai", "azure", "google")

    Returns:
        str: Default image model name, or None if not supported
    """
    defaults = {
        "openai": "dall-e-3",
        "azure": "dall-e-3",  # Azure uses same models with azure/ prefix
        "openrouter": "dall-e-3",  # OpenRouter can route to OpenAI models
        "google": "google/gemini-2.5-flash-image",
        "vertex_ai": "vertex_ai/imagegeneration@006",
        "bedrock": "bedrock/stability.stable-diffusion-xl-v0",
        "recraft": "recraft/recraftv3",
    }

    return defaults.get(provider_name.lower())


@frappe.whitelist()
async def handle_generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    n: int = 1,
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Generate an image using the agent's configured provider and image generation model.

    Uses LiteLLM's image_generation() function. The model used is either:
    1. The agent's explicitly configured image_generation_model field, OR
    2. An auto-detected suitable image model based on the provider

    Args:
        prompt: Text description of the image to generate
        size: Image size (1024x1024, 1792x1024, 1024x1792, etc.)
        quality: Image quality (standard, hd, high, medium, low)
        n: Number of images to generate (1-10)
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context

    Returns:
        dict: {
            "success": bool,
            "images": [{"url": str, "file_id": str}],
            "message": str
        }
    """
    try:
        # Get agent configuration from context
        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}

        agent_doc = frappe.get_doc("Agent", agent_name)
        provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
        api_key = provider_doc.get_password("api_key")

        if not api_key:
            return {"success": False, "error": "API key not configured for provider"}

        # Determine image generation model
        image_model = None

        if hasattr(agent_doc, "image_generation_model") and agent_doc.image_generation_model:
            # Use explicitly configured image model
            model_doc = frappe.get_doc("AI Model", agent_doc.image_generation_model)
            image_model = model_doc.model_name
        else:
            # Auto-detect suitable image model based on provider
            provider_name = provider_doc.provider_name.lower()
            image_model = _get_default_image_model(provider_name)

        if not image_model:
            return {
                "success": False,
                "error": f"Image generation not supported for provider '{provider_doc.provider_name}'. Please configure an image_generation_model in agent settings."
            }

        # Normalize to LiteLLM format
        from huf.ai.providers.litellm import _normalize_model_name
        normalized_model = _normalize_model_name(image_model, agent_doc.provider)

        # Call LiteLLM image generation
        import litellm
        litellm.drop_params = True

        response = await asyncio.to_thread(
            litellm.image_generation,
            prompt=prompt,
            model=normalized_model,
            n=n,
            size=size,
            quality=quality,
            api_key=api_key
        )

        # Get conversation_index once if conversation_id exists
        # Each Agent Message needs a unique, sequential conversation_index to maintain order.
        conversation_index = None
        if conversation_id:
            try:
                last_index = frappe.db.sql("""
                    SELECT MAX(conversation_index) as last_index
                    FROM `tabAgent Message`
                    WHERE conversation = %s
                """, (conversation_id,), as_dict=1)

                conversation_index = (last_index[0].last_index if last_index and last_index[0].last_index is not None else 0) + 1
            except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError):
                # Hard failure: message ordering is required; abort and alert admin.
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Failed to compute conversation_index for {conversation_id}"
                )
                frappe.throw(
                    "Could not determine message order for this conversation. Please retry.",
                    title="Message Ordering Error"
                )

        # Process response and save images
        images = []
        if hasattr(response, 'data') and response.data:
            for idx, image_data in enumerate(response.data):
                # Get image URL or base64
                image_url = None
                image_b64 = None

                # Handle Pydantic model / Object access
                if hasattr(image_data, 'url'):
                    image_url = image_data.url
                if hasattr(image_data, 'b64_json'):
                    image_b64 = image_data.b64_json

                # Handle Dictionary access (if not an object)
                if not image_url and not image_b64 and isinstance(image_data, dict):
                    image_url = image_data.get('url')
                    image_b64 = image_data.get('b64_json')

                if not image_url and not image_b64:
                    continue

                # Download and save image
                image_bytes = None
                filename = f"generated_image_{idx + 1}.png"

                if image_url and image_url.startswith('http'):
                    # Download from URL (with SSRF protection)
                    from huf.ai.http_handler import _http_request
                    try:
                        img_response = _http_request("GET", image_url, timeout=30)
                        img_response.raise_for_status()
                        image_bytes = img_response.content
                    except (ValueError, RequestException) as e:
                        frappe.logger("huf").warning(
                            f"Image download failed for URL {image_url}: {e}"
                        )
                        continue
                elif image_b64:
                    # Base64 encoded
                    image_bytes = base64.b64decode(image_b64)
                elif image_url:
                    # Unexpected image URL format; retain Error Log for investigation.
                    frappe.log_error(f"Unsupported image URL format: {image_url}", "Image Generation")
                    continue

                if not image_bytes:
                    continue

                # Create Agent Message first (we'll attach the file to it)
                message_doc = None
                if conversation_id and conversation_index is not None:
                    if frappe.has_permission("Agent Message", "create"):
                        try:
                            # Get provider and model from agent
                            provider = agent_doc.provider
                            model = agent_doc.model

                            # Create Agent Message with kind "Image" first (without image)
                            message_doc = frappe.get_doc({
                                "doctype": "Agent Message",
                                "conversation": conversation_id,
                                "role": "agent",
                                "content": f"Generated image: {prompt}",
                                "kind": "Image",
                                "agent": agent_name,
                                "provider": provider,
                                "model": model,  # Link to AI Model
                                "agent_run": kwargs.get("agent_run_id"),
                                "conversation_index": conversation_index + idx,  # Increment for each image
                                "is_agent_message": 1,
                                "user": "Agent"
                            })
                            message_doc.insert()
                        except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
                            logger.warning(f"Create image message failed: {e!s}")
                            # Continue even if message creation fails
                    else:
                        frappe.logger("huf").warning(
                            f"User {frappe.session.user} does not have permission to create Agent Message; attaching image to conversation instead."
                        )

                # Save file attached to the Agent Message (or conversation if message creation failed)
                if message_doc:
                    saved_file = save_file(
                        filename,
                        image_bytes,
                        "Agent Message",
                        message_doc.name,
                        is_private=False,
                        df="generated_image"
                    )
                else:
                    # Fallback: attach to conversation if message creation failed
                    saved_file = save_file(
                        filename,
                        image_bytes,
                        "Agent Conversation",
                        conversation_id or "Unknown",
                        is_private=False
                    )

                # save_file returns a File document object
                file_url = getattr(saved_file, 'file_url', None)
                file_id = getattr(saved_file, 'name', None)

                # Ensure we have a file_url
                if not file_url:
                    file_url = f"/files/{getattr(saved_file, 'file_name', filename)}"

                # Update the message with the file URL if message was created
                # This ensures the Attach Image field displays the image correctly
                if message_doc and file_url:
                    message_doc.db_set("generated_image", file_url)
                    commit_if_background()

                    # Emit socket event for new agent message (Image)
                    try:
                        frappe.publish_realtime(
                            event=f'conversation:{conversation_id}',
                            message={
                                "type": "new_agent_message",
                                "conversation_id": conversation_id,
                                "message_id": message_doc.name,
                                "kind": "Image",
                                "content": message_doc.content,
                                "generated_image": file_url,
                                "agent_run_id": kwargs.get("agent_run_id"),
                                "conversation_index": message_doc.conversation_index,
                            },
                            user=frappe.session.user,
                            after_commit=False
                        )
                    except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
                        frappe.logger("huf").debug(
                            f"Error emitting new_agent_message socket event: {e!s}"
                        )

                images.append({
                    "url": file_url or f"/files/{filename}",
                    "file_id": file_id
                })

        # Update conversation total_messages once after all images are created
        if conversation_id and conversation_index is not None and images:
            try:
                final_index = conversation_index + len(images) - 1
                frappe.db.sql("""
                    UPDATE `tabAgent Conversation`
                    SET total_messages = %s, last_activity = NOW()
                    WHERE name = %s
                """, (final_index, conversation_id))
            except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
                frappe.logger("huf").debug(
                    f"Error updating conversation total_messages: {e!s}"
                )

        if not images:
            return {
                "success": False,
                "error": "Image generation succeeded but no images were returned"
            }

        return {
            "success": True,
            "images": images,
            "message": f"Generated {len(images)} image(s) successfully"
        }

    except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
        # Hard provider/tool failure: retain Error Log for admin attention.
        frappe.log_error(f"Image generation error: {e!s}", "Image Generation Tool")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
async def handle_ocr_document(
    file_id: str = None,
    file_url: str = None,
    pages: str = None,
    include_images: bool = False,
    model: str = None,
    agent_name: str = None,
    conversation_id: str = None,
    create_message: bool = True,
    **kwargs
):
    """
    Extract text from documents and images using OCR / document parsing.

    Supports any common document or image format:
    - PDFs: LiteLLM OCR endpoint, local PDF extraction, or vision models (provider dependent)
    - Images (jpg, png, webp, gif, etc.): vision models
    - Office/text documents (docx, txt, md, html, csv, json, etc.): local extractors

    Args:
        file_id: File document ID (preferred and most reliable)
        file_url: File URL/path (alternative; supports /files/ and /private/files/)
        pages: Comma-separated page numbers (e.g., "0,1,2") - PDFs only
        include_images: Extract embedded images as base64 - PDFs with OCR endpoint only
        model: Optional OCR/vision model override
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context

    Returns:
        dict: {
            "success": bool,
            "text": str,              # Extracted text in markdown
            "pages": list,            # Page-by-page breakdown
            "strategy": str,          # "ocr", "vision", "local", "local_pdf"
            "file_id": str,
            "file_name": str,
            "file_hash": str,         # SHA-256 of processed file (for verification)
            "message_id": str,
            "model": str,
            "error": str
        }
    """
    try:
        from huf.ai.ocr_engine import extract_document

        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}

        agent_doc = frappe.get_doc("Agent", agent_name)

        result = await extract_document(
            agent_doc=agent_doc,
            file_id=file_id,
            file_url=file_url,
            pages=pages,
            include_images=bool(include_images),
            model=model,
            create_message=create_message,
            conversation_id=conversation_id,
            agent_run_id=kwargs.get("agent_run_id"),
        )

        return result.as_dict()

    except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
        # Hard OCR failure: retain Error Log for admin attention.
        frappe.log_error(f"OCR error: {e!s}", "OCR Tool")
        return {"success": False, "error": str(e)}


def _get_default_voice(provider_name: str) -> str:
    """Get default voice for a provider."""
    defaults = {
        "openai": "alloy",
        "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
        "google": "Puck",
        "vertex_ai": "Puck",
        "gemini": "Puck",
        "azure": "en-US-JennyNeural",
        "mistral": "mistral-male-1"
    }
    return defaults.get(provider_name.lower(), "alloy")


def _get_default_tts_model(provider_name: str) -> str:
    """
    Get default TTS model for a provider.

    Based on LiteLLM documentation: https://docs.litellm.ai/docs/audio_speech

    Args:
        provider_name: Lowercase provider name (e.g., "openai", "google", "elevenlabs")

    Returns:
        str: Default TTS model name, or None if not supported
    """
    defaults = {
        "openai": "tts-1",
        "azure": "tts-1",
        "google": "gemini/gemini-2.5-flash-preview-tts",
        "gemini": "gemini/gemini-2.5-flash-preview-tts",
        "vertex_ai": "vertex_ai/gemini-2.5-flash-preview-tts",
        "elevenlabs": "elevenlabs/eleven_multilingual_v2",
        "aws": "aws/polly",
        "minimax": "minimax/speech-01",
    }

    return defaults.get(provider_name.lower())


def _resolve_tts_config(
    agent_doc,
    tool_model: str | None = None,
    tool_voice: str | None = None,
) -> dict:
    """
    Resolve the TTS model, voice, API key, and provider for audio generation.

    Priority (highest → lowest):

    1. **Tool-call parameter** - ``model`` / ``voice`` values passed by the
       agent at runtime (highest precedence; lets individual calls override).
    2. **Agent-level TTS configuration** - ``agent.tts_model`` / ``agent.tts_voice``
       fields set on the Agent DocType.  The API key is fetched from the *TTS
       model's own provider* (``AI Model → AI Provider``), which may be a
       completely different provider from the agent's main conversational model.
    3. **Provider default** - ``_get_default_tts_model`` / ``_get_default_voice``
       derived from the agent's main provider (fallback when nothing else is set).

    Args:
        agent_doc:   Loaded ``Agent`` Frappe document.
        tool_model:  Optional model name supplied by the tool call at runtime.
        tool_voice:  Optional voice name supplied by the tool call at runtime.

    Returns:
        dict:
            - ``tts_model``     - Normalised LiteLLM model string.
            - ``voice``         - Voice identifier for the TTS provider.
            - ``api_key``       - Decrypted API key for the TTS provider.
            - ``provider_name`` - Lowercase provider name (used for env-var routing).
            - ``provider_doc``  - Loaded ``AI Provider`` document for the TTS provider.
            - ``source``        - How the model was resolved: ``"tool_param"``,
                                  ``"agent_config"``, or ``"provider_default"``.

    Raises:
        ValueError: If no TTS model can be determined and the provider does not
                    natively support TTS.
    """
    from huf.ai.providers.litellm import _normalize_model_name

    if tool_model:
        provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
        api_key = provider_doc.get_password("api_key")
        if not api_key:
            raise ValueError(
                f"API key is not configured for provider "
                f"'{provider_doc.provider_name}'. Please add it to the AI Provider document."
            )
        provider_name = provider_doc.provider_name.lower()
        voice = tool_voice or _get_default_voice(provider_name)
        if voice and provider_name == "openai":
            voice = voice.lower()
        normalized = _normalize_model_name(tool_model, agent_doc.provider)
        return {
            "tts_model":     normalized,
            "voice":         voice,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  provider_doc,
            "source":        "tool_param",
        }

    if getattr(agent_doc, "tts_model", None):
        tts_model_doc = frappe.get_doc("AI Model", agent_doc.tts_model)

        if not tts_model_doc.provider:
            raise ValueError(
                f"TTS model '{agent_doc.tts_model}' has no provider linked. "
                f"Please set a provider on the AI Model document."
            )

        tts_provider_doc = frappe.get_doc("AI Provider", tts_model_doc.provider)
        api_key = tts_provider_doc.get_password("api_key")

        if not api_key:
            raise ValueError(
                f"API key is not configured for TTS provider "
                f"'{tts_provider_doc.provider_name}'. "
                f"Please add the API key to that AI Provider document."
            )

        provider_name = tts_provider_doc.provider_name.lower()

        voice = (
            getattr(agent_doc, "tts_voice", None)
            or _get_default_voice(provider_name)
            or tool_voice
        )
        if voice and provider_name == "openai":
            voice = voice.lower()

        normalized = _normalize_model_name(
            tts_model_doc.model_name, tts_model_doc.provider
        )
        return {
            "tts_model":     normalized,
            "voice":         voice,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  tts_provider_doc,
            "source":        "agent_config",
        }

    provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
    api_key = provider_doc.get_password("api_key")

    if not api_key:
        raise ValueError(
            f"API key is not configured for provider "
            f"'{provider_doc.provider_name}'. Please add it to the AI Provider document."
        )

    provider_name = provider_doc.provider_name.lower()
    tts_model = _get_default_tts_model(provider_name)

    if not tts_model:
        raise ValueError(
            f"Text-to-speech is not natively supported by provider "
            f"'{provider_doc.provider_name}'. Please either:\n"
            f"  \u2022 Set a dedicated 'TTS Model' on the Agent "
            f"(Advanced Settings \u2192 Audio Generation), or\n"
            f"  \u2022 Pass a 'model' parameter directly to the generate_audio tool."
        )

    voice = tool_voice or _get_default_voice(provider_name)
    if voice and provider_name == "openai":
        voice = voice.lower()
    normalized = _normalize_model_name(tts_model, agent_doc.provider)
    return {
        "tts_model":     normalized,
        "voice":         voice,
        "api_key":       api_key,
        "provider_name": provider_name,
        "provider_doc":  provider_doc,
        "source":        "provider_default",
    }


def _get_default_stt_model(provider_name: str) -> str:
    """
    Get default STT model for a provider.

    Backward-compatible alias for ``audio_service._get_default_stt_model``.
    """
    return audio_service._get_default_stt_model(provider_name)


def _resolve_stt_config(
    agent_doc,
    tool_model: str | None = None,
) -> dict:
    """
    Resolve the STT model, API key, and provider for audio transcription.
    Priority (highest → lowest):
    1. Tool-call parameter
    2. Agent-level STT configuration
    3. Provider default

    Backward-compatible alias for ``audio_service.resolve_stt_config``.
    """
    agent_name = getattr(agent_doc, "name", None) or agent_doc
    return audio_service.resolve_stt_config(agent_name, model=tool_model)


@frappe.whitelist()
async def handle_generate_audio(
    input: str,
    voice: str = None,
    model: str = None,
    speed: float = 1.0,
    response_format: str = "mp3",
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Generate audio (speech) from text using LiteLLM's speech() function.

    Uses LiteLLM's speech() function. The model used is either:
    1. The explicitly provided model parameter, OR
    2. An auto-detected suitable TTS model based on the provider

    Args:
        input: Text to convert to speech (required)
        voice: Voice to use (e.g., "alloy", "echo", "fable", "onyx", "nova", "shimmer")
        model: Optional model name (e.g., "tts-1", "tts-1-hd", "gemini-2.5-flash-preview-tts")
        speed: Speech speed from 0.25 to 4.0 (default: 1.0)
        response_format: Audio format (mp3, opus, aac, flac, wav, pcm)
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context

    Returns:
        dict: {
            "success": bool,
            "audio": {
                "url": str,
                "file_id": str,
                "message_id": str,
                "input_text": str,
                "voice": str,
                "speed": float,
                "format": str,
                "model": str
                "model_source": str,
                "tts_provider": str,
            },
            "message": str,
            "conversation_id": str
        }
    """
    try:
        # Get agent configuration from context
        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}

        agent_doc = frappe.get_doc("Agent", agent_name)

        try:
            tts_config = _resolve_tts_config(
                agent_doc, tool_model=model, tool_voice=voice
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        normalized_model = tts_config["tts_model"]
        voice            = tts_config["voice"]
        api_key          = tts_config["api_key"]
        provider_name    = tts_config["provider_name"]
        tts_source       = tts_config["source"]
        tts_provider_doc = tts_config["provider_doc"]

        import litellm

        speech_params: dict = {
            "model": normalized_model,
            "input": input,
            "voice": voice,
        }

        speech_params["api_key"] = api_key

        if speed != 1.0:
            speech_params["speed"] = speed
        if response_format != "mp3":
            speech_params["response_format"] = response_format

        # Call LiteLLM speech (returns HttpxBinaryResponseContent)
        response = await asyncio.to_thread(
            litellm.speech,
            **speech_params
        )

        # Get audio content from response
        # LiteLLM speech() returns HttpxBinaryResponseContent
        audio_bytes = response.content

        # Get conversation_index for message ordering
        conversation_index = None
        if conversation_id:
            try:
                last_index = frappe.db.sql("""
                    SELECT MAX(conversation_index) as last_index
                    FROM `tabAgent Message`
                    WHERE conversation = %s
                """, (conversation_id,), as_dict=1)

                conversation_index = (last_index[0].last_index if last_index and last_index[0].last_index is not None else 0) + 1
            except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError):
                # Hard failure: message ordering is required; abort and alert admin.
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Failed to compute conversation_index for {conversation_id}"
                )
                frappe.throw(
                    "Could not determine message order for this conversation. Please retry.",
                    title="Message Ordering Error"
                )

        # Generate filename
        filename = f"generated_audio_{conversation_index}.{response_format}"

        # Create Agent Message first (we'll attach the file to it)
        message_doc = None
        if conversation_id and conversation_index is not None:
            if frappe.has_permission("Agent Message", "create"):
                try:
                    # Get provider and model from agent
                    provider = agent_doc.provider
                    model_name = agent_doc.model

                    # Create Agent Message with kind "Audio"
                    message_doc = frappe.get_doc({
                        "doctype": "Agent Message",
                        "conversation": conversation_id,
                        "role": "agent",
                        "content": f"Generated audio: {input[:100]}{'...' if len(input) > 100 else ''}",
                        "kind": "Audio",
                        "agent": agent_name,
                        "provider": provider,
                        "model": model_name,
                        "agent_run": kwargs.get("agent_run_id"),
                        "conversation_index": conversation_index,
                        "is_agent_message": 1,
                        "user": "Agent",
                        "tts_voice": voice
                    })
                    message_doc.insert()

                    if tts_source == "agent_config" and getattr(agent_doc, "tts_model", None):
                        frappe.db.set_value(
                            "Agent Message", message_doc.name,
                            "tts_model", agent_doc.tts_model,
                            update_modified=False
                        )
                        message_doc.tts_model = agent_doc.tts_model

                except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
                    logger.warning(f"Create audio message failed: {e!s}")
                    message_doc = None
            else:
                frappe.logger("huf").warning(
                    f"User {frappe.session.user} does not have permission to create Agent Message; attaching audio to conversation instead."
                )

        # Save file attached to the Agent Message
        if message_doc:
            saved_file = save_file(
                filename,
                audio_bytes,
                "Agent Message",
                message_doc.name,
                is_private=False,
                df="generated_audio"
            )
        else:
            # Fallback: attach to conversation if message creation failed
            saved_file = save_file(
                filename,
                audio_bytes,
                "Agent Conversation",
                conversation_id or "Unknown",
                is_private=False
            )

        # Get file URL
        file_url = getattr(saved_file, 'file_url', None)
        file_id = getattr(saved_file, 'name', None)

        if not file_url:
            file_url = f"/files/{getattr(saved_file, 'file_name', filename)}"

        # Update the message with the file URL
        if message_doc and file_url:
            message_doc.db_set("generated_audio", file_url)
            commit_if_background()

            # Emit socket event for new agent message (Audio)
            try:
                frappe.publish_realtime(
                    event=f'conversation:{conversation_id}',
                    message={
                        "type": "new_agent_message",
                        "conversation_id": conversation_id,
                        "message_id": message_doc.name,
                        "kind": "Audio",
                        "content": message_doc.content,
                        "generated_audio": file_url,
                        "agent_run_id": kwargs.get("agent_run_id"),
                        "conversation_index": message_doc.conversation_index,
                    },
                    user=frappe.session.user,
                    after_commit=False
                )
            except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
                frappe.logger("huf").debug(
                    f"Error emitting new_agent_message socket event: {e!s}"
                )

        # Update conversation total_messages
        if conversation_id and conversation_index is not None:
            try:
                frappe.db.sql("""
                    UPDATE `tabAgent Conversation`
                    SET total_messages = %s, last_activity = NOW()
                    WHERE name = %s
                """, (conversation_index, conversation_id))
            except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
                frappe.logger("huf").debug(
                    f"Error updating conversation total_messages: {e!s}"
                )

        return {
            "success": True,
            "audio": {
                "url": file_url,
                "file_id": file_id,
                "message_id": message_doc.name if message_doc else None,
                "input_text": input,
                "voice": voice,
                "speed": speed,
                "format": response_format,
                "model": normalized_model,
                "model_source": tts_source,
                "tts_provider": tts_provider_doc.provider_name,
            },
            "message": "Generated audio successfully",
            "conversation_id": conversation_id
        }

    except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
        # Hard provider/tool failure: retain Error Log for admin attention.
        frappe.log_error(title="Audio Generation Tool", message=f"Audio generation error: {e!s}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
async def handle_transcribe_audio(
    file_id: str = None,
    file_url: str = None,
    file_path: str = None,
    language: str = None,
    model: str = None,
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Transcribe audio using LiteLLM's transcription function.

    This is a pure agent tool: it resolves the audio file, calls the
    canonical audio service, and returns the transcript. It does **not**
    create or update Agent Message records. Callers that need chat/UI
    persistence should use ``huf.ai.audio_api.transcribe`` or the chat
    endpoints, which layer message creation on top of the same service.

    Uses LiteLLM's transcription() function. The model used is either:
    1. The explicitly provided model parameter, OR
    2. An auto-detected suitable transcription model based on the provider

    Args:
        file_id: File document ID (preferred) - File must exist in Frappe
        file_url: File URL/path (alternative) - e.g., "/files/audio.mp3"
        file_path: Absolute server path inside an allowed audio import
               directory (alternative to file_id/file_url)
        language: Optional language code (e.g., "en", "es", "fr") - ISO 639-1 format
        model: Optional model name (e.g., "whisper-1", "whisper-large-v3")
               If not provided, defaults based on provider
        agent_name: Automatically passed from context
        conversation_id: Present for context but ignored; this tool does
            not create messages.

    Returns:
        dict: {
            "success": bool,
            "text": str,
            "transcript": str,
            "file_id": str,
            "file_url": str,
            "local_path": str,
            "language": str,
            "model": str,
            "provider": str
        }
    """
    try:
        # Pure transcription (no message/socket side effects) via the
        # canonical audio service.
        result = await asyncio.to_thread(
            audio_service.transcribe_audio_file,
            file_id=file_id,
            file_url=file_url,
            local_path=file_path,
            agent_name=agent_name,
            language=language,
            model=model,
        )

        if not result.get("success"):
            return result

        transcribed_text = result["text"]

        return {
            "success": True,
            "text": transcribed_text,
            "transcript": transcribed_text,
            "file_id": result.get("file_id"),
            "file_url": result.get("file_url"),
            "local_path": result.get("local_path"),
            "language": result.get("language") or "auto-detected",
            "model": result.get("stt_model"),
            "provider": result.get("provider"),
        }

    except (frappe.DoesNotExistError, frappe.ValidationError, AttributeError, KeyError, ValueError) as e:
        # Hard transcription failure: retain Error Log for admin attention.
        frappe.log_error(f"Audio transcription error: {e!s}", "Audio Transcription Tool")
        return {"success": False, "error": str(e)}
