# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Large-result context exclusion regression tests.

These tests are placeholders for Step 3 (Result/Context Foundation V1).
They document the expected contract now and will be filled in once the
``Agent Execution Result`` store and bounded read paths are implemented.
"""

import unittest

from frappe.tests import IntegrationTestCase


class TestResultContextExclusion(IntegrationTestCase):
    """Result payloads must stay outside Agent Message and model context."""

    @unittest.skip("Step 3: implement Agent Execution Result store")
    def test_large_result_stored_outside_message_content(self):
        """A result larger than max_context_chars is stored outside Agent Message.content."""
        # TODO(Step 3): create a tool result exceeding max_context_chars, route it
        # through results.store.persist_result, and assert the Agent Message content
        # is a bounded envelope/reference rather than the raw payload.
        pass

    @unittest.skip("Step 3: implement include_reference history projection")
    def test_include_reference_does_not_return_full_payload(self):
        """get_conversation_history does not return the full raw payload for include_reference."""
        # TODO(Step 3): persist a large result with context_policy="include_reference"
        # and assert get_conversation_history returns only the compact handle/envelope.
        pass

    @unittest.skip("Step 3: implement result_read permission checks")
    def test_unauthorized_result_read_rejected(self):
        """Unauthorized result_read calls are rejected."""
        # TODO(Step 3): create a result owned by one user and assert another user
        # cannot read it through the whitelisted result_read API.
        pass
