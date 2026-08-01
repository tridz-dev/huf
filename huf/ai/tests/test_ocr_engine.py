"""Unit tests for OCR / document extraction engine."""

import os
import tempfile
import unittest

from huf.ai.ocr_engine import (
    _MAX_MESSAGE_TEXT_LENGTH,
    _build_agent_message_content,
    _default_model,
    _determine_strategy,
    _extract_local,
    _has_local_extractor,
    _is_pdf_by_content,
    _mime_type_and_extension,
)


class TestOCREngineUnit(unittest.TestCase):
    def test_determine_strategy_images(self):
        self.assertEqual(_determine_strategy("image/png", "png", "openai"), "vision")
        self.assertEqual(_determine_strategy("image/jpeg", "jpg", "anthropic"), "vision")
        self.assertEqual(_determine_strategy("image/webp", "webp", "google"), "vision")

    def test_determine_strategy_pdfs(self):
        # Vision-capable providers
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "google"), "vision")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "gemini"), "vision")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "vertex_ai"), "vision")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "anthropic"), "vision")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "openai"), "vision")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "openrouter"), "vision")

        # LiteLLM OCR endpoint providers
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "mistral"), "ocr")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "azure"), "ocr")

        # Fallback local PDF providers
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "ollama"), "local_pdf")
        self.assertEqual(_determine_strategy("application/pdf", "pdf", "deepseek"), "local_pdf")

    def test_determine_strategy_local_docs(self):
        self.assertEqual(_determine_strategy("text/plain", "txt", "openai"), "local")
        self.assertEqual(_determine_strategy("text/markdown", "md", "anthropic"), "local")
        self.assertEqual(_determine_strategy("text/html", "html", "google"), "local")
        self.assertEqual(
            _determine_strategy(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "docx",
                "openai",
            ),
            "local",
        )

    def test_default_model(self):
        # OCR strategy
        self.assertEqual(_default_model("mistral", "ocr"), "mistral/mistral-ocr-latest")
        self.assertEqual(_default_model("azure", "ocr"), "azure_ai/ocr")

        # Vision strategy
        self.assertEqual(_default_model("openai", "vision"), "gpt-4o")
        self.assertEqual(_default_model("google", "vision"), "gemini/gemini-2.5-flash")
        self.assertEqual(_default_model("anthropic", "vision"), "claude-3-5-sonnet-20241022")
        self.assertEqual(_default_model("openrouter", "vision"), "openrouter/google/gemini-2.5-flash")

        # Unknown provider/strategy returns None
        self.assertIsNone(_default_model("unknown_provider", "vision"))

    def test_mime_type_and_extension(self):
        mime, ext = _mime_type_and_extension("document.pdf")
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(ext, "pdf")

        # Normalize image/jpg -> image/jpeg
        mime, ext = _mime_type_and_extension("photo.jpg", file_type="image/jpg")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(ext, "jpg")

    def test_is_pdf_by_content(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.7 header content here")
            pdf_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Hello world plain text")
            txt_path = f.name

        try:
            self.assertTrue(_is_pdf_by_content(pdf_path))
            self.assertFalse(_is_pdf_by_content(txt_path))
        finally:
            os.unlink(pdf_path)
            os.unlink(txt_path)

    def test_has_local_extractor(self):
        self.assertTrue(_has_local_extractor("application/pdf", "pdf"))
        self.assertTrue(_has_local_extractor("text/plain", "txt"))
        self.assertTrue(_has_local_extractor("text/markdown", "md"))
        self.assertTrue(_has_local_extractor("text/html", "html"))
        self.assertTrue(
            _has_local_extractor(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
            )
        )
        self.assertFalse(_has_local_extractor("image/png", "png"))

    def test_extract_local_text_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("Sample extracted text for unit test")
            txt_path = f.name

        try:
            res = _extract_local(txt_path, "text/plain")
            self.assertTrue(res.success)
            self.assertIn("Sample extracted text", res.text)
            self.assertEqual(res.strategy, "local")
        finally:
            os.unlink(txt_path)

    def test_build_agent_message_content_truncation(self):
        short_text = "Short text result"
        msg_short = _build_agent_message_content("test.txt", short_text, "local", "local_extractor")
        self.assertIn(short_text, msg_short)
        self.assertNotIn("truncated", msg_short)

        long_text = "A" * (_MAX_MESSAGE_TEXT_LENGTH + 500)
        msg_long = _build_agent_message_content("big.txt", long_text, "local", "local_extractor")
        self.assertIn("truncated from", msg_long)
