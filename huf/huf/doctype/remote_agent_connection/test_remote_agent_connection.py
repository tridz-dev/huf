# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import json
import unittest
import frappe
from frappe.tests import IntegrationTestCase
from huf.huf.doctype.remote_agent_connection.remote_agent_connection import RemoteAgentConnection


class TestRemoteAgentConnection(IntegrationTestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_validations(self):
		# Base URL missing for HTTP
		doc = frappe.get_doc({
			"doctype": "Remote Agent Connection",
			"connection_name": "Test Connection Invalid URL",
			"protocol_type": "huf_native",
			"transport": "http",
			"auth_type": "none",
			"enabled": 1,
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

		# Invalid scheme
		doc.base_url = "ftp://invalid-url.com"
		self.assertRaises(frappe.ValidationError, doc.insert)

		# Invalid Auth secret missing
		doc.base_url = "https://valid-url.com"
		doc.auth_type = "bearer_token"
		self.assertRaises(frappe.ValidationError, doc.insert)

		# Invalid manifest JSON
		doc.auth_type = "none"
		doc.manifest_json = "{ invalid json }"
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_auth_secret_security(self):
		conn_name = "Test Secret Connection"
		if frappe.db.exists("Remote Agent Connection", conn_name):
			frappe.delete_doc("Remote Agent Connection", conn_name)

		doc = frappe.get_doc({
			"doctype": "Remote Agent Connection",
			"connection_name": conn_name,
			"protocol_type": "huf_native",
			"transport": "http",
			"base_url": "https://secure-agent.example.com",
			"auth_type": "bearer_token",
			"auth_secret": "super_secret_token_123",
			"enabled": 1,
		})
		doc.insert()

		# Verify auth_secret is not returned in as_dict()
		doc_dict = doc.as_dict()
		self.assertNotIn("auth_secret", doc_dict)

		# Verify secret can be safely fetched internally via get_auth_secret()
		retrieved_secret = doc.get_auth_secret()
		self.assertEqual(retrieved_secret, "super_secret_token_123")

		frappe.delete_doc("Remote Agent Connection", conn_name)
