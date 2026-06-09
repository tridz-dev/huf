"""
ERPNext integration tools for Items, BOM, Inventory and Stock.
Uses direct Frappe DocType APIs – no external HTTP calls.
"""

import json
import frappe


def _erpnext_installed():
    try:
        return "erpnext" in frappe.get_installed_apps()
    except Exception:
        return False


def _error(msg):
    return json.dumps({"success": False, "error": msg}, default=str)


def _docstatus_label(ds):
    return {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(ds, str(ds))


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def _handle_get_items(**kwargs) -> str:
    """List ERPNext items with optional search and filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = [["Item", "disabled", "=", int(kwargs.get("disabled", 0))]]
        item_group = kwargs.get("item_group")
        is_stock_item = kwargs.get("is_stock_item")
        search = kwargs.get("search")
        limit = int(kwargs.get("limit", 20))

        if item_group:
            filters.append(["Item", "item_group", "=", item_group])
        if is_stock_item is not None:
            filters.append(["Item", "is_stock_item", "=", int(is_stock_item)])

        or_filters = []
        if search:
            or_filters = [
                ["Item", "item_code", "like", f"%{search}%"],
                ["Item", "item_name", "like", f"%{search}%"],
                ["Item", "item_group", "like", f"%{search}%"],
            ]

        fields = [
            "name",
            "item_code",
            "item_name",
            "item_group",
            "stock_uom",
            "is_stock_item",
            "disabled",
            "standard_rate",
            "valuation_rate",
        ]

        items = frappe.get_all(
            "Item",
            fields=fields,
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(items), "results": items}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Items Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_item(**kwargs) -> str:
    """Get a single ERPNext item by item_code with item_defaults child table."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Item", name):
            return _error(f"Item {name} not found")

        doc = frappe.get_doc("Item", name)
        result = doc.as_dict()
        return json.dumps({"success": True, "results": result}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Item Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_item_prices(**kwargs) -> str:
    """List ERPNext item prices for an item with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        item_code = kwargs.get("item_code")
        price_list = kwargs.get("price_list")
        buying = kwargs.get("buying")
        selling = kwargs.get("selling")
        limit = int(kwargs.get("limit", 20))

        if item_code:
            filters.append(["Item Price", "item_code", "=", item_code])
        if price_list:
            filters.append(["Item Price", "price_list", "=", price_list])
        if buying is not None:
            filters.append(["Item Price", "buying", "=", int(buying)])
        if selling is not None:
            filters.append(["Item Price", "selling", "=", int(selling)])

        fields = [
            "name",
            "item_code",
            "price_list",
            "buying",
            "selling",
            "currency",
            "price_list_rate",
            "uom",
            "valid_from",
        ]

        prices = frappe.get_all(
            "Item Price",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(prices), "results": prices}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Item Prices Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

def _handle_get_boms(**kwargs) -> str:
    """List ERPNext BOMs with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        item = kwargs.get("item")
        is_active = kwargs.get("is_active")
        is_default = kwargs.get("is_default")
        company = kwargs.get("company")
        limit = int(kwargs.get("limit", 20))

        if item:
            filters.append(["BOM", "item", "=", item])
        if is_active is not None:
            filters.append(["BOM", "is_active", "=", int(is_active)])
        if is_default is not None:
            filters.append(["BOM", "is_default", "=", int(is_default)])
        if company:
            filters.append(["BOM", "company", "=", company])

        fields = [
            "name",
            "item",
            "item_name",
            "quantity",
            "uom",
            "is_active",
            "is_default",
            "total_cost",
            "company",
            "modified",
        ]

        boms = frappe.get_all(
            "BOM",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(boms), "results": boms}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get BOMs Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_bom(**kwargs) -> str:
    """Get a single ERPNext BOM by name with items and operations child tables."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("BOM", name):
            return _error(f"BOM {name} not found")

        doc = frappe.get_doc("BOM", name)
        result = doc.as_dict()
        return json.dumps({"success": True, "results": result}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get BOM Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_create_bom(**kwargs) -> str:
    """Create a draft ERPNext BOM. Provide item, quantity, and line items."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        item = kwargs.get("item")
        if not item:
            return _error("item is required")

        doc = frappe.new_doc("BOM")
        doc.item = item
        doc.quantity = float(kwargs.get("quantity", 1))
        doc.uom = kwargs.get("uom", "")
        doc.company = kwargs.get("company", "")
        doc.is_default = int(kwargs.get("is_default", 1))
        doc.is_active = 1

        items = kwargs.get("items", [])
        if isinstance(items, str):
            items = json.loads(items)
        for row in items:
            doc.append(
                "items",
                {
                    "item_code": row.get("item_code"),
                    "qty": float(row.get("qty", 1)),
                    "uom": row.get("uom", ""),
                    "rate": float(row.get("rate", 0)),
                },
            )

        doc.insert(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name, "item": doc.item}}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Create BOM Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Stock & Inventory
