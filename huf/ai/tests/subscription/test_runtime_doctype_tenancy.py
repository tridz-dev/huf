# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for
`SubscriptionRuntime.check_tenancy()` in
`huf/huf/doctype/subscription_runtime/subscription_runtime.py`.

`check_tenancy()` (plus its private helpers `_get_allowed_users` /
`_get_allowed_roles` / `get_user_roles`) only touches `self.tenancy_policy`,
`self.owner_user`, `self.allowed_users_json`, `self.allowed_roles_json`, and
(for the `explicit_roles` branch) `frappe.get_roles()`. Rather than a plain
`types.SimpleNamespace` -- which would be missing those bound helper methods
-- `self` here is a real (but never-`__init__`-ed) `SubscriptionRuntime`
instance built via `object.__new__`, with only the fields `check_tenancy`
reads set directly. This exercises the real, unmodified implementation
(including its private helpers) without needing a live Frappe site/DB.

`frappe.get_roles` is monkeypatched for the `explicit_roles` branch since
that is the only external dependency `check_tenancy()` has.
"""

import unittest
from unittest import mock

import frappe

from huf.huf.doctype.subscription_runtime.subscription_runtime import SubscriptionRuntime


def _make_runtime(**overrides):
	defaults = dict(
		tenancy_policy="owner_only",
		owner_user=None,
		allowed_users_json=None,
		allowed_roles_json=None,
	)
	defaults.update(overrides)
	# Bypass Document.__init__ (needs a live Frappe site) but keep every real
	# bound method (check_tenancy, _get_allowed_users, _get_allowed_roles,
	# get_user_roles) intact, since check_tenancy calls them as self.<method>().
	runtime = object.__new__(SubscriptionRuntime)
	for key, value in defaults.items():
		setattr(runtime, key, value)
	return runtime


class TestCheckTenancy(unittest.TestCase):
	# --- owner_only ---

	def test_owner_only_allows_owner(self):
		runtime = _make_runtime(tenancy_policy="owner_only", owner_user="alice@example.com")
		self.assertTrue(runtime.check_tenancy("alice@example.com"))

	def test_owner_only_denies_non_owner(self):
		runtime = _make_runtime(tenancy_policy="owner_only", owner_user="alice@example.com")
		self.assertFalse(runtime.check_tenancy("bob@example.com"))

	def test_owner_only_denies_when_owner_unset(self):
		runtime = _make_runtime(tenancy_policy="owner_only", owner_user=None)
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	# --- explicit_users ---

	def test_explicit_users_allows_listed_user(self):
		runtime = _make_runtime(
			tenancy_policy="explicit_users",
			allowed_users_json='["alice@example.com", "bob@example.com"]',
		)
		self.assertTrue(runtime.check_tenancy("bob@example.com"))

	def test_explicit_users_denies_unlisted_user(self):
		runtime = _make_runtime(
			tenancy_policy="explicit_users",
			allowed_users_json='["alice@example.com"]',
		)
		self.assertFalse(runtime.check_tenancy("carol@example.com"))

	def test_explicit_users_denies_when_empty_list(self):
		runtime = _make_runtime(tenancy_policy="explicit_users", allowed_users_json="[]")
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_explicit_users_denies_when_none(self):
		runtime = _make_runtime(tenancy_policy="explicit_users", allowed_users_json=None)
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_explicit_users_denies_when_malformed_json(self):
		runtime = _make_runtime(tenancy_policy="explicit_users", allowed_users_json="not-json")
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_explicit_users_denies_when_json_not_a_list(self):
		runtime = _make_runtime(
			tenancy_policy="explicit_users",
			allowed_users_json='{"alice@example.com": true}',
		)
		self.assertFalse(runtime.check_tenancy("alice@example.com"))

	# --- explicit_roles ---

	def test_explicit_roles_allows_user_with_matching_role(self):
		runtime = _make_runtime(
			tenancy_policy="explicit_roles",
			allowed_roles_json='["Huf Manager", "Huf Admin"]',
		)
		with mock.patch.object(frappe, "get_roles", return_value=["Huf User", "Huf Manager"]):
			self.assertTrue(runtime.check_tenancy("alice@example.com"))

	def test_explicit_roles_denies_user_without_matching_role(self):
		runtime = _make_runtime(
			tenancy_policy="explicit_roles",
			allowed_roles_json='["Huf Admin"]',
		)
		with mock.patch.object(frappe, "get_roles", return_value=["Huf User"]):
			self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_explicit_roles_denies_when_empty_list(self):
		runtime = _make_runtime(tenancy_policy="explicit_roles", allowed_roles_json="[]")
		with mock.patch.object(frappe, "get_roles", return_value=["Huf Admin"]):
			self.assertFalse(runtime.check_tenancy("alice@example.com"))

	def test_explicit_roles_denies_when_none(self):
		runtime = _make_runtime(tenancy_policy="explicit_roles", allowed_roles_json=None)
		with mock.patch.object(frappe, "get_roles", return_value=["Huf Admin"]):
			self.assertFalse(runtime.check_tenancy("alice@example.com"))

	# --- system_managed_shared ---

	def test_system_managed_shared_always_allows(self):
		runtime = _make_runtime(tenancy_policy="system_managed_shared")
		self.assertTrue(runtime.check_tenancy("anyone@example.com"))

	# --- unknown policy ---

	def test_unknown_policy_fails_closed(self):
		runtime = _make_runtime(tenancy_policy="something_else")
		self.assertFalse(runtime.check_tenancy("alice@example.com"))


if __name__ == "__main__":
	unittest.main()
