# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""``_is_api_key_caller`` must not raise "object is not bound" outside an HTTP request.

An approved agent tool (``tool_confirmation.run_approved``) starts a broadcast from an RQ job, where
``frappe.request`` is unbound; the typed-count check calls ``_is_api_key_caller`` there.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import frappe

from huf.ai.whatsapp.broadcast import api as mgmt


@unittest.skipIf(isinstance(frappe, MagicMock), "needs real frappe.local")
class TestApiKeyCallerWithoutRequest(unittest.TestCase):
	def test_no_http_request_is_not_api_key_caller(self):
		missing = object()
		saved = getattr(frappe.local, "request", missing)
		frappe.local.request = None  # unbound / absent request, as in an RQ job
		try:
			self.assertFalse(mgmt._is_api_key_caller())
		finally:
			if saved is missing:
				try:
					del frappe.local.request
				except AttributeError:
					pass
			else:
				frappe.local.request = saved
