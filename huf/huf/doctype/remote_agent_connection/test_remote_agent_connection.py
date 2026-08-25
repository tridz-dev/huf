# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import os

import frappe
from frappe.tests import IntegrationTestCase


class TestRemoteAgentConnection(IntegrationTestCase):
	def test_acp_connection_requires_registry_entry(self):
		doc = frappe.new_doc("Remote Agent Connection")
		doc.connection_name = "test-acp-no-registry"
		doc.protocol_type = "acp_stdio"
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_acp_connection_rejects_disabled_registry(self):
		registry = self._ensure_test_registry(enabled=0)
		doc = frappe.new_doc("Remote Agent Connection")
		doc.connection_name = "test-acp-disabled-registry"
		doc.protocol_type = "acp_stdio"
		doc.acp_registry_entry = registry.name
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_acp_connection_requires_auth_when_registry_requires_it(self):
		registry = self._ensure_test_registry(enabled=1, auth_required=1, auth_env_key="HUF_ACP_TARGET_TOKEN")
		doc = frappe.new_doc("Remote Agent Connection")
		doc.connection_name = "test-acp-no-auth"
		doc.protocol_type = "acp_stdio"
		doc.acp_registry_entry = registry.name
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def _ensure_test_registry(self, enabled=1, auth_required=0, auth_env_key=None):
		name = f"_test_registry_{enabled}_{auth_required}"
		if frappe.db.exists("ACP Command Registry", name):
			return frappe.get_doc("ACP Command Registry", name)
		doc = frappe.new_doc("ACP Command Registry")
		doc.registry_name = name
		doc.binary_path = "/usr/bin/true"
		doc.argv_shape = '["acp"]'
		doc.working_directory = os.path.dirname(__file__)
		doc.enabled = enabled
		doc.auth_required = auth_required
		doc.auth_env_key = auth_env_key
		doc.insert()
		return doc
