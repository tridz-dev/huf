# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import unittest
from unittest import mock


class TestExternalAgentConnection(unittest.TestCase):
	def test_module_imports(self):
		from huf.huf.doctype.external_agent_connection import external_agent_connection as module

		self.assertTrue(hasattr(module, "ExternalAgentConnection"))
		self.assertTrue(callable(module.get_active_connection))

	def test_get_active_connection_queries_enabled_connection(self):
		from huf.huf.doctype.external_agent_connection import external_agent_connection as module

		self.assertTrue(callable(module.get_active_connection))
		with mock.patch.object(module.frappe.db, "get_value", return_value="CONN-0001") as get_value:
			result = module.get_active_connection("user@example.com", "Support Agent")

		self.assertEqual(result, "CONN-0001")
		get_value.assert_called_once_with(
			"External Agent Connection",
			{"user": "user@example.com", "agent": "Support Agent", "enabled": 1},
			"name",
		)
