# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.system_records -- the shared system-record locking
helper (permission query conditions, flag-tamper guard, field immutability,
delete guard, rename guard).

All five layers are pure functions over a fake Document-like object and a
mocked ``frappe`` module, so these tests are frappe-free and do not require
a live bench. They cover only the helper's own logic, not Frappe's actual
permission-query-conditions wiring or ORM behaviour -- verifying that
non-System-Managers genuinely cannot see/edit/rename/delete a system record
through the real API (e.g. Flow Definition end-to-end) needs a bench and is
out of scope here; see PLAN.md T-15's "Done when" for that acceptance bar.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_system_records
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import system_records


def _field(fieldname, fieldtype="Data"):
	return SimpleNamespace(fieldname=fieldname, fieldtype=fieldtype)


class _FakeDoc:
	"""Minimal stand-in for a frappe Document, covering only what
	system_records touches: is_new/get/has_value_changed/get_doc_before_save
	plus a .meta.fields list."""

	def __init__(self, values, meta_fields, before=None, new=False):
		self._values = dict(values)
		self.meta = SimpleNamespace(fields=meta_fields)
		self._before = before
		self._new = new

	def is_new(self):
		return self._new

	def get(self, fieldname, default=None):
		return self._values.get(fieldname, default)

	def has_value_changed(self, fieldname):
		if self._before is None:
			return False
		return self._values.get(fieldname) != self._before.get(fieldname)

	def get_doc_before_save(self):
		return self._before


META_FIELDS = [
	_field("is_system", "Check"),
	_field("title"),
	_field("locked_field"),
	_field("child_rows", "Table"),
	_field("layout_only", "Section Break"),
]


