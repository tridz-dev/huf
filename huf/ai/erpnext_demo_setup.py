"""
Demo/dev convenience: create the minimum ERPNext master data a fresh site
needs before a Procedure that touches Customers, Sales Invoices, or Payment
Entries can actually run (e.g. Benchmark 1's customer/invoice/payment
scenario).

A fresh ERPNext install leaves several required "leaf" records missing
until someone runs the setup wizard or manually creates them: a Warehouse
Type, an Item Group leaf, a Customer Group leaf, a Territory, a selling
Price List, and a Fiscal Year covering today. ``ensure_erpnext_demo_masters``
creates only what is missing, is safe to call repeatedly (every write is
guarded by a ``frappe.db.exists`` check first), and is a no-op if ERPNext
is not installed on the site at all.

Call it from a bench console for a scripted/headless setup::

    bench --site <site> console
    >>> import frappe
    >>> frappe.set_user("Administrator")
    >>> from huf.ai.erpnext_demo_setup import ensure_erpnext_demo_masters
    >>> ensure_erpnext_demo_masters()

Or via the whitelisted API (System Manager only)::

    POST /api/method/huf.ai.erpnext_demo_setup.run_ensure_erpnext_demo_masters
"""

import frappe
from frappe.utils import getdate, today

from huf.permissions import SYSTEM_MANAGER

WAREHOUSE_TYPE = "Huf Demo"
ITEM_GROUP = "Huf Demo Items"
ITEM_GROUP_PARENT = "All Item Groups"
CUSTOMER_GROUP = "Huf Demo Customers"
CUSTOMER_GROUP_PARENT = "All Customer Groups"
TERRITORY = "Huf Demo Territory"
TERRITORY_PARENT = "All Territories"
PRICE_LIST = "Huf Demo Price List"
FALLBACK_UOM = "Nos"


def _erpnext_installed() -> bool:
	try:
		return "erpnext" in frappe.get_installed_apps()
	except Exception:
		return False


def _ensure_warehouse_type(created: list, already_present: list) -> None:
	label = f"Warehouse Type {WAREHOUSE_TYPE}"
	if frappe.db.exists("Warehouse Type", WAREHOUSE_TYPE):
		already_present.append(label)
		return
	frappe.get_doc({"doctype": "Warehouse Type", "name": WAREHOUSE_TYPE}).insert(
		ignore_permissions=True
	)
	created.append(label)


def _ensure_uom(created: list, already_present: list) -> None:
	# ERPNext's own install fixtures ship a "Nos" UOM by default, so on any
	# normal ERPNext site this is a no-op. Only create it if the site
	# genuinely has none -- defensive against a stripped-down install.
	label = f"UOM {FALLBACK_UOM}"
	if frappe.db.exists("UOM", FALLBACK_UOM):
		already_present.append(label)
		return
	frappe.get_doc(
		{"doctype": "UOM", "uom_name": FALLBACK_UOM, "must_be_whole_number": 1}
	).insert(ignore_permissions=True)
	created.append(label)


def _ensure_item_group(created: list, already_present: list) -> None:
	label = f"Item Group {ITEM_GROUP}"
	if frappe.db.exists("Item Group", ITEM_GROUP):
		already_present.append(label)
		return
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": ITEM_GROUP,
			"parent_item_group": ITEM_GROUP_PARENT
			if frappe.db.exists("Item Group", ITEM_GROUP_PARENT)
			else None,
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	created.append(label)


def _ensure_customer_group(created: list, already_present: list) -> None:
	label = f"Customer Group {CUSTOMER_GROUP}"
	if frappe.db.exists("Customer Group", CUSTOMER_GROUP):
		already_present.append(label)
		return
	frappe.get_doc(
		{
			"doctype": "Customer Group",
			"customer_group_name": CUSTOMER_GROUP,
			"parent_customer_group": CUSTOMER_GROUP_PARENT
			if frappe.db.exists("Customer Group", CUSTOMER_GROUP_PARENT)
			else None,
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	created.append(label)


def _ensure_territory(created: list, already_present: list) -> None:
	label = f"Territory {TERRITORY}"
	if frappe.db.exists("Territory", TERRITORY):
		already_present.append(label)
		return
	frappe.get_doc(
		{
			"doctype": "Territory",
			"territory_name": TERRITORY,
			"parent_territory": TERRITORY_PARENT
			if frappe.db.exists("Territory", TERRITORY_PARENT)
			else None,
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	created.append(label)


def _ensure_price_list(created: list, already_present: list) -> None:
	label = f"Price List {PRICE_LIST}"
	if frappe.db.exists("Price List", PRICE_LIST):
		already_present.append(label)
		return
	frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": PRICE_LIST,
			"selling": 1,
			"currency": frappe.db.get_default("currency") or "USD",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	created.append(label)


def _ensure_fiscal_year(created: list, already_present: list) -> None:
	label_prefix = "Fiscal Year covering"
	today_date = getdate(today())

	covering = frappe.db.sql(
		"""
		select name from `tabFiscal Year`
		where %(today)s between year_start_date and year_end_date
		limit 1
		""",
		{"today": today_date},
	)
	if covering:
		already_present.append(f"{label_prefix} {today_date} ({covering[0][0]})")
		return

	year_start = today_date.replace(month=1, day=1)
	year_end = today_date.replace(month=12, day=31)
	doc = frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": str(today_date.year),
			"year_start_date": year_start,
			"year_end_date": year_end,
		}
	)
	doc.insert(ignore_permissions=True)
	created.append(f"{label_prefix} {today_date} ({doc.name})")


def ensure_erpnext_demo_masters() -> dict:
	"""Create the minimum ERPNext master data needed to exercise a demo
	Procedure (customer / invoice / payment style scenarios), idempotently.

	Safe to call repeatedly: every record is created only if missing.
	No-ops cleanly (returns ``skipped_reason``) if ERPNext isn't installed.
	Requires the System Manager role when called over the whitelisted API
	(:func:`run_ensure_erpnext_demo_masters`); no role check is enforced
	when this function is imported and called directly (e.g. from
	``bench console``), since that already requires site/database access.

	Returns:
	    dict with ``created`` (list[str]), ``already_present`` (list[str]),
	    and ``skipped_reason`` (str | None).
	"""
	if not _erpnext_installed():
		return {"created": [], "already_present": [], "skipped_reason": "erpnext not installed"}

	created: list = []
	already_present: list = []

	_ensure_warehouse_type(created, already_present)
	_ensure_uom(created, already_present)
	_ensure_item_group(created, already_present)
	_ensure_customer_group(created, already_present)
	_ensure_territory(created, already_present)
	_ensure_price_list(created, already_present)
	_ensure_fiscal_year(created, already_present)

	return {"created": created, "already_present": already_present, "skipped_reason": None}


@frappe.whitelist()
def run_ensure_erpnext_demo_masters() -> dict:
	"""POST /api/method/huf.ai.erpnext_demo_setup.run_ensure_erpnext_demo_masters

	Whitelisted, System-Manager-gated wrapper around
	:func:`ensure_erpnext_demo_masters`, for the settings-page button and
	any other HTTP caller.
	"""
	frappe.only_for(SYSTEM_MANAGER)
	return ensure_erpnext_demo_masters()
