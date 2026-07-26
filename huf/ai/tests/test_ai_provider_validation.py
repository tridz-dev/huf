# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for AI Provider doctype validation (P1) and the atomic Agent run-stats
update (P3).

Covers:
- Local provider (is_local_llm) saves without an API key; the key defaults
  to "not-needed" for legacy readers.
- Local provider without api_base_url or url throws.
- Cloud provider without an API key throws.
- Provider names containing whitespace throw (the name becomes the LiteLLM
  model routing prefix).
- _update_agent_run_stats issues a single atomic UPDATE that does not bump
  `modified`, and swallows TimestampMismatchError / generic DB errors so a
  stats failure never fails a user run.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_ai_provider_validation
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase



def _get_update_agent_run_stats():
    # Lazy import: huf.ai.agent_integration requires an initialized frappe
    # site context at module import time (frappe.logger), which the test
    # runner's discovery phase does not provide.
    from huf.ai.agent_integration import _update_agent_run_stats
    return _update_agent_run_stats


class TestAIProviderValidation(FrappeTestCase):
    created_providers = []

    def tearDown(self):
        for name in self.created_providers:
            frappe.db.delete("AI Provider", name)
        self.created_providers = []

    def _make_provider(self, **fields):
        doc = frappe.get_doc(
            {
                "doctype": "AI Provider",
                "provider_name": fields.pop("provider_name"),
                "provider_brand": fields.pop("provider_brand", "openai"),
                **fields,
            }
        )
        doc.insert(ignore_permissions=True)
        self.created_providers.append(doc.name)
        return doc

    def test_local_provider_without_api_key_saves_with_default(self):
        doc = self._make_provider(
            provider_name="OllamaValidationTest",
            provider_brand="ollama",
            is_local_llm=1,
            api_base_url="http://host.docker.internal:11434",
        )
        self.assertEqual(doc.get_password("api_key"), "not-needed")

    def test_local_provider_with_legacy_url_saves(self):
        doc = self._make_provider(
            provider_name="OllamaLegacyURLTest",
            provider_brand="ollama",
            is_local_llm=1,
            url="http://host.docker.internal",
            port=11434,
        )
        self.assertEqual(doc.get_password("api_key"), "not-needed")

    def test_local_provider_without_any_endpoint_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_provider(
                provider_name="OllamaNoEndpointTest",
                provider_brand="ollama",
                is_local_llm=1,
            )

    def test_cloud_provider_without_api_key_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_provider(
                provider_name="OpenAINoKeyTest",
                provider_brand="openai",
                is_local_llm=0,
            )

    def test_provider_name_with_whitespace_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_provider(
                provider_name="Ollama LocalSpace Test",
                provider_brand="ollama",
                is_local_llm=1,
                api_base_url="http://host.docker.internal:11434",
            )


class TestUpdateAgentRunStats(FrappeTestCase):
    def _mock_frappe(self):
        mock_frappe = MagicMock()
        # The except clause needs the real exception class.
        mock_frappe.TimestampMismatchError = frappe.TimestampMismatchError
        mock_frappe.db.count.return_value = 3
        mock_frappe.db.get_value.return_value = "2026-07-26 10:00:00"
        return mock_frappe

    def test_uses_single_atomic_update_without_modified_bump(self):
        mock_frappe = self._mock_frappe()
        with patch("huf.ai.agent_integration.frappe", mock_frappe):
            _get_update_agent_run_stats()("Test Agent")

        mock_frappe.db.sql.assert_called_once()
        stmt, params = mock_frappe.db.sql.call_args[0]
        self.assertIn("UPDATE `tabAgent`", stmt)
        self.assertNotIn("modified", stmt)
        self.assertEqual(params, (3, "2026-07-26 10:00:00", "Test Agent"))
        mock_frappe.db.set_value.assert_not_called()

    def test_swallows_generic_db_error(self):
        mock_frappe = self._mock_frappe()
        mock_frappe.db.sql.side_effect = Exception("boom")
        with patch("huf.ai.agent_integration.frappe", mock_frappe):
            _get_update_agent_run_stats()("Test Agent")  # must not raise

    def test_swallows_timestamp_mismatch(self):
        mock_frappe = self._mock_frappe()
        mock_frappe.db.sql.side_effect = frappe.TimestampMismatchError("Test Agent")
        with patch("huf.ai.agent_integration.frappe", mock_frappe):
            _get_update_agent_run_stats()("Test Agent")  # must not raise
