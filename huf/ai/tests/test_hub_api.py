# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for huf.ai.hub_api (M2 — hub readiness + provider introspection).

Covers:
- get_hub_readiness() shape with no keyed provider (ready=False + remediation)
- get_provider_status() never leaks API key material
- approve_model_proposals() creates models and is idempotent
- approve_model_proposals() rejects non-manager users
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class _LazyModule:
    """Defer heavy app imports until first use (bench run-tests discovers test
    modules before frappe.init completes on some Frappe versions; eager imports
    of app modules with module-level frappe.logger() crash discovery)."""

    def __init__(self, module_path):
        self._module_path = module_path

    def __getattr__(self, name):
        import importlib

        return getattr(importlib.import_module(self._module_path), name)


hub_api = _LazyModule("huf.ai.hub_api")

TEST_PROVIDER = "ZZ Test Hub Provider"
TEST_SECRET = "sk-hub-test-secret-0001"
OPENAI_CANDIDATE = "gpt-5.2"


def _ensure_test_provider():
    """Create a keyed AI Provider for tests (rolled back with the test case)."""
    if not frappe.db.exists("AI Provider", TEST_PROVIDER):
        frappe.get_doc({
            "doctype": "AI Provider",
            "provider_name": TEST_PROVIDER,
            "provider_brand": "openai",
            "api_key": TEST_SECRET,
        }).insert(ignore_permissions=True)


class TestHubReadiness(FrappeTestCase):
    """Readiness must report not-ready with remediation when nothing is keyed."""

    def test_readiness_shape_with_no_keyed_provider(self):
        fake_orchestrator = {"present": True, "disabled": True, "provider": None, "model": None}

        with (
            patch("huf.ai.hub_api._orchestrator_info", return_value=dict(fake_orchestrator)),
            patch("huf.ai.hub_api._provider_has_key", return_value=False),
            patch("huf.ai.hub_api._count_keyed_providers", return_value=0),
            patch("frappe.has_permission", return_value=True),
        ):
            result = hub_api.get_hub_readiness()

        # Shape
        self.assertIn("orchestrator", result)
        self.assertIn("providers_with_keys", result)
        self.assertIn("models_available", result)
        self.assertIn("ready", result)
        self.assertIn("remediation", result)

        orchestrator = result["orchestrator"]
        for key in ("present", "disabled", "provider", "model", "provider_configured"):
            self.assertIn(key, orchestrator)
        self.assertFalse(orchestrator["provider_configured"])

        # Not ready, and the user is told what to fix
        self.assertFalse(result["ready"])
        self.assertEqual(result["providers_with_keys"], 0)
        self.assertTrue(result["remediation"])

        codes = {entry["code"] for entry in result["remediation"]}
        self.assertIn("no_provider_key", codes)
        self.assertIn("orchestrator_disabled", codes)
        for entry in result["remediation"]:
            self.assertTrue(entry["message"])
            self.assertTrue(entry["action_route"])


class TestProviderStatus(FrappeTestCase):
    """get_provider_status must report configured state without leaking keys."""

    def test_provider_status_never_leaks_key_material(self):
        _ensure_test_provider()

        with patch("frappe.has_permission", return_value=True):
            rows = hub_api.get_provider_status()

        target = [r for r in rows if r["name"] == TEST_PROVIDER]
        self.assertTrue(target, "test provider must appear in provider status")
        self.assertTrue(target[0]["configured"])
        self.assertEqual(target[0]["provider_brand"], "openai")
        self.assertIn("model_count", target[0])

        for row in rows:
            self.assertNotIn("api_key", row)
            for value in row.values():
                self.assertNotEqual(value, TEST_SECRET)
                self.assertNotIn(TEST_SECRET, str(value))

        # Configured providers sort before unconfigured ones
        configured_flags = [r["configured"] for r in rows]
        self.assertEqual(configured_flags, sorted(configured_flags, reverse=True))


class TestApproveModelProposals(FrappeTestCase):
    """approve_model_proposals creates AI Model rows idempotently, manager-only."""

    def setUp(self):
        super().setUp()
        # Make sure a provider exists for the candidate's brand, and that the
        # candidate model does not already exist on this site.
        if not frappe.db.exists("AI Provider", {"provider_brand": "openai"}):
            _ensure_test_provider()
        if frappe.db.exists("AI Model", OPENAI_CANDIDATE):
            frappe.delete_doc("AI Model", OPENAI_CANDIDATE, ignore_permissions=True, force=True)

    def test_approve_creates_model_and_is_idempotent(self):
        with patch("frappe.has_permission", return_value=True):
            first = hub_api.approve_model_proposals([OPENAI_CANDIDATE])

        self.assertIn(OPENAI_CANDIDATE, first["created"])
        self.assertNotIn(OPENAI_CANDIDATE, first["skipped"])
        self.assertTrue(frappe.db.exists("AI Model", OPENAI_CANDIDATE))

        doc = frappe.get_doc("AI Model", OPENAI_CANDIDATE)
        brand = frappe.db.get_value("AI Provider", doc.provider, "provider_brand")
        self.assertEqual(brand, "openai")

        with patch("frappe.has_permission", return_value=True):
            second = hub_api.approve_model_proposals([OPENAI_CANDIDATE])
        self.assertNotIn(OPENAI_CANDIDATE, second["created"])
        self.assertIn(OPENAI_CANDIDATE, second["skipped"])

    def test_approve_skips_unknown_and_unmatched_proposals(self):
        with patch("frappe.has_permission", return_value=True):
            result = hub_api.approve_model_proposals(["not-a-catalog-model"])
        self.assertEqual(result["created"], [])
        self.assertIn("not-a-catalog-model", result["skipped"])

    def test_non_manager_cannot_approve(self):
        with patch("frappe.get_roles", return_value=["Huf User"]):
            self.assertRaises(
                frappe.PermissionError,
                hub_api.approve_model_proposals,
                [OPENAI_CANDIDATE],
            )
        self.assertFalse(frappe.db.exists("AI Model", OPENAI_CANDIDATE))
