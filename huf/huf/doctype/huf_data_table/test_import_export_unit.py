"""Pure-logic tests; run with frappe stubbed (no bench):
python -m pytest huf/huf/doctype/huf_data_table/test_import_export_unit.py
"""
import importlib.util
import io
import os
import sys
import types
from pathlib import Path

import pytest

if getattr(sys.modules.get("frappe"), "__file__", None) is None:
	stub = types.ModuleType("frappe")
	stub._ = lambda s, *a: s
	stub.whitelist = lambda *a, **k: (lambda f: f)
	stub.__file__ = None
	stub.scrub = lambda s: s.strip().lower().replace(" ", "_").replace("-", "_")
	stub.throw = lambda msg, *a, **k: (_ for _ in ()).throw(Exception(msg))
	sys.modules["frappe"] = stub

_pkg = types.ModuleType("ie_pkg")
_pkg.__path__ = [str(Path(__file__).parent)]
sys.modules["ie_pkg"] = _pkg


def _load_mod(name):
	spec = importlib.util.spec_from_file_location(f"ie_pkg.{name}", Path(__file__).with_name(f"{name}.py"))
	mod = importlib.util.module_from_spec(spec)
	sys.modules[f"ie_pkg.{name}"] = mod
	spec.loader.exec_module(mod)
	return mod


_load_mod("csv_out")
sec = _load_mod("import_security")
ie = _load_mod("import_export")
_load_mod("import_replace")

FIELDS = [
	{"fieldname": "title", "label": "Title", "fieldtype": "Data", "reqd": 1, "options": None},
	{"fieldname": "qty", "label": "Quantity", "fieldtype": "Int", "reqd": 0, "options": None},
	{"fieldname": "price", "label": "Unit Price", "fieldtype": "Currency", "reqd": 0, "options": None},
	{"fieldname": "due", "label": "Due Date", "fieldtype": "Date", "reqd": 0, "options": None},
	{"fieldname": "done", "label": "Done", "fieldtype": "Check", "reqd": 0, "options": None},
	{"fieldname": "status", "label": "Status", "fieldtype": "Select", "reqd": 0, "options": "Open\nClosed"},
]
BY = {f["fieldname"]: f for f in FIELDS}


def test_parse_csv_bom_and_semicolon():
	h, r = ie.parse_csv("﻿a;b\n1;2\n\n3;4\n".encode("utf-8"))
	assert h == ["a", "b"] and r == [["1", "2"], ["3", "4"]]


def test_parse_csv_short_rows_padded():
	h, r = ie.parse_csv("a,b,c\n1,2\n")
	assert r == [["1", "2", ""]]


def test_detect_types():
	assert ie.detect_type(["1", "2.5", "1,000"]) == "number"
	assert ie.detect_type(["2024-01-31", "31/01/2024"]) == "date"
	assert ie.detect_type(["yes", "no", ""]) == "checkbox"
	assert ie.detect_type(["a", "1"]) == "text"
	assert ie.detect_type(["", ""]) == "text"


def test_auto_map_label_fieldname_case_insensitive():
	m = ie.auto_map(["TITLE", "quantity", "Unit Price", "unknown", "Name"], FIELDS)
	assert m == {"TITLE": "title", "quantity": "qty", "Unit Price": "price", "unknown": None, "Name": "name"}


def test_auto_map_no_duplicate_targets():
	m = ie.auto_map(["title", "Title"], FIELDS)
	assert m["title"] == "title" and m["Title"] is None


def test_coerce_ok():
	assert ie.coerce_value(BY["qty"], "5") == (5, None)
	assert ie.coerce_value(BY["due"], "31/01/2024") == ("2024-01-31", None)
	assert ie.coerce_value(BY["done"], "Yes") == (1, None)
	assert ie.coerce_value(BY["status"], "closed") == ("Closed", None)


@pytest.mark.parametrize("name,val", [("qty", "x"), ("qty", "1.5"), ("due", "nope"), ("done", "maybe"), ("status", "Other"), ("title", "")])
def test_coerce_errors(name, val):
	assert ie.coerce_value(BY[name], val)[1]


def test_build_record_collects_errors_and_required():
	headers = ["Title", "Quantity"]
	mapping = ie.auto_map(headers, FIELDS)
	rec, errs = ie.build_record(headers, ["Hi", "3"], mapping, BY)
	assert rec == {"title": "Hi", "qty": 3} and not errs
	_, errs = ie.build_record(headers, ["", "z"], mapping, BY)
	assert len(errs) == 2


def test_build_record_missing_required_column():
	_, errs = ie.build_record(["Quantity"], ["1"], {"Quantity": "qty"}, BY)
	assert any("required" in e for e in errs), errs


