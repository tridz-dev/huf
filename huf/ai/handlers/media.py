"""
Media handler functions for Huf Agent tools.

Covers image generation, OCR/document processing, text-to-speech,
and speech-to-text (audio transcription). Uses shared helpers from
media_utils.py to avoid boilerplate repetition.
"""

import asyncio
import base64

import frappe
import requests

from huf.ai.media_utils import (
	create_agent_message,
	emit_message_event,
	get_agent_provider_config,
	get_next_conversation_index,
	save_media_file,
	update_conversation_total_messages,
)


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

def _get_default_image_model(provider_name: str) -> str:
	"""Get default image generation model for a provider."""
	defaults = {
		"openai": "dall-e-3",
		"azure": "dall-e-3",
		"openrouter": "dall-e-3",
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
	**kwargs,
):
	"""
	Generate an image using the agent's configured provider and image generation model.

	Uses LiteLLM's image_generation() function. The model used is either:
	1. The agent's explicitly configured image_generation_model field, OR
	2. An auto-detected suitable image model based on the provider
	"""
	try:
		agent_doc, provider_doc, api_key = get_agent_provider_config(agent_name)

		# Determine image generation model
		image_model = None
		if hasattr(agent_doc, "image_generation_model") and agent_doc.image_generation_model:
			model_doc = frappe.get_doc("AI Model", agent_doc.image_generation_model)
			image_model = model_doc.model_name
		else:
			provider_name = provider_doc.provider_name.lower()
			image_model = _get_default_image_model(provider_name)

		if not image_model:
			return {
				"success": False,
				"error": (
					f"Image generation not supported for provider '{provider_doc.provider_name}'. "
					f"Please configure an image_generation_model in agent settings."
				),
			}

		from huf.ai.providers.litellm import _normalize_model_name

		normalized_model = _normalize_model_name(image_model, agent_doc.provider)

		import litellm

		litellm.drop_params = True

		response = await asyncio.to_thread(
			litellm.image_generation,
			prompt=prompt,
			model=normalized_model,
			n=n,
			size=size,
			quality=quality,
			api_key=api_key,
		)

		# Get conversation_index once if conversation_id exists
		conversation_index = None
		if conversation_id:
			conversation_index = get_next_conversation_index(conversation_id)

		# Process response and save images
		images = []
		if hasattr(response, "data") and response.data:
			for idx, image_data in enumerate(response.data):
				# Get image URL or base64
				image_url = None
				image_b64 = None

				if hasattr(image_data, "url"):
					image_url = image_data.url
				if hasattr(image_data, "b64_json"):
					image_b64 = image_data.b64_json

				if not image_url and not image_b64 and isinstance(image_data, dict):
					image_url = image_data.get("url")
					image_b64 = image_data.get("b64_json")

				if not image_url and not image_b64:
					continue

				# Download and save image
				image_bytes = None
				filename = f"generated_image_{idx + 1}.png"

				if image_url and image_url.startswith("http"):
					img_response = requests.get(image_url, timeout=30)
					img_response.raise_for_status()
					image_bytes = img_response.content
				elif image_b64:
					image_bytes = base64.b64decode(image_b64)
				elif image_url:
					frappe.log_error(
						title="Image Generation",
						message=f"Unsupported image URL format: {image_url}",
					)
					continue

				if not image_bytes:
					continue

				# Create Agent Message
				message_doc = None
				if conversation_id and conversation_index is not None:
					message_doc = create_agent_message(
						conversation_id=conversation_id,
						agent_name=agent_name,
						agent_doc=agent_doc,
						kind="Image",
						content=f"Generated image: {prompt}",
						conversation_index=conversation_index + idx,
						agent_run_id=kwargs.get("agent_run_id"),
					)

				# Save file
				file_url, file_id = save_media_file(
					filename,
					image_bytes,
					message_doc=message_doc,
					conversation_id=conversation_id,
					field_name="generated_image",
				)

				# Update the message with the file URL
				if message_doc and file_url:
					message_doc.db_set("generated_image", file_url)
					frappe.db.commit()

					emit_message_event(
						conversation_id,
						message_doc,
						"Image",
						extra_data={
							"generated_image": file_url,
							"agent_run_id": kwargs.get("agent_run_id"),
						},
					)

				images.append({"url": file_url, "file_id": file_id})

		# Update conversation total_messages once after all images
		if conversation_id and conversation_index is not None and images:
			final_index = conversation_index + len(images) - 1
			update_conversation_total_messages(conversation_id, final_index)

		if not images:
			return {
				"success": False,
				"error": "Image generation succeeded but no images were returned",
			}

		frappe.logger().debug(f"Returned images: {images}")
		return {
			"success": True,
			"images": images,
			"message": f"Generated {len(images)} image(s) successfully",
		}

	except ValueError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(title="Image Generation Tool", message=f"Image generation error: {str(e)}")
		return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# OCR / Document processing
