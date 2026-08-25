# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
D15 follow-up: opt-in persistence of the assembled system prompt.

Off by default (no site_config key set); when huf_retain_system_prompts_enabled
is set, the exact text is written to a dedicated Agent Run Prompt Snapshot doc,
never onto Agent Run itself. Never raises -- a snapshot failure must never
fail the run it's describing.
"""

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.system_prompt_retention import SITE_CONFIG_KEY, is_enabled, maybe_snapshot_system_prompt


class TestSystemPromptRetention(unittest.TestCase):
    def test_disabled_by_default_writes_nothing(self):
        with patch("huf.ai.system_prompt_retention.frappe") as mock_frappe:
            mock_frappe.conf = {}
            maybe_snapshot_system_prompt("RUN-1", "agent-a", "CONV-1", "You are a helpful assistant.")
            mock_frappe.get_doc.assert_not_called()

    def test_enabled_writes_dedicated_doctype_verbatim(self):
        with patch("huf.ai.system_prompt_retention.frappe") as mock_frappe:
            mock_frappe.conf = {SITE_CONFIG_KEY: True}
            doc = MagicMock()
            mock_frappe.get_doc.return_value = doc

            maybe_snapshot_system_prompt("RUN-2", "agent-b", "CONV-2", "verbatim text")

            mock_frappe.get_doc.assert_called_once()
            (payload,), _ = mock_frappe.get_doc.call_args
            self.assertEqual(payload["doctype"], "Agent Run Prompt Snapshot")
            self.assertEqual(payload["agent_run"], "RUN-2")
            self.assertEqual(payload["agent"], "agent-b")
            self.assertEqual(payload["conversation"], "CONV-2")
            self.assertEqual(payload["system_prompt"], "verbatim text")
            doc.insert.assert_called_once_with(ignore_permissions=True)

    def test_enabled_but_no_instructions_writes_nothing(self):
        with patch("huf.ai.system_prompt_retention.frappe") as mock_frappe:
            mock_frappe.conf = {SITE_CONFIG_KEY: True}

            maybe_snapshot_system_prompt("RUN-3", "agent-c", "CONV-3", None)
            maybe_snapshot_system_prompt("RUN-3", "agent-c", "CONV-3", "")

            mock_frappe.get_doc.assert_not_called()

    def test_insert_failure_is_swallowed_not_raised(self):
        with patch("huf.ai.system_prompt_retention.frappe") as mock_frappe:
            mock_frappe.conf = {SITE_CONFIG_KEY: True}
            doc = MagicMock()
            doc.insert.side_effect = RuntimeError("db is down")
            mock_frappe.get_doc.return_value = doc

            # Must not raise -- a snapshot failure must never fail the run.
            maybe_snapshot_system_prompt("RUN-4", "agent-d", "CONV-4", "text")

            mock_frappe.log_error.assert_called_once()

    def test_is_enabled_reads_site_config_key(self):
        with patch("huf.ai.system_prompt_retention.frappe") as mock_frappe:
            mock_frappe.conf = {}
            self.assertFalse(is_enabled())

            mock_frappe.conf = {SITE_CONFIG_KEY: True}
            self.assertTrue(is_enabled())

            mock_frappe.conf = {SITE_CONFIG_KEY: False}
            self.assertFalse(is_enabled())


if __name__ == "__main__":
    unittest.main()
