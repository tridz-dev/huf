# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""get_me reports the DocType rights the screens gate their buttons on."""

import unittest
from unittest import mock

from huf import permissions


class TestDocPermissionsReport(unittest.TestCase):
	def test_write_is_reported_separately_from_create_and_delete(self):
		with mock.patch.object(permissions, "frappe") as fake:
			fake.has_permission.side_effect = lambda doctype, ptype, user=None: ptype != "write"
			report = permissions._doc_permissions("user@example.com")

		self.assertEqual(report["Knowledge Source"], {"create": True, "write": False, "delete": True})


if __name__ == "__main__":
	unittest.main()