def test_csv_escaping_and_formula_injection():
	out = ie.to_csv_text(["a", "b"], [['he said "hi", ok', "=SUM(A1)"], ["-5", "line\nbreak"]])
	import csv
	rows = list(csv.reader(io.StringIO(out)))
	assert rows[1] == ['he said "hi", ok', "'=SUM(A1)"]
	assert rows[2] == ["-5", "line\nbreak"]


def test_rejected_csv():
	out = ie.rejected_to_csv(["a"], [(3, "bad", ["x"])])
	assert out.splitlines() == ["row,error,a", "3,bad,x"]


def test_xlsx_roundtrip():
	openpyxl = pytest.importorskip("openpyxl")
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.append(["Title", "Qty", "Due"])
	ws.append(["A", 2, __import__("datetime").date(2024, 1, 5)])
	buf = io.BytesIO()
	wb.save(buf)
	h, r = ie.parse_xlsx(buf.getvalue())
	assert h == ["Title", "Qty", "Due"] and r == [["A", "2", "2024-01-05"]]


# ---- Track-Item: SEC-1/2/3/5/8

def _dr(doctype, headers, records, rejected):
	return sys.modules["ie_pkg.import_replace"].do_replace(doctype, headers, records, rejected, ie._result)


def test_csv_formula_prefixes_include_tab_and_cr():
	for p in ("=", "+", "-", "@", "\t", "\r"):
		assert p in ie._FORMULA_PREFIXES
	assert ie._csv_safe("\tcmd") == "'\tcmd"
	assert ie._csv_safe("\rcmd") == "'\rcmd"
	assert ie._csv_safe("@x") == "'@x"
	assert ie._csv_safe("-5") == "-5"


def test_strip_reserved_removes_server_keys():
	d = {k: 1 for k in sec.RESERVED_KEYS}
	d["title"] = "x"
	assert sec.strip_reserved(d) == {"title": "x"}


def test_xlsx_zip_bomb_rejected(monkeypatch):
	import zipfile
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		z.writestr("a.xml", "0" * 4096)
	monkeypatch.setattr(sec, "MAX_XLSX_UNCOMPRESSED", 1000)
	with pytest.raises(Exception):
		sec.check_xlsx_size(buf.getvalue())
	monkeypatch.setattr(sec, "MAX_XLSX_UNCOMPRESSED", 10_000)
	sec.check_xlsx_size(buf.getvalue())


def test_max_import_bytes_configurable():
	ie.frappe.conf = {}
	assert sec._max_import_bytes() == 20 * 1024 * 1024
	ie.frappe.conf = {"huf_table_import_max_mb": 1}
	assert sec._max_import_bytes() == 1024 * 1024


def _setup_load(monkeypatch, url_ok=True, perm_ok=True, size=10, private=False, owner="u@x.com"):
	from unittest import mock
	fr = ie.frappe
	fr.conf = {}
	fr.throw = lambda msg, *a, **k: (_ for _ in ()).throw(ValueError(msg))
	fr.PermissionError = PermissionError
	fr.ValidationError = ValueError
	fr.DoesNotExistError = LookupError
	fr.session = types.SimpleNamespace(user="u@x.com")
	fr.db = mock.MagicMock()
	fr.db.get_value.side_effect = lambda dt, f, *a, **k: "t_doctype" if dt == "Huf Data Table" else "FILE-1"
	doc = mock.MagicMock(file_size=size, is_private=private, owner=owner, file_name="a.csv")
	doc.get_content.return_value = b"a,b\n1,2\n"
	if not perm_ok:
		doc.check_permission.side_effect = PermissionError("no")
	fr.get_doc = mock.MagicMock(return_value=doc)
	monkeypatch.setattr(ie, "_can", lambda c: False)
	return doc


@pytest.mark.parametrize("url", ["/etc/passwd", "http://x/files/a.csv", "/private/files/../../x", "", None])
def test_load_rejects_non_files_urls(monkeypatch, url):
	_setup_load(monkeypatch)
	with pytest.raises(ValueError):
		ie._load("T", url)


def test_load_requires_read_permission_and_is_generic(monkeypatch):
	doc = _setup_load(monkeypatch, perm_ok=False)
	with pytest.raises(ValueError) as e:
		ie._load("T", "/private/files/a.csv")
	doc.get_content.assert_not_called()
	assert "not available" in str(e.value)


def test_load_private_file_of_other_owner_denied(monkeypatch):
	doc = _setup_load(monkeypatch, private=True, owner="other@x.com")
	with pytest.raises(ValueError):
		ie._load("T", "/private/files/a.csv")
	doc.get_content.assert_not_called()


