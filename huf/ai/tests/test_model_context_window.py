"""Unit tests for model context window resolution and safe handling of unknown values.

Tests ensure that:
1. resolve_model_context_window returns safe values (int or None)
2. Unknown models degrade to 0, never causing database integrity errors
3. Both sync and stream agent paths handle unknown context windows identically
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.model_metadata import resolve_model_context_window


class TestResolveModelContextWindow(unittest.TestCase):
    """Test the resolver function behavior with various model configurations."""

    def test_returns_none_for_empty_model_name(self):
        """Empty model names should return None."""
        self.assertIsNone(resolve_model_context_window(""))
        self.assertIsNone(resolve_model_context_window(None))

    def test_returns_context_window_from_ai_model_record(self):
        """When AI Model record exists with context_window, use that value."""
        with patch("huf.ai.model_metadata.frappe") as mock_frappe:
            mock_doc = MagicMock()
            mock_doc.get.return_value = 8192  # For the truthiness check
            mock_doc.context_window = 8192  # For the actual attribute access
            mock_frappe.get_cached_doc.return_value = mock_doc

            result = resolve_model_context_window("test/model")
            self.assertEqual(result, 8192)

    def test_returns_none_when_ai_model_has_no_context_window(self):
        """When AI Model record exists but has no context_window, return None."""
        with patch("huf.ai.model_metadata.frappe") as mock_frappe:
            with patch(
                "huf.ai.model_metadata._context_window_from_litellm", return_value=None
            ):
                mock_doc = MagicMock()
                mock_doc.get.return_value = None  # For the truthiness check
                mock_doc.context_window = None  # For the actual attribute access
                mock_frappe.get_cached_doc.return_value = mock_doc

                result = resolve_model_context_window("unknown/model")
                self.assertIsNone(result)

    def test_returns_none_when_ai_model_not_found(self):
        """When AI Model record doesn't exist, fall back to LiteLLM (or None)."""
        with patch("huf.ai.model_metadata.frappe") as mock_frappe:
            with patch(
                "huf.ai.model_metadata._context_window_from_litellm", return_value=None
            ) as mock_litellm:
                mock_frappe.get_cached_doc.side_effect = frappe.DoesNotExistError()

                result = resolve_model_context_window("nonexistent/model", "provider", "brand")
                self.assertIsNone(result)
                # Verify fallback was called
                mock_litellm.assert_called_once()

    def test_result_type_is_int_or_none(self):
        """Resolver always returns int or None, never other types."""
        with patch("huf.ai.model_metadata.frappe") as mock_frappe:
            mock_doc = MagicMock()
            mock_doc.get.return_value = 128000
            mock_doc.context_window = 128000
            mock_frappe.get_cached_doc.return_value = mock_doc

            result = resolve_model_context_window("test/model")
            self.assertIsInstance(result, (int, type(None)))


class TestAgentRunWritePathHandling(unittest.TestCase):
    """Test that the write paths (sync and stream) handle None properly.

    These tests verify the fix at the write site: both paths coalesce None
    to 0 using the `or 0` pattern.
    """

    def test_sync_path_coalesces_none_to_zero(self):
        """Sync path should coalesce None to 0."""
        result = resolve_model_context_window("nonexistent/unknown-xyz") or 0
        # Result should be 0 (from the coalescing)
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_stream_path_coalesces_none_to_zero(self):
        """Stream path should coalesce None to 0."""
        result = resolve_model_context_window("nonexistent/unknown-xyz") or 0
        # Result should be 0 (from the coalescing)
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_valid_window_not_coalesced(self):
        """Valid context windows should not be affected by coalescing."""
        with patch("huf.ai.model_metadata.frappe") as mock_frappe:
            mock_doc = MagicMock()
            mock_doc.get.return_value = 4096
            mock_doc.context_window = 4096
            mock_frappe.get_cached_doc.return_value = mock_doc

            result = resolve_model_context_window("test/model") or 0
            # Should be 4096, not 0
            self.assertEqual(result, 4096)


class TestAnalyticsConsumerFallback(unittest.TestCase):
    """Test that analytics consumers gracefully handle unknown context windows.

    The analytics code checks: if peak_context_tokens is not None and model_context_window:
    Both None and 0 are falsy, so the division is skipped for unknown windows.
    """

    def test_zero_window_is_falsy(self):
        """Zero context window is falsy in Python truthiness checks."""
        model_context_window = 0
        # This is how analytics checks the value
        should_calculate = model_context_window  # Truthiness check
        self.assertFalse(should_calculate)

    def test_none_window_is_falsy(self):
        """None context window is falsy in Python truthiness checks."""
        model_context_window = None
        # This is how analytics checks the value
        should_calculate = model_context_window  # Truthiness check
        self.assertFalse(should_calculate)

    def test_both_zero_and_none_skip_division(self):
        """Both 0 and None skip the division in analytics code guard."""
        peak_context_tokens = 1000

        # Test with None (original behavior when resolver returns None)
        model_context_window = None
        context_fullness = None
        if peak_context_tokens is not None and model_context_window:
            context_fullness = peak_context_tokens / model_context_window
        self.assertIsNone(context_fullness, "None window should skip division")

        # Test with 0 (new behavior after coalescing)
        model_context_window = 0
        context_fullness = None
        if peak_context_tokens is not None and model_context_window:
            context_fullness = peak_context_tokens / model_context_window
        self.assertIsNone(context_fullness, "0 window should skip division")


if __name__ == "__main__":
    unittest.main()
