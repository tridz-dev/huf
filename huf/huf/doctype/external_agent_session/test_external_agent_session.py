# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import json
import os
import unittest

from huf.huf.doctype.external_agent_session.external_agent_session import ExternalAgentSession

_HERE = os.path.dirname(os.path.abspath(__file__))


class TestExternalAgentSession(unittest.TestCase):
	def test_controller_class_available(self):
		self.assertTrue(callable(ExternalAgentSession))

	def test_doctype_json_smoke(self):
		with open(os.path.join(_HERE, "external_agent_session.json")) as f:
			meta = json.load(f)
		self.assertEqual(meta["name"], "External Agent Session")
		self.assertEqual(meta["autoname"], "hash")
		state = next(f for f in meta["fields"] if f["fieldname"] == "state")
		self.assertEqual(state["default"], "Active")