class TestPermissionQueryConditions(unittest.TestCase):
	@patch("huf.ai.system_records.frappe")
	def test_system_manager_sees_everything(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["System Manager"]
		fn = system_records.make_permission_query_conditions("Flow Definition")
		self.assertIsNone(fn(user="admin@example.com"))

	@patch("huf.ai.system_records.frappe")
	def test_non_system_manager_is_scoped_to_non_system_rows(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["Huf User"]
		fn = system_records.make_permission_query_conditions("Flow Definition")
		condition = fn(user="user@example.com")
		self.assertEqual(condition, "`tabFlow Definition`.`is_system` = 0")

	@patch("huf.ai.system_records.frappe")
	def test_defaults_to_session_user_when_none_given(self, mock_frappe):
		mock_frappe.session.user = "user@example.com"
		mock_frappe.get_roles.return_value = []
		fn = system_records.make_permission_query_conditions("Agent")
		fn(user=None)
		mock_frappe.get_roles.assert_called_once_with("user@example.com")


class TestGuardFlagTamper(unittest.TestCase):
	@patch("huf.ai.system_records.frappe")
	def test_new_doc_is_never_blocked(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		doc = _FakeDoc({"is_system": 1}, META_FIELDS, before=None, new=True)
		system_records.guard_flag_tamper(doc)  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_unchanged_flag_is_never_blocked(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		before = {"is_system": 1}
		doc = _FakeDoc({"is_system": 1}, META_FIELDS, before=before)
		system_records.guard_flag_tamper(doc)  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_non_admin_cannot_flip_flag(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["Huf User"]
		mock_frappe.flags = SimpleNamespace()
		mock_frappe.throw.side_effect = ValueError("blocked")
		before = {"is_system": 0}
		doc = _FakeDoc({"is_system": 1}, META_FIELDS, before=before)
		with self.assertRaises(ValueError):
			system_records.guard_flag_tamper(doc)

	@patch("huf.ai.system_records.frappe")
	def test_system_manager_can_flip_flag(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["System Manager"]
		before = {"is_system": 0}
		doc = _FakeDoc({"is_system": 1}, META_FIELDS, before=before)
		system_records.guard_flag_tamper(doc)  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_seeding_flag_bypasses_the_guard(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		mock_frappe.flags = SimpleNamespace(in_seeding=True, in_install=False, in_migrate=False)
		before = {"is_system": 0}
		doc = _FakeDoc({"is_system": 1}, META_FIELDS, before=before)
		system_records.guard_flag_tamper(doc)  # must not raise


class TestGuardFieldImmutability(unittest.TestCase):
	@patch("huf.ai.system_records.frappe")
	def test_non_system_record_is_never_locked(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		before = {"is_system": 0, "title": "old"}
		doc = _FakeDoc({"is_system": 0, "title": "new"}, META_FIELDS, before=before)
		system_records.guard_field_immutability(doc)  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_unlisted_field_is_locked_by_default(self, mock_frappe):
		"""GAP 1 hardening: a field with no explicit allow-list entry is
		locked, not silently editable."""
		mock_frappe.get_roles.return_value = ["Huf User"]
		mock_frappe.flags = SimpleNamespace()
		mock_frappe.throw.side_effect = ValueError("blocked")
		mock_frappe.as_json.side_effect = lambda v: str(v)
		before = {"is_system": 1, "title": "old", "locked_field": "old"}
		doc = _FakeDoc({"is_system": 1, "title": "old", "locked_field": "new"}, META_FIELDS, before=before)
		with self.assertRaises(ValueError):
			system_records.guard_field_immutability(doc, unlocked_fields=("title",))

	@patch("huf.ai.system_records.frappe")
	def test_allow_listed_field_stays_editable(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["Huf User"]
		mock_frappe.throw.side_effect = ValueError("blocked")
		mock_frappe.as_json.side_effect = lambda v: str(v)
		before = {"is_system": 1, "title": "old", "locked_field": "same"}
		doc = _FakeDoc({"is_system": 1, "title": "new", "locked_field": "same"}, META_FIELDS, before=before)
		system_records.guard_field_immutability(doc, unlocked_fields=("title",))  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_child_table_change_is_locked_by_default(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["Huf User"]
		mock_frappe.flags = SimpleNamespace()
		mock_frappe.throw.side_effect = ValueError("blocked")
		mock_frappe.as_json.side_effect = lambda v: str(v)

		row_old = SimpleNamespace(as_dict=lambda: {"value": "old"})
		row_new = SimpleNamespace(as_dict=lambda: {"value": "new"})
		before = SimpleNamespace(get=lambda f, d=None: [row_old] if f == "child_rows" else d)
		doc = _FakeDoc(
			{"is_system": 1, "title": "old", "locked_field": "old", "child_rows": [row_new]},
			META_FIELDS,
			before=before,
		)
		# has_value_changed is only used for scalar fields in _FakeDoc; child
		# tables are compared via .get() directly, so patch it accordingly.
		doc.has_value_changed = lambda f: False
		with self.assertRaises(ValueError):
			system_records.guard_field_immutability(doc, unlocked_fields=("title",))

	@patch("huf.ai.system_records.frappe")
	def test_privileged_user_bypasses_the_guard(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["System Manager"]
		before = {"is_system": 1, "title": "old", "locked_field": "old"}
		doc = _FakeDoc({"is_system": 1, "title": "old", "locked_field": "new"}, META_FIELDS, before=before)
		system_records.guard_field_immutability(doc, unlocked_fields=("title",))  # must not raise


class TestGuardDelete(unittest.TestCase):
	@patch("huf.ai.system_records.frappe")
	def test_non_system_record_can_be_deleted(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		doc = _FakeDoc({"is_system": 0}, META_FIELDS)
		system_records.guard_delete(doc)  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_system_record_cannot_be_deleted_by_non_admin(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["Huf User"]
		mock_frappe.flags = SimpleNamespace()
		mock_frappe.throw.side_effect = ValueError("blocked")
		doc = _FakeDoc({"is_system": 1}, META_FIELDS)
		with self.assertRaises(ValueError):
			system_records.guard_delete(doc)

	@patch("huf.ai.system_records.frappe")
	def test_uninstall_flag_bypasses_the_guard(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		mock_frappe.flags = SimpleNamespace(in_install=False, in_migrate=False, in_uninstall=True)
		doc = _FakeDoc({"is_system": 1}, META_FIELDS)
		system_records.guard_delete(doc)  # must not raise


class TestGuardRename(unittest.TestCase):
	@patch("huf.ai.system_records.frappe")
	def test_non_system_record_can_be_renamed(self, mock_frappe):
		mock_frappe.get_roles.return_value = []
		doc = _FakeDoc({"is_system": 0}, META_FIELDS)
		system_records.guard_rename(doc, "old-name", "new-name")  # must not raise

	@patch("huf.ai.system_records.frappe")
	def test_system_record_cannot_be_renamed_by_non_admin(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["Huf User"]
		mock_frappe.flags = SimpleNamespace()
		mock_frappe.throw.side_effect = ValueError("blocked")
		doc = _FakeDoc({"is_system": 1}, META_FIELDS)
		with self.assertRaises(ValueError):
			system_records.guard_rename(doc, "old-name", "new-name")

	@patch("huf.ai.system_records.frappe")
	def test_system_manager_can_rename(self, mock_frappe):
		mock_frappe.get_roles.return_value = ["System Manager"]
		doc = _FakeDoc({"is_system": 1}, META_FIELDS)
		system_records.guard_rename(doc, "old-name", "new-name")  # must not raise


if __name__ == "__main__":
	unittest.main()
