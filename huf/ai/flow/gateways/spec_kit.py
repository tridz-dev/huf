"""Small builders that keep every gateway trigger spec in one frozen shape.

The shape (see ``registry.get_gateway_trigger_spec``) is pinned by a JSON snapshot test; adding a key to a param or a
payload field is a contract change that needs coordinator approval. Pure Python, no frappe.
"""

from __future__ import annotations

PARAM_TYPES = ("text", "textarea", "select", "multiselect", "boolean", "number", "tags", "people")
PAYLOAD_TYPES = ("text", "number", "yes_no", "list", "datetime", "record")
SECTIONS = ("setup", "more")

# Which JSON value each param type accepts (see registry.param_problems).
LIST_TYPES = ("multiselect", "tags", "people")
STRING_TYPES = ("text", "textarea", "select")


def option(value: str, label: str) -> dict:
	return {"value": value, "label": label}


def param(
	key: str,
	label: str,
	type: str,
	*,
	help: str = "",
	options: list[tuple[str, str]] | None = None,
	required: bool = False,
	default=None,
	multiple: bool = False,
	show_when: dict | None = None,
	section: str = "setup",
) -> dict:
	"""One filter the node offers. ``show_when`` is ``{"key": <other param>, "in": [values]}`` or None."""
	assert type in PARAM_TYPES, type
	assert section in SECTIONS, section
	return {
		"key": key,
		"label": label,
		"help": help,
		"type": type,
		"options": [option(v, lbl) for v, lbl in (options or [])],
		"required": required,
		"default": default,
		"multiple": multiple,
		"show_when": show_when,
		"section": section,
	}


def field(
	name: str,
	label: str,
	type: str,
	sample,
	*,
	customer_provided: bool = False,
	sensitive: bool = False,
	advanced: bool = False,
) -> dict:
	"""One value a later step can read as ``input.<name>``."""
	assert type in PAYLOAD_TYPES, type
	return {
		"path": f"input.{name}",
		"label": label,
		"type": type,
		"sample": sample,
		"customer_provided": customer_provided,
		"sensitive": sensitive,
		"advanced": advanced,
	}


def sample_payload(fields: list[dict]) -> dict:
	"""``{name: sample}`` built from the field list, so the sample can never drift from the declared fields."""
	return {f["path"].removeprefix("input."): f["sample"] for f in fields}
