"""Test list-scoping for Huf API Key via permission_query_conditions.

Tests that Huf API Key list is scoped to the owner, preventing users
from enumerating API keys created by other users.
"""

import frappe
import pytest
from huf.huf.doctype.huf_api_key.huf_api_key import get_api_key_permission_conditions


class TestApiKeyListScope:
	"""Test permission_query_conditions for Huf API Key."""

	def test_system_manager_gets_no_filter(self):
		"""System Manager should see no filter (returns None)."""
		frappe.set_user("Administrator")
		result = get_api_key_permission_conditions("Administrator")
		assert result is None

	def test_huf_user_gets_where_clause(self):
		"""Regular Huf User should get a WHERE clause filtering by owner."""
		result = get_api_key_permission_conditions("alice@example.com")
		assert result is not None
		assert "Huf API Key" in result
		assert "owner" in result
		assert "alice@example.com" in result or "alice@example.com" in result

	def test_huf_user_list_sees_only_own_api_keys(self):
		"""Huf User listing API keys should only see those they own."""
		# Setup: Create API keys for two users
		alice_key = frappe.new_doc("Huf API Key")
		alice_key.key_id = "huf_sk_test_alice"
		alice_key.label = "Alice's Key"
		alice_key.hashed_secret = "dummy_hash_alice"
		alice_key.scopes = '["agents:read"]'
		alice_key.owner = "alice@example.com"
		alice_key.insert()

		bob_key = frappe.new_doc("Huf API Key")
		bob_key.key_id = "huf_sk_test_bob"
		bob_key.label = "Bob's Key"
		bob_key.hashed_secret = "dummy_hash_bob"
		bob_key.scopes = '["agents:read"]'
		bob_key.owner = "bob@example.com"
		bob_key.insert()

		try:
			# Alice lists API keys as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Huf API Key",
				filters=[],
				pluck="name",
			)

			# Alice should only see her own key
			assert alice_key.name in alice_list
			assert bob_key.name not in alice_list
		finally:
			alice_key.delete()
			bob_key.delete()

	def test_huf_user_list_excludes_foreign_api_keys(self):
		"""Huf User should not see API keys owned by others."""
		# Setup: Create a key owned by bob
		bob_key = frappe.new_doc("Huf API Key")
		bob_key.key_id = "huf_sk_test_bob"
		bob_key.label = "Bob's Key"
		bob_key.hashed_secret = "dummy_hash_bob"
		bob_key.scopes = '["agents:read"]'
		bob_key.owner = "bob@example.com"
		bob_key.insert()

		try:
			# Alice lists API keys as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Huf API Key",
				filters=[],
				pluck="name",
			)

			# Alice should NOT see bob's key
			assert bob_key.name not in alice_list
		finally:
			bob_key.delete()

	def test_system_manager_list_sees_all_api_keys(self):
		"""System Manager should see all API keys from all users."""
		# Setup: Create keys for two users
		alice_key = frappe.new_doc("Huf API Key")
		alice_key.key_id = "huf_sk_test_alice"
		alice_key.label = "Alice's Key"
		alice_key.hashed_secret = "dummy_hash_alice"
		alice_key.scopes = '["agents:read"]'
		alice_key.owner = "alice@example.com"
		alice_key.insert()

		bob_key = frappe.new_doc("Huf API Key")
		bob_key.key_id = "huf_sk_test_bob"
		bob_key.label = "Bob's Key"
		bob_key.hashed_secret = "dummy_hash_bob"
		bob_key.scopes = '["agents:read"]'
		bob_key.owner = "bob@example.com"
		bob_key.insert()

		try:
			# System Manager lists API keys
			frappe.set_user("Administrator")
			admin_list = frappe.get_list(
				"Huf API Key",
				filters=[],
				pluck="name",
			)

			# Admin should see both keys
			assert alice_key.name in admin_list
			assert bob_key.name in admin_list
		finally:
			alice_key.delete()
			bob_key.delete()
