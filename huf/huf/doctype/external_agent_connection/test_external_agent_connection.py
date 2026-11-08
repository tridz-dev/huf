# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import unittest


class TestExternalAgentConnection(unittest.TestCase):
	def test_module_imports(self):
		from huf.huf.doctype.external_agent_connection import external_agent_connection as module

		self.assertTrue(hasattr(module, "ExternalAgentConnection"))
		self.assertTrue(callable(module.get_active_connection))
