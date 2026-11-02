import unittest

import frappe

from huf.ai.solutions import crud, handoff


class TestCrudReassignExport(unittest.TestCase):
	def test_reexported_function_is_the_handoff_one(self):
		self.assertIs(crud.reassign_conversation, handoff.reassign_conversation)

	def test_is_whitelisted(self):
		self.assertIn(crud.reassign_conversation, frappe.whitelisted)
