"""Fields of a document type, as the "Use data" picker names them (a data trigger knows its fields without a sample).

Pure over duck-typed field rows (anything with ``fieldname``, ``fieldtype``, ``label``, ``options``, ``hidden``,
``reqd``): the whitelisted API hands in the real Frappe meta, the tests hand in simple objects.

A data trigger starts a run with the document's own fields (``input.<fieldname>``). A *Link* field holds only the linked
record's name (``input.customer`` = ``CUST-0001``), so "Customer > Credit limit" cannot be read from that. Instead the
trigger adds ``input._links.<fieldname>.<other field>`` with the linked record's plain fields
(``triggers.build_doc_event_payload``); ``link_targets`` and ``LINK_KEY`` keep the two sides in agreement.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from huf.ai.flow.catalog.fields import IDENT, MAX_TEXT, sample_for

LINK_KEY = "_links"
MAX_LINKS = 6
MAX_LINK_FIELDS = 12
MAX_DOC_FIELDS = 60

NUMBER = {"Int", "Float", "Currency", "Percent", "Rating", "Duration"}
DATE = {"Date", "Datetime", "Time"}
YES_NO = {"Check"}
TEXT = {
	"Data", "Small Text", "Text", "Long Text", "Text Editor", "Markdown Editor", "HTML Editor", "Select", "Link",
	"Dynamic Link", "Phone", "Read Only", "Code", "Attach", "Attach Image", "Color", "Autocomplete",
}
LIST = {"Table", "Table MultiSelect"}
#: Layout, secrets and widgets: never data a person would pick.
SKIPPED = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold", "Image", "Password",
	"Geolocation", "Signature", "Barcode", "Icon", "JSON",
}

#: Always on a document, in the words people use.
STANDARD = (
	("name", "ID", "text"),
	("creation", "Created on", "date"),
	("modified", "Last changed", "date"),
	("owner", "Created by", "text"),
)


def kind_of(fieldtype: str | None) -> str | None:
	if fieldtype in SKIPPED or not fieldtype:
		return None
	if fieldtype in NUMBER:
		return "number"
	if fieldtype in DATE:
		return "date"
	if fieldtype in YES_NO:
		return "yes_no"
	if fieldtype in LIST:
		return "list"
	if fieldtype in TEXT:
		return "text"
	return None


def _label(df: Any) -> str:
	label = getattr(df, "label", None) or getattr(df, "fieldname", "")
	return " ".join(str(label).split())


def _usable(df: Any) -> bool:
	name = getattr(df, "fieldname", None)
	return bool(name) and bool(IDENT.match(name)) and not name.startswith("_") and kind_of(getattr(df, "fieldtype", None)) is not None


def link_targets(fields: Iterable[Any], limit: int = MAX_LINKS) -> list[tuple[str, str, str]]:
	"""``[(fieldname, label, linked doctype)]`` for the first Link fields worth following."""
	out: list[tuple[str, str, str]] = []
	for df in fields:
		if getattr(df, "fieldtype", None) == "Link" and _usable(df) and getattr(df, "options", None) and not getattr(df, "hidden", 0):
			out.append((df.fieldname, _label(df), df.options))
		if len(out) >= limit:
			break
	return out


def plain_fields(fields: Iterable[Any], limit: int = MAX_LINK_FIELDS) -> list[Any]:
	"""Scalar fields of a linked record that are safe and useful to offer (no tables, no hidden, no secrets)."""
	out = []
	for df in fields:
		if _usable(df) and kind_of(df.fieldtype) not in ("list",) and not getattr(df, "hidden", 0):
			out.append(df)
		if len(out) >= limit:
			break
	return out


def doctype_fields(
	fields: Iterable[Any],
	record: dict | None = None,
	child_fields: Callable[[str], Iterable[Any]] | None = None,
	link_meta: Callable[[str], Iterable[Any]] | None = None,
	budget: int = MAX_DOC_FIELDS,
) -> list[dict]:
	"""Catalog fields (paths start with ``input``) for a document type; ``record`` supplies sample values."""
	record = record or {}
	fields = list(fields)
	out: list[dict] = []

	def sample(key: str, row: dict | None = None):
		src = record if row is None else row
		return sample_for(src.get(key)) if isinstance(src, dict) else None

	for key, label, kind in STANDARD:
		out.append({"path": f"input.{key}", "label": label, "type": kind, "sample": sample(key)})
	for df in fields:
		if len(out) >= budget:
			break
		if not _usable(df) or getattr(df, "hidden", 0):
			continue
		kind = kind_of(df.fieldtype)
		field: dict = {"path": f"input.{df.fieldname}", "label": _label(df), "type": kind, "sample": sample(df.fieldname)}
		if kind == "list":
			rows = record.get(df.fieldname) if isinstance(record.get(df.fieldname), list) else []
			item_fields = []
			if child_fields and getattr(df, "options", None):
				for child in plain_fields(child_fields(df.options)):
					first = rows[0] if rows and isinstance(rows[0], dict) else {}
					item_fields.append(
						{"path": child.fieldname, "label": _label(child), "type": kind_of(child.fieldtype), "sample": sample_for(first.get(child.fieldname))}
					)
			field["list"] = {"count": len(rows), "item_type": "object", "item_fields": item_fields}
			field["sample"] = f"{len(rows)} item{'s' if len(rows) != 1 else ''}" if rows else None
		out.append(field)
	if link_meta:
		links = record.get(LINK_KEY) if isinstance(record.get(LINK_KEY), dict) else {}
		for fieldname, label, doctype in link_targets(fields):
			row = links.get(fieldname) if isinstance(links.get(fieldname), dict) else {}
			for df in plain_fields(link_meta(doctype)):
				if len(out) >= budget + MAX_LINKS * MAX_LINK_FIELDS:
					break
				out.append(
					{
						"path": f"input.{LINK_KEY}.{fieldname}.{df.fieldname}",
						"label": f"{label} > {_label(df)}"[: MAX_TEXT],
						"type": kind_of(df.fieldtype),
						"sample": sample_for(row.get(df.fieldname)),
					}
				)
	return out
