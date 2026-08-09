"""Unit tests for huf.ai.capabilities.actions (action capability discovery)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.capabilities.actions import (
    declared_actions_for_app,
    describe_app_action,
    search_app_actions,
)
from huf.ai.capabilities.models import build_capability_id, make_capability_descriptor

TEST_APP = "capability-discovery-test-app"


class TestCapabilityActions(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._tool_names = []

    def tearDown(self):
        for name in self._tool_names:
            if frappe.db.exists("Agent Tool Function", name):
                frappe.delete_doc("Agent Tool Function", name, ignore_permissions=True, force=True)

    def _make_tool(self, **overrides):
        suffix = frappe.generate_hash(length=8)
        fields = {
            "doctype": "Agent Tool Function",
            "tool_name": f"Test Tool {suffix}",
            "description": "A test tool for capability discovery unit tests",
            "tool_type": "Miscellaneous",
            "types": "App Provided",
            "provider_app": TEST_APP,
            "function_path": f"huf.tests.fixtures.test_tool_{suffix}",
            "required_permission": "read",
            "is_read_only": 1,
            "allowed_for_guest": 0,
            "params": json.dumps({"type": "object", "properties": {}}),
        }
        fields.update(overrides)
        doc = frappe.get_doc(fields).insert(ignore_permissions=True)
        self._tool_names.append(doc.name)
        return doc

    def test_declared_actions_for_app_returns_descriptor(self):
        tool = self._make_tool()

        descriptors = declared_actions_for_app(TEST_APP)

        matches = [d for d in descriptors if d["source_key"] == tool.function_path]
        self.assertEqual(len(matches), 1)
        descriptor = matches[0]
        self.assertEqual(descriptor["kind"], "action")
        self.assertEqual(descriptor["source_type"], "declared")
        self.assertEqual(descriptor["source_app"], TEST_APP)
        self.assertEqual(descriptor["function_path"], tool.function_path)
        self.assertEqual(descriptor["title"], tool.tool_name)
        self.assertTrue(descriptor["read_only"])
        self.assertEqual(descriptor["id"], build_capability_id("action", TEST_APP, tool.function_path))

    def test_declared_actions_for_app_empty_for_unknown_app(self):
        self.assertEqual(declared_actions_for_app("no-such-app-xyz"), [])

    def test_search_app_actions_merges_declared_and_discovered_dedup(self):
        tool = self._make_tool()
        # A "discovered" descriptor for the SAME function_path as our declared tool -
        # search_app_actions must de-dupe these and keep the declared one.
        fake_discovered_dup = make_capability_descriptor(
            kind="action",
            source_app=TEST_APP,
            source_type="framework_discovered",
            source_key=tool.function_path,
            title="Discovered duplicate",
            function_path=tool.function_path,
            parameters_schema={},
            confidence=0.7,
        )
        # A "discovered" descriptor with no declared counterpart - should pass through.
        only_discovered = make_capability_descriptor(
            kind="action",
            source_app=TEST_APP,
            source_type="framework_discovered",
            source_key="huf.tests.fixtures.only_discovered",
            title="Only Discovered",
            function_path="huf.tests.fixtures.only_discovered",
            parameters_schema={},
            confidence=0.7,
        )

        with patch(
            "huf.ai.capabilities.actions.discover_whitelisted_actions_for_app",
            return_value=[fake_discovered_dup, only_discovered],
        ):
            results = search_app_actions(TEST_APP)

        by_path = {r["function_path"]: r for r in results}
        self.assertEqual(len(results), 2)
        self.assertIn(tool.function_path, by_path)
        self.assertEqual(by_path[tool.function_path]["source_type"], "declared")
        self.assertIn("huf.tests.fixtures.only_discovered", by_path)
        self.assertEqual(by_path["huf.tests.fixtures.only_discovered"]["source_type"], "framework_discovered")

    def test_search_app_actions_filters_by_query(self):
        tool = self._make_tool(tool_name="Unique Searchable Widget")

        with patch("huf.ai.capabilities.actions.discover_whitelisted_actions_for_app", return_value=[]):
            matched = search_app_actions(TEST_APP, query="searchable")
            unmatched = search_app_actions(TEST_APP, query="totally-unrelated-xyz-nomatch")

        self.assertTrue(any(d["function_path"] == tool.function_path for d in matched))
        self.assertEqual(unmatched, [])

    def test_describe_app_action_raises_for_unknown_id(self):
        with self.assertRaises(frappe.DoesNotExistError):
            describe_app_action(f"action:{TEST_APP}:does-not-exist")

    def test_describe_app_action_round_trip(self):
        tool = self._make_tool()
        capability_id = build_capability_id("action", TEST_APP, tool.function_path)

        with patch("huf.ai.capabilities.actions.discover_whitelisted_actions_for_app", return_value=[]):
            descriptor = describe_app_action(capability_id)

        self.assertEqual(descriptor["id"], capability_id)
        self.assertEqual(descriptor["function_path"], tool.function_path)
        self.assertEqual(descriptor["title"], tool.tool_name)
