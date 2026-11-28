"""W1: ``_require_app_view`` refuses exactly the callers ``guard_app_named`` already refused. Needs no site."""

import itertools
import unittest
from unittest import mock

import frappe

from huf.ai.flow.app_scope import api_guards, runs_api


def _refused(fn, app, privileged, app_only, grants):
	with (
		mock.patch.object(api_guards, "is_privileged", return_value=privileged),
		mock.patch.object(runs_api, "is_privileged", return_value=privileged),
		mock.patch.object(api_guards, "is_app_only", return_value=app_only),
		mock.patch.object(api_guards, "apps_for", return_value=grants),
		mock.patch.object(runs_api, "apps_for", return_value=grants),
		mock.patch.object(api_guards, "_deny", side_effect=frappe.PermissionError),
	):
		try:
			fn(app)
		except frappe.PermissionError:
			return True
	return False


class TestRunsApiGuard(unittest.TestCase):
	def test_same_callers_are_refused_as_before(self):
		for app, privileged, app_only, grants in itertools.product(
			(None, "", "crm", "other"), (True, False), (True, False), (set(), {"crm"})
		):
			with self.subTest(app=app, privileged=privileged, app_only=app_only, grants=grants):
				self.assertEqual(
					_refused(runs_api._require_app_view, app, privileged, app_only, grants),
					_refused(api_guards.guard_app_named, app, privileged, app_only, grants),
				)