# ---------------------------------------------------------------------------

def _determine_ocr_strategy(file_path: str, file_type: str) -> str:
	"""Determine OCR strategy based on file type."""
	ext = file_path.lower().split(".")[-1] if "." in file_path else ""

	if file_type in ["pdf", "application/pdf"] or ext == "pdf":
		return "ocr"

	if file_type.startswith("image/") or ext in ["jpg", "jpeg", "png", "webp", "gif"]:
		return "vision"

	return "vision"


def _get_default_ocr_model(provider_name: str, strategy: str) -> str:
	"""Get default OCR/Vision model for a provider."""
	if strategy == "ocr":
		defaults = {
			"mistral": "mistral/mistral-ocr-latest",
			"azure": "azure_ai/ocr",
			"google": "vertex_ai/ocr",
			"vertex_ai": "vertex_ai/ocr",
		}
	else:
		defaults = {
			"mistral": "mistral/mistral-small-latest",
			"openai": "gpt-4o",
			"google": "gemini/gemini-2.5-flash",
			"gemini": "gemini/gemini-2.5-flash",
			"anthropic": "claude-3-5-sonnet-20241022",
		}
	return defaults.get(provider_name.lower())


async def _process_with_ocr_endpoint(
	file_path: str,
	model: str,
	api_key: str,
	pages: str = None,
	include_images: bool = False,
):
	"""Process document using LiteLLM OCR endpoint."""
	import litellm

	try:
		with open(file_path, "rb") as f:
			file_content = f.read()
			base64_content = base64.b64encode(file_content).decode("utf-8")

		ext = file_path.lower().split(".")[-1]
		mime_type = "application/pdf" if ext == "pdf" else f"image/{ext}"

		ocr_params = {
			"model": model,
			"document": {
				"type": "document_url",
				"document_url": f"data:{mime_type};base64,{base64_content}",
			},
			"api_key": api_key,
		}

		if pages:
			page_list = [int(p.strip()) for p in pages.split(",")]
			ocr_params["pages"] = page_list

		if include_images:
			ocr_params["include_image_base64"] = True

		response = await asyncio.to_thread(litellm.ocr, **ocr_params)

		all_text = []
		pages_data = []

		for page in response.pages:
			all_text.append(f"## Page {page.index + 1}\n\n{page.markdown}")
			pages_data.append(
				{
					"index": page.index,
					"text": page.markdown,
					"dimensions": page.dimensions if hasattr(page, "dimensions") else None,
				}
			)

		combined_text = "\n\n".join(all_text)

		return {"success": True, "text": combined_text, "pages": pages_data}

	except Exception as e:
		return {"success": False, "error": str(e)}


