"""Guards for the permission_query_conditions hook mapping."""
import ast
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.huf.doctype.agent_procedure_run import agent_procedure_run as apr


def _hooks_keys():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "hooks.py")
    with open(path) as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "permission_query_conditions" for t in node.targets
        ):
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)], node.value
    raise AssertionError("permission_query_conditions not found")


class TestHooksPermissionConditions(unittest.TestCase):
    def test_no_duplicate_keys(self):
        keys, _ = _hooks_keys()
        dupes = {k for k in keys if keys.count(k) > 1}
        self.assertFalse(dupes, f"duplicate permission_query_conditions keys: {dupes}")

    def test_procedure_run_mapped_to_doctype_function(self):
        _, node = _hooks_keys()
        mapping = {k.value: v.value for k, v in zip(node.keys, node.values)}
        self.assertEqual(
            mapping["Agent Procedure Run"],
            "huf.huf.doctype.agent_procedure_run.agent_procedure_run.get_permission_query_conditions",
        )

    def test_normal_user_scoped_to_owner(self):
        with patch.object(apr.frappe, "get_roles", return_value=["Huf User"]), patch(
            "huf.permissions.has_capability", return_value=False
        ), patch.object(
            apr.frappe, "db", SimpleNamespace(escape=lambda v: f"'{v}'"), create=True
        ):
            result = apr.get_permission_query_conditions("alice@example.com")
        self.assertEqual(result, "`tabAgent Procedure Run`.owner = 'alice@example.com'")

    def test_administrator_unrestricted(self):
        with patch.object(apr.frappe, "get_roles", return_value=["System Manager"]):
            self.assertIsNone(apr.get_permission_query_conditions("Administrator"))
