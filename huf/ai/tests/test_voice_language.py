from huf.ai.voice.language import (
	language_label,
	normalize_voice_language,
	reply_language_instruction,
	stt_language_hint,
	transcription_prompt,
)


def test_auto_is_default():
	for v in (None, "", "  ", "auto", "Auto-detect"):
		assert normalize_voice_language(v) == ""
		assert stt_language_hint(v) is None
	assert "Detect the spoken language" in transcription_prompt(None)
	assert "same language and script" in reply_language_instruction("")


def test_override_hint_and_label():
	assert stt_language_hint("ml") == "ml"
	assert stt_language_hint("ml-IN") == "ml"
	assert stt_language_hint("Malayalam") == "ml"
	assert stt_language_hint("some odd dialect of nowhere") is None
	assert language_label("ml") == "Malayalam"
	assert "Malayalam" in transcription_prompt("ml")
	assert "always reply in Malayalam" in reply_language_instruction("ml")


def test_prompt_never_translates():
	assert "never translate" in transcription_prompt("ta")
