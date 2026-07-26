"""
Tests for SSH Connection controller validation and capability-gated mutation.

Run with: bench --site <site> run-tests --app huf --module huf.huf.doctype.ssh_connection.test_ssh_connection
"""
import unittest
from unittest.mock import patch

import frappe

from huf.install import create_huf_roles
from huf.huf.doctype.ssh_connection.ssh_connection import (
	enroll_host_key,
	rotate_ssh_secret,
	test_ssh_connection,
)


class TestSSHConnection(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		create_huf_roles()

	def setUp(self):
		self._users = []
		self._connections = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._connections:
			self._delete("SSH Connection", name)
		for name in self._users:
			self._delete("User", name)
		frappe.db.commit()

	def _delete(self, doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	def _make_user(self, roles=()):
		email = f"huf-ssh-test-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "SSHTest",
				"send_welcome_email": 0,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_connection(self, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "SSH Connection",
				"display_name": f"ssh-test-{frappe.generate_hash(length=8)}",
				"host": "example.com",
				"port": 22,
				"username": "ubuntu",
				"auth_method": "Password",
				"password": "secret-pass",
				**overrides,
			}
		)
		doc.insert(ignore_permissions=True)
		self._connections.append(doc.name)
		return doc

	def test_manage_capability_gates_mutation_but_not_read(self):
		doc = frappe.new_doc("SSH Connection")
		plain_user = self._make_user(roles=("Huf User",))
		manager_user = self._make_user(roles=("Huf Manager",))

		frappe.set_user(plain_user)
		self.assertFalse(doc.has_permission("create"))
		self.assertFalse(doc.has_permission("write"))
		self.assertFalse(doc.has_permission("delete"))
		self.assertTrue(doc.has_permission("read"))

		frappe.set_user(manager_user)
		self.assertTrue(doc.has_permission("create"))
		self.assertTrue(doc.has_permission("write"))
		self.assertTrue(doc.has_permission("delete"))

		frappe.set_user("Administrator")
		self.assertTrue(doc.has_permission("delete"))

	def test_password_auth_requires_password(self):
		doc = frappe.get_doc(
			{
				"doctype": "SSH Connection",
				"display_name": f"ssh-test-{frappe.generate_hash(length=8)}",
				"host": "example.com",
				"port": 22,
				"username": "ubuntu",
				"auth_method": "Password",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_private_key_auth_requires_key(self):
		doc = frappe.get_doc(
			{
				"doctype": "SSH Connection",
				"display_name": f"ssh-test-{frappe.generate_hash(length=8)}",
				"host": "example.com",
				"port": 22,
				"username": "ubuntu",
				"auth_method": "Private Key",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_blank_password_edit_keeps_existing_secret(self):
		doc = self._make_connection()
		self.assertEqual(doc.get_password("password"), "secret-pass")

		doc.password = ""
		doc.save(ignore_permissions=True)

		reloaded = frappe.get_doc("SSH Connection", doc.name)
		self.assertEqual(reloaded.get_password("password"), "secret-pass")

	@patch("huf.huf.doctype.ssh_connection.ssh_connection._open_transport")
	def test_test_connection_reports_success_and_fingerprint(self, mock_open_transport):
		doc = self._make_connection()
		transport = unittest.mock.Mock()
		mock_open_transport.return_value = (transport, "SHA256:testfingerprint", "ssh-ed25519")

		result = test_ssh_connection(doc.name)

		self.assertTrue(result["success"])
		self.assertEqual(result["fingerprint"], "SHA256:testfingerprint")
		self.assertEqual(result["host_key_type"], "ssh-ed25519")
		reloaded = frappe.get_doc("SSH Connection", doc.name)
		self.assertEqual(reloaded.last_test_status, "Success")

	@patch("huf.huf.doctype.ssh_connection.ssh_connection._open_transport")
	def test_enroll_host_key_persists_metadata(self, mock_open_transport):
		doc = self._make_connection()
		transport = unittest.mock.Mock()
		mock_open_transport.return_value = (transport, "SHA256:enrolled", "ssh-rsa")

		result = enroll_host_key(doc.name)

		self.assertTrue(result["success"])
		reloaded = frappe.get_doc("SSH Connection", doc.name)
		self.assertEqual(reloaded.host_key_fingerprint, "SHA256:enrolled")
		self.assertEqual(reloaded.host_key_type, "ssh-rsa")
		self.assertTrue(reloaded.host_key_enrolled_by)
		self.assertTrue(reloaded.host_key_enrolled_on)

	def test_rotate_secret_switches_auth_method_and_sets_timestamp(self):
		doc = self._make_connection()

		result = rotate_ssh_secret(
			doc.name,
			auth_method="Private Key",
			private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----",
			private_key_passphrase="passphrase",
		)

		self.assertTrue(result["success"])
		reloaded = frappe.get_doc("SSH Connection", doc.name)
		self.assertEqual(reloaded.auth_method, "Private Key")
		self.assertTrue(reloaded.key_rotated_on)


if __name__ == "__main__":
	unittest.main()
