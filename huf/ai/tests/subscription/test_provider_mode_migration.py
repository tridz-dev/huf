# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Unit tests for AI Provider provider_mode and billing_mode migration.

Tests that the migrate_ai_provider_mode_fields patch correctly:
1. Migrates is_local_llm=0/unset → provider_mode="API"
2. Migrates is_local_llm=1 → provider_mode="Local Endpoint"
3. NEVER sets provider_mode="Subscription CLI" for existing rows
4. Sets billing_mode="API" as default for all rows
5. Migration patch has no provider brand-based branching logic

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.subscription.test_provider_mode_migration
"""

import frappe
from frappe.tests import IntegrationTestCase


class TestProviderModeMigration(IntegrationTestCase):
	"""Integration tests for AI Provider provider_mode and billing_mode migration."""

	def setUp(self):
		self._providers = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._providers:
			try:
				frappe.delete_doc("AI Provider", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	def _create_provider(self, provider_brand="openai", is_local_llm=0, **kwargs):
		"""Helper to create an AI Provider with the given options."""
		frappe.set_user("Administrator")
		defaults = {
			"provider_name": f"test-provider-{frappe.generate_hash(length=8)}",
			"provider_brand": provider_brand,
			"is_local_llm": is_local_llm,
			"api_key": "test-key-12345",
		}
		defaults.update(kwargs)

		provider = frappe.get_doc({"doctype": "AI Provider", **defaults})
		self._providers.append(provider.name)
		return provider

	def test_migration_is_local_llm_0_to_api_mode(self):
		"""Test that is_local_llm=0 migrates to provider_mode='API'."""
		provider = self._create_provider(is_local_llm=0)
		provider.insert()

		# Verify initial state
		self.assertEqual(provider.is_local_llm, 0)

		# Simulate patch execution by manually running the migration logic
		from huf.patches.v1.migrate_ai_provider_mode_fields import _build_updates

		doc = frappe.get_doc("AI Provider", provider.name)
		row_data = {
			"name": doc.name,
			"is_local_llm": doc.is_local_llm,
			"provider_mode": doc.get("provider_mode", "API"),
			"billing_mode": doc.get("billing_mode", ""),
		}
		updates = _build_updates(row_data)
		self.assertIsNotNone(updates)
		self.assertEqual(updates.get("provider_mode"), "API")
		self.assertEqual(updates.get("billing_mode"), "API")

	def test_migration_is_local_llm_1_to_local_endpoint_mode(self):
		"""Test that is_local_llm=1 migrates to provider_mode='Local Endpoint'."""
		provider = self._create_provider(is_local_llm=1)
		provider.insert()

		# Verify initial state
		self.assertEqual(provider.is_local_llm, 1)

		# Simulate patch execution
		from huf.patches.v1.migrate_ai_provider_mode_fields import _build_updates

		doc = frappe.get_doc("AI Provider", provider.name)
		row_data = {
			"name": doc.name,
			"is_local_llm": doc.is_local_llm,
			"provider_mode": doc.get("provider_mode", "API"),
			"billing_mode": doc.get("billing_mode", ""),
		}
		updates = _build_updates(row_data)
		self.assertIsNotNone(updates)
		self.assertEqual(updates.get("provider_mode"), "Local Endpoint")
		self.assertEqual(updates.get("billing_mode"), "API")

	def test_migration_never_sets_subscription_cli_mode(self):
		"""Test that migration NEVER sets provider_mode='Subscription CLI' for existing rows.

		This is critical per plan §10.3: provider_mode='Subscription CLI' must only
		ever be set explicitly by an admin choosing it in the UI, never by the migration.
		"""
		from huf.patches.v1.migrate_ai_provider_mode_fields import _build_updates

		# Test with is_local_llm=0
		row_data = {
			"name": "test1",
			"is_local_llm": 0,
			"provider_mode": "API",
			"billing_mode": "",
		}
		updates = _build_updates(row_data)
		if updates and "provider_mode" in updates:
			self.assertNotEqual(updates["provider_mode"], "Subscription CLI")

		# Test with is_local_llm=1
		row_data = {
			"name": "test2",
			"is_local_llm": 1,
			"provider_mode": "API",
			"billing_mode": "",
		}
		updates = _build_updates(row_data)
		if updates and "provider_mode" in updates:
			self.assertNotEqual(updates["provider_mode"], "Subscription CLI")

		# Test with various provider brands
		for brand in ["openai", "anthropic", "google"]:
			provider = self._create_provider(provider_brand=brand, is_local_llm=0)
			provider.insert()

			doc = frappe.get_doc("AI Provider", provider.name)
			row_data = {
				"name": doc.name,
				"is_local_llm": doc.is_local_llm,
				"provider_mode": doc.get("provider_mode", "API"),
				"billing_mode": doc.get("billing_mode", ""),
			}
			updates = _build_updates(row_data)
			if updates and "provider_mode" in updates:
				self.assertNotEqual(
					updates["provider_mode"],
					"Subscription CLI",
					f"Migration should never set provider_mode='Subscription CLI' for {brand}",
				)

	def test_migration_sets_billing_mode_default(self):
		"""Test that all rows get billing_mode='API' as default."""
		provider = self._create_provider(is_local_llm=0)
		provider.insert()

		from huf.patches.v1.migrate_ai_provider_mode_fields import _build_updates

		doc = frappe.get_doc("AI Provider", provider.name)
		row_data = {
			"name": doc.name,
			"is_local_llm": doc.is_local_llm,
			"provider_mode": doc.get("provider_mode", "API"),
			"billing_mode": doc.get("billing_mode", ""),
		}
		updates = _build_updates(row_data)
		self.assertIsNotNone(updates)
		self.assertEqual(updates.get("billing_mode"), "API")

	def test_migration_has_no_brand_based_branching(self):
		"""Test that migration code has no conditional on provider brand.

		This ensures provider_mode is derived only from is_local_llm,
		not from provider brand (plan §10.3).
		"""
		from huf.patches.v1 import migrate_ai_provider_mode_fields
		import inspect

		# Read the patch source code
		source = inspect.getsource(migrate_ai_provider_mode_fields._build_updates)

		# Check that the function does NOT reference provider_brand
		# or any brand/name that would indicate conditional logic based on provider brand
		forbidden_terms = [
			"provider_brand",
			"openai",
			"anthropic",
			"google",
			"stripe",
			"brand",
		]
		for term in forbidden_terms:
			self.assertNotIn(
				term.lower(),
				source.lower(),
				f"Migration function should not have logic based on '{term}'",
			)

	def test_migration_idempotent(self):
		"""Test that running the migration twice produces the same result."""
		provider = self._create_provider(is_local_llm=0)
		provider.insert()

		from huf.patches.v1.migrate_ai_provider_mode_fields import _build_updates

		doc = frappe.get_doc("AI Provider", provider.name)

		# First run
		row_data1 = {
			"name": doc.name,
			"is_local_llm": doc.is_local_llm,
			"provider_mode": doc.get("provider_mode", "API"),
			"billing_mode": doc.get("billing_mode", ""),
		}
		updates1 = _build_updates(row_data1)

		# Simulate applying the updates
		if updates1:
			for key, value in updates1.items():
				row_data1[key] = value

		# Second run (with updated values)
		updates2 = _build_updates(row_data1)

		# Should be idempotent: second run should not produce further updates
		# (or updates should be the same as the first)
		if updates2:
			self.assertEqual(
				updates2.get("provider_mode"),
				updates1.get("provider_mode") if updates1 else row_data1.get("provider_mode"),
				"Migration should be idempotent",
			)


if __name__ == "__main__":
	import unittest

	unittest.main()
