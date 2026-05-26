import frappe

ALLOWED_FIELD_TYPES = {
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Check",
	"Date",
	"Datetime",
	"Time",
	"Duration",
	"Select",
	"Link",
	"Rating",
	"Color",
	"Phone",
	"Section Break",
	"Column Break",
}

LAYOUT_FIELD_TYPES = {"Section Break", "Column Break"}

RESERVED_FIELDNAMES = {
	"name",
	"doctype",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
}


def validate_and_prepare_fields(fields: list[dict]) -> list[dict]:
	"""Validate field definitions and prepare for DocType creation."""
	validated = []
	fieldnames_seen = set()

	for i, field in enumerate(fields):
		fieldtype = field.get("fieldtype")
		if fieldtype not in ALLOWED_FIELD_TYPES:
			frappe.throw(f"Field type '{fieldtype}' is not allowed")

		label = field.get("label", "")
		if not label and fieldtype not in LAYOUT_FIELD_TYPES:
			frappe.throw(f"Field at position {i + 1} must have a label")

		fieldname = field.get("fieldname") or frappe.scrub(label or f"field_{i}")

		if fieldname in RESERVED_FIELDNAMES:
			frappe.throw(f"Field name '{fieldname}' is reserved and cannot be used")

		if fieldname in fieldnames_seen:
			frappe.throw(f"Duplicate field name: {fieldname}")
		fieldnames_seen.add(fieldname)

		validated_field = {
			"fieldname": fieldname,
			"fieldtype": fieldtype,
			"label": label or fieldname.replace("_", " ").title(),
			"idx": i + 1,
		}

		if fieldtype not in LAYOUT_FIELD_TYPES:
			for prop in (
				"reqd",
				"unique",
				"read_only",
				"hidden",
				"default",
				"description",
				"in_list_view",
				"non_negative",
			):
				if field.get(prop) is not None:
					validated_field[prop] = field[prop]

		if fieldtype == "Select" and field.get("options"):
			validated_field["options"] = field["options"]
		elif fieldtype == "Link" and field.get("options"):
			target = field["options"]
			if not frappe.db.exists("Huf Data Table", {"doctype_name": target}):
				frappe.throw(f"Link target '{target}' must be a Huf data table")
			validated_field["options"] = target

		if fieldtype in LAYOUT_FIELD_TYPES and field.get("label"):
			validated_field["label"] = field["label"]

		validated.append(validated_field)

	return validated


def resolve_autoname(autoname_method: str, title_field: str = "") -> str:
	"""Convert user-facing naming method to Frappe autoname string."""
	if autoname_method == "By Field" and title_field:
		return f"field:{title_field}"
	elif autoname_method == "Hash":
		return "hash"
	else:
		return "autoincrement"


def get_search_fields(fields: list[dict]) -> str:
	"""Extract first few data fields as search fields."""
	search = []
	for field in fields:
		if field["fieldtype"] not in LAYOUT_FIELD_TYPES and field["fieldtype"] in (
			"Data",
			"Small Text",
			"Text",
			"Long Text",
			"Phone",
		):
			search.append(field["fieldname"])
			if len(search) >= 3:
				break
	return ",".join(search)
