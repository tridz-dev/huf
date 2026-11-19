# Copyright (c) 2026, Huf and contributors
# See license.txt

import json
import os
import unittest

from huf.huf.doctype.external_action_approval.external_action_approval import (
	ExternalActionApproval,
	is_allowed_status_transition,
)

_HERE = os.path.dirname(os.path.abspath(__file__))


class TestExternalActionApproval(unittest.TestCase):
	def test_controller_module_imports(self):
		self.assertIsNotNone(ExternalActionApproval)

	def test_pending_may_move_to_any_status(self):
		for current in ("Pending", "Approved", "Rejected", "Expired", "Consumed"):
			with self.subTest(current=current):
				self.assertTrue(is_allowed_status_transition("Pending", current))

	def test_decided_statuses_are_final(self):
		for previous in ("Rejected", "Expired", "Consumed"):
			for current in ("Pending", "Approved", "Rejected", "Expired", "Consumed"):
				if current == previous:
					continue
				with self.subTest(previous=previous, current=current):
					self.assertFalse(is_allowed_status_transition(previous, current))

	def test_approved_may_only_be_consumed(self):
		self.assertTrue(is_allowed_status_transition("Approved", "Consumed"))
		for current in ("Pending", "Rejected", "Expired"):
			with self.subTest(current=current):
				self.assertFalse(is_allowed_status_transition("Approved", current))

	def test_unchanged_status_is_always_allowed(self):
		for status in ("Pending", "Approved", "Rejected", "Expired", "Consumed"):
			with self.subTest(status=status):
				self.assertTrue(is_allowed_status_transition(status, status))

	def test_doctype_json_smoke(self):
		with open(os.path.join(_HERE, "external_action_approval.json")) as f:
			meta = json.load(f)
		self.assertEqual(meta["name"], "External Action Approval")
		self.assertEqual(meta["autoname"], "hash")
		self.assertEqual(meta["module"], "Huf")
