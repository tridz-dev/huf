"""App capability validation (moved verbatim from apps_loader.py)."""


def validate_app_capabilities(capabilities: dict, agent_doc) -> list:
	"""
	Check that ``capabilities`` (the proposed ``HUF App.capabilities`` JSON
	blob) is a subset of what the linked ``agent_doc`` (Agent doc) actually
	supports.

	Covers file_upload / ocr / audio_input / audio_output / live_voice /
	video_output. 'live_voice' is validated for basic Agent config only
	(voice_enabled + voice_engine present) -- known upstream gaps in the
	voice engines themselves (send_to_session unimplemented, no user-speech
	persistence on litellm_realtime, no memory injection on either engine;
	see huf/ai/voice/README.md's "Known gaps") are informational and
	surfaced separately via ``collect_app_capability_warnings``, not treated
	as hard errors here.

	Returns a list of human-readable error strings; an empty list means the
	capabilities payload is valid.
	"""
	errors = []
	if not capabilities:
		return errors

	if capabilities.get("file_upload") and not agent_doc.get("allow_file_upload"):
		errors.append(
			"App capability 'file_upload' requires the linked Agent to have "
			"'allow_file_upload' enabled."
		)

	if capabilities.get("ocr") and not agent_doc.get("enable_ocr"):
		errors.append(
			"App capability 'ocr' requires the linked Agent to have "
			"'enable_ocr' enabled."
		)

	if capabilities.get("audio_input") and not agent_doc.get("stt_model"):
		errors.append(
			"App capability 'audio_input' requires the linked Agent to have "
			"an 'stt_model' configured."
		)

	if capabilities.get("audio_output") and not agent_doc.get("tts_model"):
		errors.append(
			"App capability 'audio_output' requires the linked Agent to have "
			"a 'tts_model' configured."
		)

	if capabilities.get("live_voice"):
		if not agent_doc.get("voice_enabled"):
			errors.append(
				"App capability 'live_voice' requires the linked Agent to have "
				"'voice_enabled' turned on."
			)
		if not agent_doc.get("voice_engine"):
			errors.append(
				"App capability 'live_voice' requires the linked Agent to have "
				"a 'voice_engine' configured."
			)

	if capabilities.get("video_output"):
		# GAP (documented, not silently skipped): Agent DocType has no
		# dedicated video-generation-model field yet (no analogue to
		# `image_generation_model` / `tts_model` — confirmed by inspecting
		# huf/huf/doctype/agent/agent.json). Until such a field exists, this
		# capability can never be meaningfully validated, so we fail closed
		# rather than pretend it passed. See
		# the hub-orchestrator unified builder plan (archived in the workspace) Phase 10 and
		# the hub-orchestrator-app-builder-todo note (workspace).
		errors.append(
			"App capability 'video_output' cannot be validated yet: the "
			"Agent DocType has no video-generation-model field (analogous "
			"to 'image_generation_model'/'tts_model'). Add that field "
			"before enabling this capability; until then 'video_output' is "
			"rejected rather than silently accepted."
		)

	return errors


def collect_app_capability_warnings(capabilities: dict, agent_doc) -> list:
	"""
	Return non-blocking, informational warnings about ``capabilities`` that are
	otherwise valid (see ``validate_app_capabilities``) but have known platform
	limitations the caller should be told about rather than silently hitting
	at runtime.

	Currently: 'live_voice' when the Agent's configured voice engine reports
	``memory: False`` from its ``capabilities()`` (see
	huf/ai/voice/engines/base.py and huf/ai/voice/README.md's "Known gaps" --
	no shipped voice engine currently injects Agent memory into a live voice
	session). This does not block saving; it is surfaced so the caller can
	set expectations.
	"""
	warnings = []
	if not capabilities:
		return warnings

	if capabilities.get("live_voice") and agent_doc.get("voice_engine"):
		try:
			from huf.ai.voice import get_engine_class

			engine_class = get_engine_class(agent_doc.get("voice_engine"))
			engine_capabilities = engine_class.capabilities()
		except Exception:
			# Engine key not resolvable (e.g. unregistered/misconfigured) --
			# validate_app_capabilities already covers the "not set at all"
			# case as a hard error; here we simply skip the informational
			# warning rather than blocking the save on a lookup failure.
			engine_capabilities = None

		if engine_capabilities is not None and not engine_capabilities.get("memory", True):
			warnings.append(
				"Live voice for this App will not have access to Agent memory "
				"(known platform limitation, see huf/ai/voice/README.md)."
			)

	return warnings
