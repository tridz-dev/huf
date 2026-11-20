"""CSV writing helpers for Huf data table export (split out of import_export.py)."""

import csv
import datetime
import io

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _is_number(v: str) -> bool:
	try:
		float(v.replace(",", ""))
		return True
	except ValueError:
		return False


def to_csv_text(headers, rows) -> str:
	buf = io.StringIO()
	w = csv.writer(buf, lineterminator="\n")
	w.writerow(headers)
	for r in rows:
		w.writerow([_csv_safe(c) for c in r])
	return buf.getvalue()


def _csv_safe(v):
	if v is None:
		return ""
	if isinstance(v, (datetime.datetime, datetime.date, datetime.timedelta)):
		return str(v)
	s = str(v)
	# Neutralise spreadsheet formula injection; leave plain negative numbers alone.
	if s.startswith(_FORMULA_PREFIXES) and not (s[0] in "+-" and _is_number(s)):
		return "'" + s
	return s


def rejected_to_csv(headers, rejected) -> str:
	"""rejected: list of (row_number, message, raw_row)."""
	return to_csv_text(["row", "error", *headers], [[n, m, *r] for n, m, r in rejected])
