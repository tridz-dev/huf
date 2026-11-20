"""Pure-logic tests for rows.py with frappe stubbed (no bench needed)."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

ROWS = Path(__file__).with_name("rows.py")


class _Err(Exception):
	pass


def _load():
	frappe = types.ModuleType("frappe")
	frappe.whitelist = lambda **kw: (lambda fn: fn)
	frappe.ValidationError = _Err
	frappe.PermissionError = _Err
	frappe.DoesNotExistError = _Err
	frappe.DataError = _Err

	def throw(msg, exc=_Err):
		raise exc(msg)

	frappe.throw = throw
	frappe._ = lambda s: s
	frappe.db = mock.MagicMock()
	frappe.get_meta = mock.MagicMock()
	frappe.get_list = mock.MagicMock()
	frappe.get_all = mock.MagicMock(return_value=[])
	sys.modules["frappe"] = frappe

	pkg = types.ModuleType("hdt_pkg")
	pkg.__path__ = []
	api = types.ModuleType("hdt_pkg.api")
	api._TYPES_TO_ACTION = {"Get List": "view"}
	api._PARAM_TOOL_TYPES = {"Get List"}
	api.TABLE_ACTION_MAP = {"view": (("Get List", "read"),)}
	for name in ("_require_read", "_resolve_table_registry", "_sync_tool_params", "_table_field_params", "_compute_access"):
		setattr(api, name, mock.MagicMock())
	sys.modules["hdt_pkg"] = pkg
	sys.modules["hdt_pkg.api"] = api
	spec = importlib.util.spec_from_file_location("hdt_pkg.rows", ROWS)
	mod = importlib.util.module_from_spec(spec)
	sys.modules["hdt_pkg.rows"] = mod
	spec.loader.exec_module(mod)
	return mod, frappe, api


rows, fr, api = _load()


def test_operator_allow_list_accepts_valid():
	rows.validate_filters([["qty", ">=", 3], ["name", "like", "%a%"], ["x", "not in", [1]]])
	rows.validate_filters([["HF T", "qty", "between", [1, 2]]])


@pytest.mark.parametrize("op", ["; drop", "regexp", "sleep(1)"])
def test_operator_allow_list_rejects(op):
	with pytest.raises(_Err):
		rows.validate_filters([["qty", op, 1]])


def test_dict_filter_operator_checked():
	rows.validate_filters({"qty": [">", 1]})
	with pytest.raises(_Err):
		rows.validate_filters({"qty": ["regexp", 1]})


def test_build_query_search_uses_search_fields_and_title():
	fr.get_meta.return_value = mock.Mock(search_fields="a, b", title_field="t")
	q = rows.build_record_query("HF T", "*", "[]", " hi ")
	assert q["or_filters"] == [["a", "like", "%hi%"], ["b", "like", "%hi%"], ["t", "like", "%hi%"]]


def test_count_without_search_uses_db_count():
	fr.db.count.return_value = 7
	assert rows.count_records("HF T", {"filters": [["a", "=", 1]], "or_filters": []}) == 7


def test_count_with_search_uses_aggregate():
	fr.get_list.return_value = [{"total": 3}]
	assert rows.count_records("HF T", {"filters": None, "or_filters": [["a", "like", "%x%"]]}) == 3


def test_bulk_limit_enforced():
	with pytest.raises(_Err):
		rows._check_bulk(list(range(rows.MAX_BULK_ROWS + 1)))


# ---- Track-Item: SEC-4 / SEC-5

def test_strip_reserved_keys():
	d = {k: "x" for k in rows.RESERVED_KEYS}
	d["title"] = "keep"
	assert rows.strip_reserved(d) == {"title": "keep"}
	assert rows.strip_reserved("nope") == {}


def test_bulk_insert_strips_reserved_keys():
	fr.get_doc = mock.Mock(return_value=mock.Mock(name="doc"))
	rows.bulk_insert_rows("HF T", [{"title": "a", "owner": "evil", "docstatus": 1, "doctype": "User"}])
	arg = fr.get_doc.call_args.args[0]
	assert arg == {"title": "a", "doctype": "HF T"}


def test_bulk_update_strips_reserved_keys():
	doc = mock.Mock()
	fr.get_doc = mock.Mock(return_value=doc)
	rows.bulk_update_rows("HF T", ["r1"], {"title": "b", "owner": "evil", "name": "x"})
	doc.update.assert_called_once_with({"title": "b"})


def _restore_setup(deleter, *, caller="me@x.com", admin=False, perms=("create", "read")):
	fr.session = types.SimpleNamespace(user=caller)
	fr.has_permission = lambda dt, ptype=None, *a, **k: (
		admin if dt == "Deleted Document" else ptype in perms
	)
	fr.db.get_value.return_value = mock.Mock(name="n", owner=deleter) if deleter else None
	if deleter:
		fr.db.get_value.return_value.name = "DD-1"
	deleted = mock.Mock(data='{"doctype": "HF T"}', deleted_name="r1")
	fr.get_doc = mock.Mock(return_value=deleted)
	fr.db.set_value = mock.Mock()
	return deleted


def test_restore_skips_rows_deleted_by_someone_else():
	_restore_setup("other@x.com")
	assert rows.restore_rows("HF T", ["r1"]) == {"restored": 0}


def test_restore_allows_own_deletion():
	_restore_setup("me@x.com")
	assert rows.restore_rows("HF T", ["r1"]) == {"restored": 1}


def test_restore_allows_deleted_document_admin():
	_restore_setup("other@x.com", admin=True)
	assert rows.restore_rows("HF T", ["r1"]) == {"restored": 1}


def test_restore_unknown_row_is_silent_not_found():
	_restore_setup(None)
	assert rows.restore_rows("HF T", ["ghost"]) == {"restored": 0}


def test_restore_requires_create_and_read():
	_restore_setup("me@x.com", perms=("create",))
	with pytest.raises(_Err):
		rows.restore_rows("HF T", ["r1"])
