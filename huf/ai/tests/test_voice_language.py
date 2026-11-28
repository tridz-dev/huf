import unittest

from huf.ai.voice.language import (
	language_label,
	normalize_voice_language,
	reply_language_instruction,
	stt_language_hint,
	transcription_prompt,
)


class TestVoiceLanguage(unittest.TestCase):
	def test_auto_is_default(self):
		for v in (None, "", "  ", "auto", "Auto-detect"):
			self.assertEqual((normalize_voice_language(v)), (""))
			self.assertIsNone(stt_language_hint(v))
		self.assertIn(("Detect the spoken language"), (transcription_prompt(None)))
		self.assertIn(("same language and script"), (reply_language_instruction("")))

	def test_override_hint_and_label(self):
		self.assertEqual((stt_language_hint("ml")), ("ml"))
		self.assertEqual((stt_language_hint("ml-IN")), ("ml"))
		self.assertEqual((stt_language_hint("Malayalam")), ("ml"))
		self.assertIsNone(stt_language_hint("some odd dialect of nowhere"))
		self.assertEqual((language_label("ml")), ("Malayalam"))
		self.assertIn(("Malayalam"), (transcription_prompt("ml")))
		self.assertIn(("always reply in Malayalam"), (reply_language_instruction("ml")))

	def test_prompt_never_translates(self):
		self.assertIn(("never translate"), (transcription_prompt("ta")))