# ---------------------------------------------------------------------------

def _handle_get_stock_balance(**kwargs) -> str:
    """Get current stock balance per item and warehouse from Stock Ledger Entry."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = {"is_cancelled": 0}
        item_code = kwargs.get("item_code")
        warehouse = kwargs.get("warehouse")
        as_of_date = kwargs.get("as_of_date")

        if item_code:
            filters["item_code"] = item_code
        if warehouse:
            filters["warehouse"] = warehouse
        if as_of_date:
            filters["posting_date"] = ["<=", as_of_date]

        sle_list = frappe.get_all(
            "Stock Ledger Entry",
            fields=[
                "item_code",
                "warehouse",
                "qty_after_transaction",
                "valuation_rate",
                "posting_date",
                "posting_time",
            ],
            filters=filters,
            order_by="posting_date desc, posting_time desc, creation desc",
            limit=500,
        )

        seen = {}
        for sle in sle_list:
            key = (sle["item_code"], sle["warehouse"])
            if key not in seen:
                seen[key] = sle

        results = []
        for sle in seen.values():
            results.append({
                "item_code": sle["item_code"],
                "warehouse": sle["warehouse"],
                "qty_after_transaction": sle["qty_after_transaction"],
                "valuation_rate": sle["valuation_rate"],
                "stock_value": (
                    (sle["qty_after_transaction"] or 0) * (sle["valuation_rate"] or 0)
                ),
            })

        return json.dumps({"success": True, "count": len(results), "results": results}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Stock Balance Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_stock_movements(**kwargs) -> str:
    """List ERPNext stock ledger entries with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = [["Stock Ledger Entry", "is_cancelled", "=", 0]]
        item_code = kwargs.get("item_code")
        warehouse = kwargs.get("warehouse")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        voucher_type = kwargs.get("voucher_type")
        limit = int(kwargs.get("limit", 50))

        if item_code:
            filters.append(["Stock Ledger Entry", "item_code", "=", item_code])
        if warehouse:
            filters.append(["Stock Ledger Entry", "warehouse", "=", warehouse])
        if from_date:
            filters.append(["Stock Ledger Entry", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Stock Ledger Entry", "posting_date", "<=", to_date])
        if voucher_type:
            filters.append(["Stock Ledger Entry", "voucher_type", "=", voucher_type])

        fields = [
            "name",
            "item_code",
            "warehouse",
            "posting_date",
            "voucher_type",
            "voucher_no",
            "actual_qty",
            "qty_after_transaction",
            "incoming_rate",
            "valuation_rate",
            "company",
        ]

        entries = frappe.get_all(
            "Stock Ledger Entry",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc, posting_time desc",
        )

        return json.dumps({"success": True, "count": len(entries), "results": entries}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Stock Movements Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_stock_entries(**kwargs) -> str:
    """List ERPNext stock entry documents with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        stock_entry_type = kwargs.get("stock_entry_type")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        docstatus = kwargs.get("docstatus")
        limit = int(kwargs.get("limit", 20))

        if stock_entry_type:
            filters.append(["Stock Entry", "stock_entry_type", "=", stock_entry_type])
        if from_date:
            filters.append(["Stock Entry", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Stock Entry", "posting_date", "<=", to_date])
        if docstatus is not None:
            filters.append(["Stock Entry", "docstatus", "=", int(docstatus)])

        fields = [
            "name",
            "stock_entry_type",
            "posting_date",
            "company",
            "docstatus",
        ]

        entries = frappe.get_all(
            "Stock Entry",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc",
        )

        for entry in entries:
            entry["docstatus_label"] = _docstatus_label(entry.get("docstatus"))

        return json.dumps({"success": True, "count": len(entries), "results": entries}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Stock Entries Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_warehouses(**kwargs) -> str:
    """List ERPNext warehouses with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = [["Warehouse", "disabled", "=", int(kwargs.get("disabled", 0))]]
        company = kwargs.get("company")
        warehouse_type = kwargs.get("warehouse_type")
        limit = int(kwargs.get("limit", 50))

        if company:
            filters.append(["Warehouse", "company", "=", company])
        if warehouse_type:
            filters.append(["Warehouse", "warehouse_type", "=", warehouse_type])

        fields = [
            "name",
            "warehouse_name",
            "warehouse_type",
            "company",
            "parent_warehouse",
            "disabled",
        ]

        warehouses = frappe.get_all(
            "Warehouse",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="warehouse_name asc",
        )

        return json.dumps({"success": True, "count": len(warehouses), "results": warehouses}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Warehouses Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_delivery_notes(**kwargs) -> str:
    """List ERPNext delivery notes with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        customer = kwargs.get("customer")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        docstatus = kwargs.get("docstatus")
        limit = int(kwargs.get("limit", 20))

        if customer:
            filters.append(["Delivery Note", "customer", "=", customer])
        if from_date:
            filters.append(["Delivery Note", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Delivery Note", "posting_date", "<=", to_date])
        if docstatus is not None:
            filters.append(["Delivery Note", "docstatus", "=", int(docstatus)])

        fields = [
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "status",
            "docstatus",
        ]

        notes = frappe.get_all(
            "Delivery Note",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc",
        )

        for note in notes:
            note["docstatus_label"] = _docstatus_label(note.get("docstatus"))

        return json.dumps({"success": True, "count": len(notes), "results": notes}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Delivery Notes Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_purchase_receipts(**kwargs) -> str:
    """List ERPNext purchase receipts with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        supplier = kwargs.get("supplier")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        docstatus = kwargs.get("docstatus")
        limit = int(kwargs.get("limit", 20))

        if supplier:
            filters.append(["Purchase Receipt", "supplier", "=", supplier])
        if from_date:
            filters.append(["Purchase Receipt", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Purchase Receipt", "posting_date", "<=", to_date])
        if docstatus is not None:
            filters.append(["Purchase Receipt", "docstatus", "=", int(docstatus)])

        fields = [
            "name",
            "supplier",
            "supplier_name",
            "posting_date",
            "status",
            "docstatus",
        ]

        receipts = frappe.get_all(
            "Purchase Receipt",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc",
        )

        for receipt in receipts:
            receipt["docstatus_label"] = _docstatus_label(receipt.get("docstatus"))

        return json.dumps({"success": True, "count": len(receipts), "results": receipts}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Purchase Receipts Error: {e}", "ERPNext Tool")
        return _error(str(e))


def handle_action(**kwargs) -> str:
    action = kwargs.get("action", "").strip().lower()
    dispatch = {
        "list_items": _handle_get_items,
        "get_item": _handle_get_item,
        "item_prices": _handle_get_item_prices,
        "stock_balance": _handle_get_stock_balance,
        "stock_movements": _handle_get_stock_movements,
        "list_stock_entries": _handle_get_stock_entries,
        "list_warehouses": _handle_get_warehouses,
        "list_delivery_notes": _handle_get_delivery_notes,
        "list_purchase_receipts": _handle_get_purchase_receipts,
        "list_boms": _handle_get_boms,
        "get_bom": _handle_get_bom,
        "create_bom": _handle_create_bom,
    }
    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Valid: {valid}"}, default=str)
    return handler(**kwargs)
