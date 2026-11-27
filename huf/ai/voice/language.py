"""Spoken-language handling for voice agents.

Default is auto-detect: the transcript keeps the spoken language and script and
the reply uses it. ``Agent.voice_language`` (empty = auto) optionally overrides
both the speech-to-text hint and the reply language.
"""

from __future__ import annotations

_NAMES = {
	"en": "English",
	"es": "Spanish",
	"fr": "French",
	"de": "German",
	"hi": "Hindi",
	"ta": "Tamil",
	"ml": "Malayalam",
	"te": "Telugu",
	"kn": "Kannada",
	"mr": "Marathi",
	"bn": "Bengali",
	"gu": "Gujarati",
	"pa": "Punjabi",
	"ur": "Urdu",
	"ar": "Arabic",
	"pt": "Portuguese",
	"it": "Italian",
	"ru": "Russian",
	"ja": "Japanese",
	"ko": "Korean",
	"zh": "Chinese",
	"id": "Indonesian",
	"tr": "Turkish",
	"nl": "Dutch",
}

_MAX_LEN = 40


def normalize_voice_language(value) -> str:
	"""Return the cleaned override ('' when unset/auto)."""
	text = value.strip() if isinstance(value, str) else ""
	if text.lower() in {"auto", "auto-detect", "autodetect"}:
		return ""
	return text[:_MAX_LEN]


def _base(text: str) -> str:
	return text.lower().split("-")[0].split("_")[0]


def language_label(value) -> str:
	"""Human name for a code ('ml' -> 'Malayalam'); free text passes through."""
	text = normalize_voice_language(value)
	if len(text) <= 8:
		return _NAMES.get(_base(text), text)
	return text


def stt_language_hint(value) -> str | None:
	"""ISO code for providers that take a ``language`` parameter, else None."""
	text = normalize_voice_language(value)
	if not text:
		return None
	base = _base(text)
	if len(text) <= 8 and len(base) in (2, 3) and base.isalpha():
		return base
	for code, name in _NAMES.items():
		if name.lower() == text.lower():
			return code
	return None


def transcription_prompt(value) -> str:
	"""Prompt for multimodal (Gemini-style) STT."""
	base = (
		"Please transcribe this audio exactly as it is spoken. Do not add any extra "
		"commentary or formatting. Keep each language in the script it was spoken in; "
		"never translate or transliterate. If it is silent, just write [Silence]."
	)
	label = language_label(value)
	if label:
		return base + f" The speaker is expected to be speaking {label}."
	return base + " Detect the spoken language automatically."


def reply_language_instruction(value) -> str:
	"""System-prompt addition for the reply language of voice conversations."""
	label = language_label(value)
	if label:
		return f"For voice conversations, always reply in {label}, regardless of the language the user spoke."
	return (
		"For voice conversations, reply in the same language and script the user spoke, "
		"and never translate the user's words into another language."
	)
