# Copyright (c) 2026, Huf and contributors
# See license.txt

import json
import os
import unittest

from huf.huf.doctype.external_action_approval.external_action_approval import ExternalActionApproval

_HERE = os.path.dirname(os.path.abspath(__file__))


class TestExternalActionApproval(unittest.TestCase):
	def test_controller_module_imports(self):
		self.assertIsNotNone(ExternalActionApproval)

	def test_doctype_json_smoke(self):
		with open(os.path.join(_HERE, "external_action_approval.json")) as f:
			meta = json.load(f)
		self.assertEqual(meta["name"], "External Action Approval")
		self.assertEqual(meta["autoname"], "hash")
		self.assertEqual(meta["module"], "Huf")
