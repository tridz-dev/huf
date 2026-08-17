# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.agent_tool_function.agent_tool_function import (
    get_function_metadata,
    inspect_function_parameters,
    resolve_function_descriptor,
)

# A real whitelisted function in this codebase.
WHITELISTED_FUNCTION_PATH = (
    "huf.huf.doctype.agent_tool_function.agent_tool_function.fetch_tool_parameters_from_code"
)

# A real plain helper in the same module that is NOT decorated with
# @frappe.whitelist().
NON_WHITELISTED_FUNCTION_PATH = (
    "huf.huf.doctype.agent_tool_function.agent_tool_function._annotation_to_param_type"
)


def _sample(a, b=5):
    pass


class TestGetFunctionMetadata(IntegrationTestCase):
    def test_whitelisted_function_metadata(self):
        metadata = get_function_metadata(WHITELISTED_FUNCTION_PATH)

        self.assertTrue(metadata["is_whitelisted"])
        self.assertEqual(metadata["function_name"], "fetch_tool_parameters_from_code")
        self.assertEqual(
            metadata["module"],
            "huf.huf.doctype.agent_tool_function.agent_tool_function",
        )

    def test_require_whitelisted_raises_for_non_whitelisted_function(self):
        with self.assertRaises(frappe.PermissionError):
            get_function_metadata(NON_WHITELISTED_FUNCTION_PATH, require_whitelisted=True)

    def test_non_whitelisted_function_metadata_without_requirement(self):
        # Without require_whitelisted, resolving a non-whitelisted function should
        # succeed and simply report is_whitelisted=False.
        metadata = get_function_metadata(NON_WHITELISTED_FUNCTION_PATH)

        self.assertFalse(metadata["is_whitelisted"])
        self.assertEqual(metadata["function_name"], "_annotation_to_param_type")


class TestResolveFunctionDescriptor(IntegrationTestCase):
    def test_bogus_dotted_path_raises_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            resolve_function_descriptor("huf.nonexistent.module.fn")


class TestInspectFunctionParameters(IntegrationTestCase):
    def test_infers_required_and_optional_parameters(self):
        parameters = inspect_function_parameters(_sample)

        by_fieldname = {p["fieldname"]: p for p in parameters}

        self.assertEqual(set(by_fieldname.keys()), {"a", "b"})
        self.assertEqual(by_fieldname["a"]["required"], 1)
        self.assertEqual(by_fieldname["b"]["required"], 0)