async def _process_with_vision_model(file_path: str, model: str, api_key: str):
	"""Process image using LiteLLM vision models."""
	import litellm

	try:
		with open(file_path, "rb") as f:
			file_content = f.read()
			base64_image = base64.b64encode(file_content).decode("utf-8")

		ext = file_path.lower().split(".")[-1]

		if ext == "pdf":
			mime_type = "application/pdf"
		elif ext in ["jpg", "jpeg", "png", "webp", "gif"]:
			mime_type = f"image/{ext}"
		else:
			mime_type = "image/jpeg"

		messages = [
			{
				"role": "user",
				"content": [
					{
						"type": "text",
						"text": (
							"Extract all text from this image. "
							"Preserve formatting, structure, and layout. "
							"Return the text in markdown format."
						),
					},
					{
						"type": "image_url",
						"image_url": f"data:{mime_type};base64,{base64_image}",
					},
				],
			}
		]

		response = await asyncio.to_thread(
			litellm.completion,
			model=model,
			messages=messages,
			api_key=api_key,
		)

		extracted_text = response.choices[0].message.content

		return {
			"success": True,
			"text": extracted_text,
			"pages": [{"index": 0, "text": extracted_text}],
		}

	except Exception as e:
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
	**kwargs,
):
	"""
	Extract text from documents and images using OCR.

	Intelligently routes to:
	- LiteLLM OCR endpoint for PDFs (multi-page documents)
	- Vision models for single images (better context understanding)
	"""
	try:
		agent_doc, provider_doc, api_key = get_agent_provider_config(agent_name)

		# Get file
		file_doc = None
		if file_id:
			try:
				file_doc = frappe.get_doc("File", file_id)
			except Exception as e:
				return {"success": False, "error": f"File not found: {str(e)}"}
		elif file_url:
			file_path_name = file_url.replace("/files/", "")
			file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["name"], as_dict=True)
			if file_doc:
				file_doc = frappe.get_doc("File", file_doc.name)
			else:
				file_doc = frappe.db.get_value(
					"File", {"file_name": file_path_name}, ["name"], as_dict=True
				)
				if file_doc:
					file_doc = frappe.get_doc("File", file_doc.name)

		if not file_doc:
			return {"success": False, "error": "Either file_id or file_url is required"}

		file_path = file_doc.get_full_path()
		file_type = file_doc.file_type or ""
		file_name = file_doc.file_name or ""

		# Determine strategy
		strategy = _determine_ocr_strategy(file_path, file_type)

		# Override strategy for Google/Gemini
		provider_name = provider_doc.provider_name.lower()
		if provider_name in ["google", "gemini"] and (
			strategy == "ocr" or file_path.lower().endswith(".pdf")
		):
			strategy = "vision"

		# Determine model
		ocr_model = model
		if not ocr_model:
			ocr_model = _get_default_ocr_model(provider_name, strategy)

		if not ocr_model:
			return {
				"success": False,
				"error": (
					f"OCR not supported for provider '{provider_doc.provider_name}' "
					f"with strategy '{strategy}'. Please provide a model parameter."
				),
			}

		from huf.ai.providers.litellm import _normalize_model_name

		normalized_model = _normalize_model_name(ocr_model, agent_doc.provider)

		# Route to appropriate method
		if strategy == "ocr":
			result = await _process_with_ocr_endpoint(
				file_path, normalized_model, api_key, pages, include_images
			)
		else:
			result = await _process_with_vision_model(file_path, normalized_model, api_key)

		if not result["success"]:
			return result

		extracted_text = result["text"]
		pages_data = result.get("pages", [])

		# Create Agent Message with extracted text
		message_doc = None
		if conversation_id:
			try:
				conversation_index = get_next_conversation_index(conversation_id)

				truncated = (
					extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
				)
				message_doc = create_agent_message(
					conversation_id=conversation_id,
					agent_name=agent_name,
					agent_doc=agent_doc,
					kind="Message",
					content=f"Extracted text from {file_name}:\n\n{truncated}",
					conversation_index=conversation_index,
					agent_run_id=kwargs.get("agent_run_id"),
				)

				if message_doc:
					update_conversation_total_messages(conversation_id, conversation_index)
					frappe.db.commit()

					emit_message_event(conversation_id, message_doc, "Message")

			except Exception as e:
				frappe.log_error(
					title="OCR Message Creation",
					message=f"Error creating Agent Message for OCR: {str(e)}",
				)

		return {
			"success": True,
			"text": extracted_text,
			"pages": pages_data,
			"strategy": strategy,
			"file_id": file_doc.name,
			"file_name": file_name,
			"message_id": message_doc.name if message_doc else None,
			"model": normalized_model,
			"conversation_id": conversation_id,
		}

	except ValueError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(title="OCR Tool", message=f"OCR error: {str(e)}")
		return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

