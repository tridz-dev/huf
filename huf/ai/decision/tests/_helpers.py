"""Shared test helpers for huf.ai.decision.tests."""

from __future__ import annotations

import frappe


def make_user_unthrottled(*args, **kwargs):
	"""``make_user`` with ``User.before_insert``'s ``throttle_user_creation`` bypassed.

	The decision test package creates a handful of throwaway Users per test class
	(capability tiers, one-off users for permission/role-mismatch cases); running the
	whole package back to back trips the default 60-Users-per-60s site limit
	(``frappe.core.doctype.user.user.throttle_user_creation``) well before any of that
	is actually abusive. ``frappe.flags.in_import`` is the one condition that function
	already checks to skip itself (bulk-import tooling hits the same limit legitimately),
	so tests borrow that flag rather than mutating site config.
	"""
	previous = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		from huf.ai.tests.factories import make_user as make_user_impl
		return make_user_impl(*args, **kwargs)
	finally:
		frappe.flags.in_import = previous
