# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json
import os
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.acp_command_registry.acp_command_registry import ACPCommandRegistry


class TestACPCommandRegistry(IntegrationTestCase):
    def test_valid_registry_passes_validation(self):
        doc = frappe.get_doc({
            "doctype": "ACP Command Registry",
            "registry_name": "test-valid-registry",
            "binary_path": "/bin/sh",
            "argv_shape": json.dumps(["-c"]),
            "working_directory": os.path.dirname(__file__),
            "auth_required": 0,
        })
        doc.insert()
        self.assertTrue(doc.name)

    def test_rejects_relative_binary_path(self):
        doc = frappe.get_doc({
            "doctype": "ACP Command Registry",
            "registry_name": "test-relative-binary",
            "binary_path": "./kimi",
            "argv_shape": json.dumps(["acp"]),
            "working_directory": os.path.dirname(__file__),
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_non_string_argv(self):
        doc = frappe.get_doc({
            "doctype": "ACP Command Registry",
            "registry_name": "test-bad-argv",
            "binary_path": "/bin/sh",
            "argv_shape": json.dumps(["acp", 123]),
            "working_directory": os.path.dirname(__file__),
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_bad_auth_env_key(self):
        doc = frappe.get_doc({
            "doctype": "ACP Command Registry",
            "registry_name": "test-bad-env-key",
            "binary_path": "/bin/sh",
            "argv_shape": json.dumps(["acp"]),
            "working_directory": os.path.dirname(__file__),
            "auth_required": 1,
            "auth_env_key": "LD_PRELOAD",
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_get_launch_spec(self):
        doc = frappe.get_doc({
            "doctype": "ACP Command Registry",
            "registry_name": "test-launch-spec",
            "binary_path": "/bin/sh",
            "argv_shape": json.dumps(["-c"]),
            "working_directory": os.path.dirname(__file__),
            "auth_required": 1,
            "auth_env_key": "HUF_ACP_TARGET_TOKEN",
            "max_wall_time_seconds": 120,
        })
        test_secret = "secret123"  # noqa: S105
        spec = doc.get_launch_spec(auth_secret=test_secret)
        self.assertEqual(spec["cmd"], ["/bin/sh", "-c"])
        self.assertEqual(spec["cwd"], os.path.dirname(__file__))
        self.assertEqual(spec["auth_env_key"], "HUF_ACP_TARGET_TOKEN")
        self.assertEqual(spec["auth_secret"], test_secret)
        self.assertEqual(spec["max_wall_time_seconds"], 120)


if __name__ == "__main__":
    unittest.main()