def _get_default_voice(provider_name: str) -> str:
	"""Get default voice for a provider."""
	defaults = {
		"openai": "alloy",
		"elevenlabs": "21m00Tcm4TlvDq8ikWAM",
		"google": "Puck",
		"vertex_ai": "Puck",
		"gemini": "Puck",
		"azure": "en-US-JennyNeural",
		"mistral": "mistral-male-1",
	}
	return defaults.get(provider_name.lower(), "alloy")


def _get_default_tts_model(provider_name: str) -> str:
	"""Get default TTS model for a provider."""
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


_TTS_ENV_VAR_PROVIDERS: dict[str, str] = {
	"google": "GEMINI_API_KEY",
	"gemini": "GEMINI_API_KEY",
	"vertex_ai": "GEMINI_API_KEY",
	"elevenlabs": "ELEVENLABS_API_KEY",
	"minimax": "MINIMAX_API_KEY",
}


def _resolve_tts_config(
	agent_doc,
	tool_model: str | None = None,
	tool_voice: str | None = None,
) -> dict:
	"""
	Resolve the TTS model, voice, API key, and provider for audio generation.

	Priority (highest to lowest):
	1. Tool-call parameter
	2. Agent-level TTS configuration
	3. Provider default
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
		normalized = _normalize_model_name(tool_model, agent_doc.provider)
		return {
			"tts_model": normalized,
			"voice": voice,
			"api_key": api_key,
			"provider_name": provider_name,
			"provider_doc": provider_doc,
			"source": "tool_param",
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

		voice = getattr(agent_doc, "tts_voice", None) or _get_default_voice(provider_name) or tool_voice

		normalized = _normalize_model_name(tts_model_doc.model_name, tts_model_doc.provider)
		return {
			"tts_model": normalized,
			"voice": voice,
			"api_key": api_key,
			"provider_name": provider_name,
			"provider_doc": tts_provider_doc,
			"source": "agent_config",
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
	normalized = _normalize_model_name(tts_model, agent_doc.provider)
	return {
		"tts_model": normalized,
		"voice": voice,
		"api_key": api_key,
		"provider_name": provider_name,
		"provider_doc": provider_doc,
		"source": "provider_default",
	}


@frappe.whitelist()
async def handle_generate_audio(
	input: str,
	voice: str = None,
	model: str = None,
	speed: float = 1.0,
	response_format: str = "mp3",
	agent_name: str = None,
	conversation_id: str = None,
	**kwargs,
):
	"""
	Generate audio (speech) from text using LiteLLM's speech() function.

	Uses LiteLLM's speech() function. The model used is either:
	1. The explicitly provided model parameter, OR
	2. An auto-detected suitable TTS model based on the provider
	"""
	try:
		agent_doc = frappe.get_doc("Agent", agent_name) if agent_name else None
		if not agent_doc:
			return {"success": False, "error": "Agent name not found in context"}

		try:
			tts_config = _resolve_tts_config(agent_doc, tool_model=model, tool_voice=voice)
		except ValueError as exc:
			return {"success": False, "error": str(exc)}

		normalized_model = tts_config["tts_model"]
		voice = tts_config["voice"]
		api_key = tts_config["api_key"]
		provider_name = tts_config["provider_name"]
		tts_source = tts_config["source"]
		tts_provider_doc = tts_config["provider_doc"]

		import litellm

		speech_params: dict = {
			"model": normalized_model,
			"input": input,
			"voice": voice,
		}

		if provider_name in _TTS_ENV_VAR_PROVIDERS:
			import os

			os.environ[_TTS_ENV_VAR_PROVIDERS[provider_name]] = api_key
		else:
			speech_params["api_key"] = api_key

		if speed != 1.0:
			speech_params["speed"] = speed
		if response_format != "mp3":
			speech_params["response_format"] = response_format

		response = await asyncio.to_thread(litellm.speech, **speech_params)
		audio_bytes = response.content

		# Get conversation_index for message ordering
		conversation_index = None
		if conversation_id:
			conversation_index = get_next_conversation_index(conversation_id)

		filename = f"generated_audio_{conversation_index}.{response_format}"

		# Create Agent Message
		message_doc = None
		if conversation_id and conversation_index is not None:
			truncated = input[:100] + "..." if len(input) > 100 else input
			message_doc = create_agent_message(
				conversation_id=conversation_id,
				agent_name=agent_name,
				agent_doc=agent_doc,
				kind="Audio",
				content=f"Generated audio: {truncated}",
				conversation_index=conversation_index,
				agent_run_id=kwargs.get("agent_run_id"),
				tts_voice=voice,
			)

			if message_doc and tts_source == "agent_config" and getattr(agent_doc, "tts_model", None):
				frappe.db.set_value(
					"Agent Message",
					message_doc.name,
					"tts_model",
					agent_doc.tts_model,
					update_modified=False,
				)
				message_doc.tts_model = agent_doc.tts_model

		# Save file
		file_url, file_id = save_media_file(
			filename,
			audio_bytes,
			message_doc=message_doc,
			conversation_id=conversation_id,
			field_name="generated_audio",
		)

		# Update the message with the file URL
		if message_doc and file_url:
			message_doc.db_set("generated_audio", file_url)
			frappe.db.commit()

			emit_message_event(
				conversation_id,
				message_doc,
				"Audio",
				extra_data={
					"generated_audio": file_url,
					"agent_run_id": kwargs.get("agent_run_id"),
				},
			)

		# Update conversation total_messages
		if conversation_id and conversation_index is not None:
			update_conversation_total_messages(conversation_id, conversation_index)

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
			"conversation_id": conversation_id,
		}

	except Exception as e:
		frappe.log_error(title="Audio Generation Tool", message=f"Audio generation error: {str(e)}")
		return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Speech-to-text / transcription
# ---------------------------------------------------------------------------

def _get_default_stt_model(provider_name: str) -> str:
	"""Get default STT model for a provider."""
	defaults = {
		"openai": "whisper-1",
		"azure": "whisper-1",
		"groq": "groq/whisper-large-v3",
		"deepgram": "deepgram/nova-2",
	}
	return defaults.get(provider_name.lower())


def _resolve_stt_config(
	agent_doc,
	tool_model: str | None = None,
) -> dict:
	"""
	Resolve the STT model, API key, and provider for audio transcription.
	Priority (highest to lowest):
	1. Tool-call parameter
	2. Agent-level STT configuration
	3. Provider default
	"""
	from huf.ai.providers.litellm import _normalize_model_name

	if tool_model:
		stt_provider_name = None
		search_model = tool_model
		if "/" in search_model:
			search_model = search_model.split("/")[-1]

		model_doc = frappe.get_all("AI Model", filters={"name": search_model}, fields=["provider"])
		if model_doc:
			stt_provider_name = model_doc[0].provider
		elif "/" in tool_model:
			provider_slug = tool_model.split("/")[0]
			provs = frappe.get_all("AI Provider", filters={"slug": provider_slug}, fields=["name"])
			if provs:
				stt_provider_name = provs[0].name

		if not stt_provider_name:
			stt_provider_name = agent_doc.provider

		provider_doc = frappe.get_doc("AI Provider", stt_provider_name)
		api_key = provider_doc.get_password("api_key")
		if not api_key:
			raise ValueError(f"API key is not configured for provider '{provider_doc.provider_name}'.")

		provider_name = provider_doc.provider_name.lower()
		normalized = _normalize_model_name(tool_model, stt_provider_name)
		return {
			"stt_model": normalized,
			"api_key": api_key,
			"provider_name": provider_name,
			"provider_doc": provider_doc,
			"source": "tool_param",
		}

	if getattr(agent_doc, "stt_model", None):
		stt_model_doc = frappe.get_doc("AI Model", agent_doc.stt_model)
		if not stt_model_doc.provider:
			raise ValueError(f"STT model '{agent_doc.stt_model}' has no provider linked.")

		stt_provider_doc = frappe.get_doc("AI Provider", stt_model_doc.provider)
		api_key = stt_provider_doc.get_password("api_key")
		if not api_key:
			raise ValueError(
				f"API key is not configured for STT provider '{stt_provider_doc.provider_name}'."
			)

		provider_name = stt_provider_doc.provider_name.lower()
		normalized = _normalize_model_name(stt_model_doc.model_name, stt_model_doc.provider)
		return {
			"stt_model": normalized,
			"api_key": api_key,
			"provider_name": provider_name,
			"provider_doc": stt_provider_doc,
			"source": "agent_config",
		}

	provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
	api_key = provider_doc.get_password("api_key")
	if not api_key:
		raise ValueError(f"API key is not configured for provider '{provider_doc.provider_name}'.")

	provider_name = provider_doc.provider_name.lower()
	stt_model = _get_default_stt_model(provider_name)

	if not stt_model:
		stt_model = "whisper-1"  # Safe ultimate fallback

	normalized = _normalize_model_name(stt_model, agent_doc.provider)
	return {
		"stt_model": normalized,
		"api_key": api_key,
		"provider_name": provider_name,
		"provider_doc": provider_doc,
		"source": "provider_default",
	}


@frappe.whitelist()
async def handle_transcribe_audio(
	file_id: str = None,
	file_url: str = None,
	language: str = None,
	model: str = None,
	agent_name: str = None,
	conversation_id: str = None,
	**kwargs,
):
	"""
	Transcribe audio using LiteLLM's transcription function.

	Uses LiteLLM's transcription() function. The model used is either:
	1. The explicitly provided model parameter, OR
	2. An auto-detected suitable transcription model based on the provider
	"""
	try:
		message_id = kwargs.get("message_id")

		if not agent_name:
			return {"success": False, "error": "Agent name not found in context"}

		agent_doc = frappe.get_doc("Agent", agent_name)

		# Get audio file
		file_doc = None
		if file_id:
			try:
				file_doc = frappe.get_doc("File", file_id)
			except Exception as e:
				return {"success": False, "error": f"File not found: {str(e)}"}
		elif file_url:
			try:
				file_doc = frappe.get_doc("File", {"file_url": file_url})
			except Exception:
				file_name = file_url.replace("/files/", "")
				file_doc = frappe.get_doc("File", {"file_name": file_name})

			if not file_doc:
				return {"success": False, "error": f"File not found at URL: {file_url}"}
		else:
			return {"success": False, "error": "Either file_id or file_url is required"}

		try:
			file_path = file_doc.get_full_path()
		except Exception as e:
			return {"success": False, "error": f"Error getting file path: {str(e)}"}

		# Determine transcription model
		try:
			stt_config = _resolve_stt_config(agent_doc, tool_model=model)
		except ValueError as exc:
			return {"success": False, "error": str(exc)}

		normalized_model = stt_config["stt_model"]
		api_key = stt_config["api_key"]
		provider_name = stt_config["provider_name"]
		stt_source = stt_config["source"]

		# Call LiteLLM transcription
		import litellm

		if provider_name in ["google", "gemini", "vertex_ai"]:
			import mimetypes
			import os

			with open(file_path, "rb") as audio_file:
				audio_data = audio_file.read()

			mime_type, _ = mimetypes.guess_type(file_path)
			if not mime_type:
				mime_type = "audio/mp3"

			if file_path.lower().endswith(".webm") or mime_type == "video/webm":
				mime_type = "audio/webm"

			base64_audio = base64.b64encode(audio_data).decode("utf-8")
			audio_url = f"data:{mime_type};base64,{base64_audio}"

			messages = [
				{
					"role": "user",
					"content": [
						{
							"type": "text",
							"text": (
								"Please transcribe this audio exactly as it is spoken. "
								"Do not add any extra commentary or formatting. "
								"If there are multiple languages, transcribe them as spoken. "
								"If it is silent, just write [Silence]."
							),
						},
						{"type": "image_url", "image_url": {"url": audio_url}},
					],
				}
			]

			env_var = _TTS_ENV_VAR_PROVIDERS.get(provider_name, "GEMINI_API_KEY")
			os.environ[env_var] = api_key

			try:
				response = await asyncio.to_thread(
					litellm.completion,
					model=normalized_model,
					messages=messages,
					api_key=api_key,
				)
				transcribed_text = response.choices[0].message.content
			except Exception as e:
				return {"success": False, "error": f"Transcription failed: {str(e)}"}

		else:
			# Standard transcription handling (OpenAI, Deepgram, Groq, etc.)
			transcription_params = {
				"model": normalized_model,
				"file": file_path,
				"api_key": api_key,
			}

			if language:
				transcription_params["language"] = language

			def _sync_transcribe(params):
				with open(file_path, "rb") as audio_file:
					params["file"] = audio_file
					return litellm.transcription(**params)

			try:
				response = await asyncio.to_thread(_sync_transcribe, transcription_params)
			except Exception as e:
				return {"success": False, "error": f"Transcription failed: {str(e)}"}

			if hasattr(response, "text"):
				transcribed_text = response.text
			elif isinstance(response, dict):
				transcribed_text = response.get("text", "")
			else:
				transcribed_text = str(response)

		if not transcribed_text:
			return {"success": False, "error": "Transcription returned empty result"}

		# Create Agent Message with transcription result
		message_doc = None
		if conversation_id:
			try:
				conversation_index = get_next_conversation_index(conversation_id)

				# Create or Update Agent Message
				if message_id and frappe.db.exists("Agent Message", message_id):
					message_doc = frappe.get_doc("Agent Message", message_id)
					message_doc.content = transcribed_text
					if not message_doc.kind:
						message_doc.kind = "Audio"
					if stt_source == "agent_config" and getattr(agent_doc, "stt_model", None):
						message_doc.stt_model = agent_doc.stt_model
					message_doc.save(ignore_permissions=True)
				else:
					doc_data = {
						"doctype": "Agent Message",
						"conversation": conversation_id,
						"role": "user",
						"content": transcribed_text,
						"kind": "Audio",
						"agent": agent_name,
						"provider": agent_doc.provider,
						"model": agent_doc.model,
						"agent_run": kwargs.get("agent_run_id"),
						"conversation_index": conversation_index,
						"is_agent_message": 0,
						"user": frappe.session.user,
					}
					message_doc = frappe.get_doc(doc_data)
					if stt_source == "agent_config" and getattr(agent_doc, "stt_model", None):
						message_doc.stt_model = agent_doc.stt_model
					message_doc.insert(ignore_permissions=True)

				# Attach file to message if not already attached
				if file_doc and message_doc:
					if not file_doc.attached_to_name:
						file_doc.db_set("attached_to_name", message_doc.name)
						file_doc.db_set("attached_to_doctype", "Agent Message")
						file_doc.db_set("is_private", 0)

				# Update conversation
				if not message_id:
					update_conversation_total_messages(conversation_id, conversation_index)
				else:
					frappe.db.set_value(
						"Agent Conversation", conversation_id, "last_activity", frappe.utils.now()
					)

				frappe.db.commit()

				# Emit socket event
				try:
					frappe.publish_realtime(
						event=f"conversation:{conversation_id}",
						message={
							"type": "update_message" if message_id else "new_user_message",
							"conversation_id": conversation_id,
							"message_id": message_doc.name,
							"content": transcribed_text,
							"kind": "Audio",
							"file": (
								{
									"file_name": file_doc.file_name,
									"file_url": file_doc.file_url,
								}
								if file_doc
								else None
							),
							"conversation_index": conversation_index,
						},
						user=frappe.session.user,
						after_commit=False,
					)
				except Exception as e:
					frappe.log_error(
						title="Audio Transcription Socket Event",
						message=f"Error emitting new_user_message socket event: {str(e)}",
					)

			except Exception as e:
				frappe.log_error(
					title="Audio Transcription Message Creation",
					message=f"Error creating Agent Message for transcription: {str(e)}",
				)

		return {
			"success": True,
			"text": transcribed_text,
			"file_id": file_doc.name,
			"message_id": message_doc.name if message_doc else None,
			"language": language or "auto-detected",
			"model": normalized_model,
		}

	except Exception as e:
		frappe.log_error(
			title="Audio Transcription Tool", message=f"Audio transcription error: {str(e)}"
		)
		return {"success": False, "error": str(e)}
