import unittest
from unittest.mock import patch

import frappe

from huf.ai.agent import integration


class TestEffectiveSolution(unittest.TestCase):
	def test_none_stays_none(self):
		self.assertIsNone(integration._effective_solution(None))
		self.assertIsNone(integration._effective_solution(""))

	def test_unknown_solution_is_ignored(self):
		with patch.object(frappe.db, "exists", return_value=False):
			self.assertIsNone(integration._effective_solution("NOPE"))

	def test_internal_caller_keeps_existing_solution(self):
		with patch.object(frappe, "form_dict", frappe._dict()), patch.object(frappe.db, "exists", return_value=True):
			self.assertEqual(integration._effective_solution("SOL-1"), "SOL-1")

	def test_http_supplied_solution_is_ignored(self):
		with patch.object(frappe, "form_dict", frappe._dict(solution="SOL-1")), patch.object(frappe.db, "exists", return_value=True):
			self.assertIsNone(integration._effective_solution("SOL-1"))
