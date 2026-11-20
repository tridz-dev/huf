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

_spec = importlib.util.spec_from_file_location("ie_under_test", Path(__file__).with_name("import_export.py"))
ie = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ie)

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
