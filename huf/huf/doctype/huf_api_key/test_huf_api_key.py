# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""
Tests for Huf API Key generation, hashing, and verification.

Run with: bench --site <site> run-tests --app huf --module huf.huf.doctype.huf_api_key.test_huf_api_key

NOTE: these tests require a live bench (frappe.init'd site + DB) to run;
they could not be executed in this environment. See the implementation
report for what still needs live verification.
"""

import unittest

import frappe

from huf.install import create_huf_roles
from huf.huf.doctype.huf_api_key.huf_api_key import (
	create_api_key,
	revoke_api_key,
	list_api_keys,
	verify_key,
	generate_key,
	KEY_PREFIX,
)


class TestHufAPIKey(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		create_huf_roles()

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_generate_key_shape(self):
		key_id, raw_secret = generate_key()
		self.assertTrue(key_id.startswith(KEY_PREFIX))
		self.assertTrue(raw_secret.startswith(KEY_PREFIX))
		self.assertNotEqual(key_id, raw_secret)

	def test_create_and_verify_round_trip(self):
		result = create_api_key(label="Test Key", scopes=["agents:read"], agent_restriction_mode="all")
		raw_secret = result["raw_secret"]

		doc = verify_key(raw_secret)
		self.assertIsNotNone(doc)
		self.assertEqual(doc.key_id, result["key_id"])

		revoke_api_key(result["key_id"])
		self.assertIsNone(verify_key(raw_secret))

	def test_verify_key_rejects_garbage(self):
		self.assertIsNone(verify_key("not-a-real-key"))
		self.assertIsNone(verify_key(""))
		self.assertIsNone(verify_key(None))

	def test_list_api_keys_excludes_hashed_secret(self):
		create_api_key(label="Listed Key", scopes=[], agent_restriction_mode="all")
		rows = list_api_keys()
		for row in rows:
			self.assertNotIn("hashed_secret", row)
			self.assertNotIn("raw_secret", row)