def test_load_size_cap_before_get_content(monkeypatch):
	doc = _setup_load(monkeypatch, size=30 * 1024 * 1024)
	with pytest.raises(ValueError):
		ie._load("T", "/files/a.csv")
	doc.get_content.assert_not_called()


def test_load_happy_path(monkeypatch):
	_setup_load(monkeypatch, private=True)
	dt, headers, rows = ie._load("T", "/private/files/a.csv")
	assert dt == "t_doctype" and headers == ["a", "b"] and rows == [["1", "2"]]


def test_replace_deletes_nothing_when_any_row_invalid(monkeypatch):
	from unittest import mock
	fr = ie.frappe
	fr.db = mock.MagicMock()
	fr.get_meta = mock.MagicMock(return_value=types.SimpleNamespace(fields=[]))
	fr.get_all = mock.MagicMock(return_value=["R1", "R2"])
	fr.delete_doc = mock.MagicMock()
	fr.ValidationError = ValueError
	good, bad = mock.MagicMock(), mock.MagicMock()
	bad.run_method.side_effect = ValueError("bad row")
	fr.get_doc = mock.MagicMock(side_effect=[good, bad])
	res = _dr("DT", ["a"], [(2, {"a": 1}, ["1"]), (3, {"a": 2}, ["2"])], [])
	fr.delete_doc.assert_not_called()
	fr.db.savepoint.assert_not_called()
	assert res["inserted"] == 0 and res["rejected"] == 1 and "Nothing replaced" in res["note"]


def test_replace_duplicate_unique_value_in_batch_rejected(monkeypatch):
	from unittest import mock
	fr = ie.frappe
	fr.db = mock.MagicMock()
	fr.get_meta = mock.MagicMock(return_value=types.SimpleNamespace(fields=[types.SimpleNamespace(fieldname="code", get=lambda k: 1)]))
	fr.delete_doc = mock.MagicMock()
	fr.ValidationError = ValueError
	docs = [mock.MagicMock(), mock.MagicMock()]
	for d in docs:
		d.get.return_value = "X"
	fr.get_doc = mock.MagicMock(side_effect=docs)
	res = _dr("DT", ["code"], [(2, {"code": "X"}, ["X"]), (3, {"code": "X"}, ["X"])], [])
	fr.delete_doc.assert_not_called()
	assert res["rejected"] == 1


def test_replace_rolls_back_on_insert_failure(monkeypatch):
	from unittest import mock
	fr = ie.frappe
	fr.db = mock.MagicMock()
	fr.get_meta = mock.MagicMock(return_value=types.SimpleNamespace(fields=[]))
	fr.get_all = mock.MagicMock(return_value=["R1"])
	fr.delete_doc = mock.MagicMock()
	fr.ValidationError = ValueError
	d1, d2 = mock.MagicMock(), mock.MagicMock()
	d2.insert.side_effect = RuntimeError("db boom")
	fr.get_doc = mock.MagicMock(side_effect=[d1, d2])
	res = _dr("DT", ["a"], [(2, {"a": 1}, ["1"]), (3, {"a": 2}, ["2"])], [])
	fr.db.savepoint.assert_called_once_with("huf_replace")
	fr.db.rollback.assert_called_once_with(save_point="huf_replace")
	assert res["inserted"] == 0 and "rolled back" in res["note"]


def test_replace_success(monkeypatch):
	from unittest import mock
	fr = ie.frappe
	fr.db = mock.MagicMock()
	fr.get_meta = mock.MagicMock(return_value=types.SimpleNamespace(fields=[]))
	fr.get_all = mock.MagicMock(return_value=["R1"])
	fr.delete_doc = mock.MagicMock()
	fr.get_doc = mock.MagicMock(side_effect=[mock.MagicMock(), mock.MagicMock()])
	res = _dr("DT", ["a"], [(2, {"a": 1}, ["1"]), (3, {"a": 2}, ["2"])], [])
	assert res["inserted"] == 2 and not res["rejected"]
	fr.db.rollback.assert_not_called()


def test_csv_embedded_quotes_in_formula_cell_preserved():
	raw = 'name,link\nA,"=HYPERLINK(""http://x"")"\nB,"say ""hi"""\n'
	h, r = ie.parse_csv(raw)
	assert r[0][1] == '=HYPERLINK("http://x")'
	assert r[1][1] == 'say "hi"'


def test_csv_semicolon_delimiter_still_sniffed():
	h, r = ie.parse_csv('a;b\n1;"x ""y"" z"\n2;3\n')
	assert h == ["a", "b"] and r[0] == ["1", 'x "y" z']
