"""Unit tests for huf.ai.capabilities.actions (action capability discovery)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.capabilities.actions import (
    _iter_app_api_module_paths,
    _iter_module_function_paths,
    declared_actions_for_app,
    describe_app_action,
    discover_whitelisted_actions_for_app,
    search_app_actions,
)
from huf.ai.capabilities.models import build_capability_id, make_capability_descriptor

TEST_APP = "capability-discovery-test-app"
REAL_APP = "huf"


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
            "tool_name": f"test_tool_{suffix}",
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
        tool = self._make_tool(tool_name="unique_searchable_widget")

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


class TestZeroConfigDiscovery(IntegrationTestCase):
    """Tests for the filesystem/import-based discovery surfaces, run against the REAL
    "huf" app (the fake TEST_APP string isn't a real installed app, so it can't be used
    for these filesystem/import-based checks).
    """

    def setUp(self):
        frappe.set_user("Administrator")

    def test_iter_app_api_module_paths_finds_real_module(self):
        module_paths = list(_iter_app_api_module_paths(REAL_APP))

        self.assertIn("huf.ai.capabilities.api", module_paths)
        self.assertFalse(
            any(".tests." in path for path in module_paths),
            "no module path should come from a 'tests' directory",
        )

    def test_iter_app_api_module_paths_empty_for_unknown_app(self):
        self.assertEqual(list(_iter_app_api_module_paths("no-such-app-xyz")), [])

    def test_iter_module_function_paths_finds_real_function_excludes_underscored(self):
        function_paths = list(_iter_module_function_paths("huf.ai.capabilities.api"))

        self.assertIn("huf.ai.capabilities.api.search_app_actions", function_paths)
        self.assertIn("huf.ai.capabilities.api.describe_app_action", function_paths)
        # Underscore-prefixed helpers defined in this module must be excluded.
        self.assertFalse(any(p.split(".")[-1].startswith("_") for p in function_paths))
        self.assertNotIn("huf.ai.capabilities.api._require_capability_discovery_access", function_paths)
        self.assertNotIn("huf.ai.capabilities.api._coerce_bool", function_paths)

    def test_discover_whitelisted_actions_for_app_surfaces_zero_config_function(self):
        # Cross-reference huf_tools-declared function_paths against a real api.py module
        # to prove huf.ai.capabilities.api.search_app_actions has NO huf_tools declaration
        # (i.e. declared_actions_for_app / huf_tools scanning alone would never surface it),
        # so its presence below proves the new zero-config discovery path is doing real work.
        from huf.ai.tool_registry import _normalize_hook_tools

        declared_paths = set()
        for hook_entry in frappe.get_hooks("huf_tools", app_name=REAL_APP) or []:
            for tool_def in _normalize_hook_tools(hook_entry):
                function_path = (tool_def or {}).get("function_path")
                if function_path:
                    declared_paths.add(function_path)

        target_function_path = "huf.ai.capabilities.api.search_app_actions"
        self.assertNotIn(
            target_function_path,
            declared_paths,
            "test fixture assumption broken: this function is now huf_tools-declared",
        )

        descriptors = discover_whitelisted_actions_for_app(REAL_APP)

        matches = [d for d in descriptors if d.get("function_path") == target_function_path]
        self.assertEqual(len(matches), 1)
        descriptor = matches[0]
        self.assertEqual(descriptor["source_type"], "framework_discovered")
        self.assertEqual(descriptor["kind"], "action")
        self.assertEqual(descriptor["source_app"], REAL_APP)

    def test_describe_app_action_finds_discovered_action_beyond_search_limit(self):
        # search_app_actions defaults to limit=50, and declared descriptors are always
        # sorted first in the merge -- huf has 100+ huf_tools-declared actions, so a
        # naive describe_app_action(search_app_actions(app, query="")) would never reach
        # any framework-discovered action. describe_app_action must look these up directly
        # (declared_actions_for_app / discover_whitelisted_actions_for_app), not through
        # the limit-truncated search results.
        target_function_path = "huf.ai.capabilities.api.search_app_actions"
        capability_id = build_capability_id("action", REAL_APP, target_function_path)

        search_results = search_app_actions(REAL_APP, query="")
        self.assertNotIn(
            target_function_path,
            {d.get("function_path") for d in search_results},
            "test fixture assumption broken: this function now fits within the default search limit",
        )

        descriptor = describe_app_action(capability_id)

        self.assertEqual(descriptor["id"], capability_id)
        self.assertEqual(descriptor["function_path"], target_function_path)
        self.assertEqual(descriptor["source_type"], "framework_discovered")
