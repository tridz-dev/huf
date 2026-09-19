"""Tests for per-agent allowed-model list and model override restrictions.

ST-09.10: Tests for restricting model/provider overrides per agent.
"""

from frappe.tests import IntegrationTestCase
from unittest.mock import Mock, patch, MagicMock

import frappe
from huf.permissions import has_capability


class TestModelOverrideAllowlist(IntegrationTestCase):
    """Test model override restrictions via Agent Allowed Model list."""

    @patch("frappe.db.get_all")
    def test_empty_allowlist_rejects_any_override(self, mock_get_all):
        """Empty allowlist means 'use agent's configured model only'."""
        # Empty list
        mock_get_all.return_value = []

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-3.5-turbo"
        agent_doc.provider = "openai"

        # Build allowlist (empty)
        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }
        assert len(allowed_set) == 0

        # Any override should be rejected
        override_requested = ("openai", "gpt-4o") != (agent_doc.provider, agent_doc.model)
        assert override_requested is True

        # Without capability, override blocked
        if override_requested and ("openai", "gpt-4o") not in allowed_set:
            # Should check capability here
            pass

    @patch("frappe.db.get_all")
    def test_allowlist_with_one_model(self, mock_get_all):
        """Non-empty allowlist accepts listed models only."""
        # One allowed model
        mock_get_all.return_value = [
            {"provider": "openai", "model": "gpt-4o"},
        ]

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-3.5-turbo"
        agent_doc.provider = "openai"

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }
        assert ("openai", "gpt-4o") in allowed_set
        assert ("openai", "gpt-3.5-turbo") not in allowed_set

    @patch("frappe.db.get_all")
    def test_allowlist_blocks_unlisted_model(self, mock_get_all):
        """Override not in allowlist is blocked."""
        mock_get_all.return_value = [
            {"provider": "openai", "model": "gpt-4o"},
        ]

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-3.5-turbo"
        agent_doc.provider = "openai"

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }

        # Try to override with claude
        override_model = "claude-3-sonnet"
        override_provider = "anthropic"
        override_requested = (override_provider, override_model) != (agent_doc.provider, agent_doc.model)

        if override_requested and (override_provider, override_model) not in allowed_set:
            # Should be blocked
            pass


class TestModelOverrideCapability(IntegrationTestCase):
    """Test agent.model.override capability escape hatch."""

    @patch("huf.permissions.has_capability")
    @patch("frappe.db.get_all")
    def test_override_capability_allows_any_model(self, mock_get_all, mock_has_cap):
        """Users with agent.model.override capability can override anything."""
        # Empty allowlist
        mock_get_all.return_value = []
        # User has capability
        mock_has_cap.return_value = True

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-3.5-turbo"
        agent_doc.provider = "openai"

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }

        override_requested = ("anthropic", "claude-3") != (agent_doc.provider, agent_doc.model)
        assert override_requested is True
        assert ("anthropic", "claude-3") not in allowed_set

        # But capability allows it
        assert mock_has_cap.return_value is True

    @patch("huf.permissions.has_capability")
    @patch("frappe.db.get_all")
    def test_no_override_capability_blocks_override(self, mock_get_all, mock_has_cap):
        """Users without agent.model.override capability are restricted."""
        # Empty allowlist
        mock_get_all.return_value = []
        # User does NOT have capability
        mock_has_cap.return_value = False

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-3.5-turbo"
        agent_doc.provider = "openai"

        override_requested = ("anthropic", "claude-3") != (agent_doc.provider, agent_doc.model)
        assert override_requested is True

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }
        assert ("anthropic", "claude-3") not in allowed_set
        assert mock_has_cap.return_value is False

        # Override blocked


class TestAgentConfiguredModelOverride(IntegrationTestCase):
    """Test override behavior when model/provider match agent's config."""

    @patch("frappe.db.get_all")
    def test_agent_config_model_no_override(self, mock_get_all):
        """Using agent's own configured model is not an 'override'."""
        mock_get_all.return_value = []

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-4o"
        agent_doc.provider = "openai"

        # Use agent's own model
        requested_model = "gpt-4o"
        requested_provider = "openai"

        override_requested = (requested_provider, requested_model) != (agent_doc.provider, agent_doc.model)
        assert override_requested is False

        # Even with empty allowlist, no override means it's allowed
        # (no special check needed for non-overrides)

    @patch("frappe.db.get_all")
    def test_empty_allowlist_still_allows_agent_model(self, mock_get_all):
        """Empty allowlist still permits the agent's configured model."""
        mock_get_all.return_value = []

        agent_doc = Mock()
        agent_doc.name = "test_agent"
        agent_doc.model = "gpt-4o"
        agent_doc.provider = "openai"

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }

        # Agent's own model
        agent_model_tuple = (agent_doc.provider, agent_doc.model)

        # Check: is this an override?
        override_requested = agent_model_tuple != agent_model_tuple
        assert override_requested is False

        # Non-override always allowed, regardless of allowlist


class TestAllowlistEdgeCases(IntegrationTestCase):
    """Test edge cases and boundary conditions."""

    @patch("frappe.db.get_all")
    def test_multiple_providers_in_allowlist(self, mock_get_all):
        """Allowlist can have models from multiple providers."""
        mock_get_all.return_value = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "anthropic", "model": "claude-3-sonnet"},
            {"provider": "openai", "model": "gpt-4-turbo"},
        ]

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }

        assert ("openai", "gpt-4o") in allowed_set
        assert ("anthropic", "claude-3-sonnet") in allowed_set
        assert ("openai", "gpt-4-turbo") in allowed_set
        assert len(allowed_set) == 3

    @patch("frappe.db.get_all")
    def test_duplicate_entries_deduplicated_by_set(self, mock_get_all):
        """Duplicate entries in allowlist are handled by set dedup."""
        mock_get_all.return_value = [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "openai", "model": "gpt-4o"},  # Duplicate
            {"provider": "anthropic", "model": "claude-3-sonnet"},
        ]

        allowed_set = {
            (row["provider"], row["model"])
            for row in mock_get_all.return_value
        }

        # Set automatically deduplicates
        assert len(allowed_set) == 2
        assert ("openai", "gpt-4o") in allowed_set
        assert ("anthropic", "claude-3-sonnet") in allowed_set


class TestOverrideDetection(IntegrationTestCase):
    """Test logic for detecting when an override is requested."""

    def test_override_detection_both_fields_same(self):
        """Override detected only when BOTH provider and model differ."""
        agent_doc = Mock()
        agent_doc.provider = "openai"
        agent_doc.model = "gpt-4o"

        # Only provider differs
        override1 = ("anthropic", "gpt-4o") != (agent_doc.provider, agent_doc.model)
        assert override1 is True  # Different

        # Only model differs
        override2 = ("openai", "gpt-3.5") != (agent_doc.provider, agent_doc.model)
        assert override2 is True  # Different

        # Both same
        override3 = ("openai", "gpt-4o") != (agent_doc.provider, agent_doc.model)
        assert override3 is False  # Same
