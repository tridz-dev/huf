"""
ERPNext integration tools for financial and business documents.
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
# Sales Invoice
# ---------------------------------------------------------------------------

def _handle_get_sales_invoices(**kwargs) -> str:
    """List Sales Invoices with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        customer = kwargs.get("customer")
        status = kwargs.get("status")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        limit = int(kwargs.get("limit", 20))

        if customer:
            filters.append(["Sales Invoice", "customer", "=", customer])

        if status:
            if status == "Draft":
                filters.append(["Sales Invoice", "docstatus", "=", 0])
            elif status == "Submitted":
                filters.append(["Sales Invoice", "docstatus", "=", 1])
            elif status == "Cancelled":
                filters.append(["Sales Invoice", "docstatus", "=", 2])
            else:
                filters.append(["Sales Invoice", "status", "=", status])

        if from_date:
            filters.append(["Sales Invoice", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Sales Invoice", "posting_date", "<=", to_date])

        fields = [
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "due_date",
            "grand_total",
            "outstanding_amount",
            "status",
            "docstatus",
        ]

        invoices = frappe.get_all(
            "Sales Invoice",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc",
        )

        for inv in invoices:
            inv["docstatus_label"] = _docstatus_label(inv.get("docstatus"))

        return json.dumps({"success": True, "count": len(invoices), "results": invoices}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Sales Invoices Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_sales_invoice(**kwargs) -> str:
    """Get a single Sales Invoice by name/ID with all fields including items."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Sales Invoice", name):
            return _error(f"Sales Invoice {name} not found")

        doc = frappe.get_doc("Sales Invoice", name)
        result = doc.as_dict()
        result["docstatus_label"] = _docstatus_label(result.get("docstatus"))
        return json.dumps({"success": True, "results": result}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Sales Invoice Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_create_sales_invoice(**kwargs) -> str:
    """Create a draft Sales Invoice."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        customer = kwargs.get("customer")
        if not customer:
            return _error("customer is required")

        doc = frappe.new_doc("Sales Invoice")
        doc.customer = customer
        doc.company = kwargs.get("company", "")
        doc.posting_date = kwargs.get("posting_date", "")

        items = kwargs.get("items", [])
        if isinstance(items, str):
            items = json.loads(items)
        for item in items:
            doc.append(
                "items",
                {
                    "item_code": item.get("item_code"),
                    "qty": item.get("qty", 1),
                    "rate": item.get("rate", 0),
                },
            )

        doc.insert(ignore_permissions=True)
        return json.dumps(
            {"success": True, "results": {"name": doc.name, "customer": doc.customer}}
        )
    except Exception as e:
        frappe.log_error(f"ERPNext Create Sales Invoice Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Purchase Invoice
# ---------------------------------------------------------------------------

def _handle_get_purchase_invoices(**kwargs) -> str:
    """List Purchase Invoices with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        supplier = kwargs.get("supplier")
        status = kwargs.get("status")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        limit = int(kwargs.get("limit", 20))

        if supplier:
            filters.append(["Purchase Invoice", "supplier", "=", supplier])

        if status:
            if status == "Draft":
                filters.append(["Purchase Invoice", "docstatus", "=", 0])
            elif status == "Submitted":
                filters.append(["Purchase Invoice", "docstatus", "=", 1])
            elif status == "Cancelled":
                filters.append(["Purchase Invoice", "docstatus", "=", 2])
            else:
                filters.append(["Purchase Invoice", "status", "=", status])

        if from_date:
            filters.append(["Purchase Invoice", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Purchase Invoice", "posting_date", "<=", to_date])

        fields = [
            "name",
            "supplier",
            "supplier_name",
            "posting_date",
            "due_date",
            "bill_no",
            "total",
            "grand_total",
            "outstanding_amount",
            "status",
            "docstatus",
        ]

        invoices = frappe.get_all(
            "Purchase Invoice",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc",
        )

        for inv in invoices:
            inv["docstatus_label"] = _docstatus_label(inv.get("docstatus"))

        return json.dumps({"success": True, "count": len(invoices), "results": invoices}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Purchase Invoices Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_purchase_invoice(**kwargs) -> str:
    """Get a single Purchase Invoice by name/ID with all fields including items."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Purchase Invoice", name):
            return _error(f"Purchase Invoice {name} not found")

        doc = frappe.get_doc("Purchase Invoice", name)
        result = doc.as_dict()
        result["docstatus_label"] = _docstatus_label(result.get("docstatus"))
        return json.dumps({"success": True, "results": result}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Purchase Invoice Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Payment Entry
# ---------------------------------------------------------------------------

def _handle_get_payments(**kwargs) -> str:
    """List Payment Entries with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        party_type = kwargs.get("party_type")
        party = kwargs.get("party")
        payment_type = kwargs.get("payment_type")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        limit = int(kwargs.get("limit", 20))

        if party_type:
            filters.append(["Payment Entry", "party_type", "=", party_type])
        if party:
            filters.append(["Payment Entry", "party", "=", party])
        if payment_type:
            filters.append(["Payment Entry", "payment_type", "=", payment_type])
        if from_date:
            filters.append(["Payment Entry", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["Payment Entry", "posting_date", "<=", to_date])

        fields = [
            "name",
            "payment_type",
            "party_type",
            "party",
            "party_name",
            "paid_amount",
            "posting_date",
            "mode_of_payment",
            "status",
        ]

        payments = frappe.get_all(
            "Payment Entry",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date desc",
        )

        return json.dumps({"success": True, "count": len(payments), "results": payments}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Payments Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_create_payment(**kwargs) -> str:
    """Create a draft Payment Entry. Optionally link to an invoice."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        payment_type = kwargs.get("payment_type")
        party_type = kwargs.get("party_type")
        party = kwargs.get("party")
        if not payment_type:
            return _error("payment_type is required")
        if not party_type:
            return _error("party_type is required")
        if not party:
            return _error("party is required")

        doc = frappe.new_doc("Payment Entry")
        doc.payment_type = payment_type
        doc.party_type = party_type
        doc.party = party
        doc.company = kwargs.get("company", "")
        doc.posting_date = kwargs.get("posting_date", "")
        doc.mode_of_payment = kwargs.get("mode_of_payment", "")
        doc.paid_from = kwargs.get("paid_from", "")
        doc.paid_to = kwargs.get("paid_to", "")
        doc.paid_amount = float(kwargs.get("paid_amount", 0))
        doc.received_amount = float(kwargs.get("received_amount", doc.paid_amount))

        invoice_name = kwargs.get("invoice_name")
        if invoice_name:
            ref_doctype = None
            if frappe.db.exists("Sales Invoice", invoice_name):
                ref_doctype = "Sales Invoice"
            elif frappe.db.exists("Purchase Invoice", invoice_name):
                ref_doctype = "Purchase Invoice"

            if ref_doctype:
                doc.append(
                    "references",
                    {
                        "reference_doctype": ref_doctype,
                        "reference_name": invoice_name,
                        "allocated_amount": doc.paid_amount,
                    },
                )

        doc.insert(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name}}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Create Payment Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------

def _handle_get_quotations(**kwargs) -> str:
    """List Quotations with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        party_name = kwargs.get("party_name")
        status = kwargs.get("status")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        limit = int(kwargs.get("limit", 20))

        if party_name:
            filters.append(["Quotation", "party_name", "=", party_name])
        if status:
            filters.append(["Quotation", "status", "=", status])
        if from_date:
            filters.append(["Quotation", "transaction_date", ">=", from_date])
        if to_date:
            filters.append(["Quotation", "transaction_date", "<=", to_date])

        fields = [
            "name",
            "quotation_to",
            "party_name",
            "customer_name",
            "company",
            "transaction_date",
            "valid_till",
            "currency",
            "total",
            "grand_total",
            "status",
            "docstatus",
        ]

        quotes = frappe.get_all(
            "Quotation",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="transaction_date desc",
        )

        for q in quotes:
            q["docstatus_label"] = _docstatus_label(q.get("docstatus"))

        return json.dumps({"success": True, "count": len(quotes), "results": quotes}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Quotations Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_create_quotation(**kwargs) -> str:
    """Create a draft Quotation."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        quotation_to = kwargs.get("quotation_to")
        party_name = kwargs.get("party_name")
        if not quotation_to:
            return _error("quotation_to is required")
        if not party_name:
            return _error("party_name is required")

        doc = frappe.new_doc("Quotation")
        doc.quotation_to = quotation_to
        doc.party_name = party_name
        doc.company = kwargs.get("company", "")
        doc.transaction_date = kwargs.get("transaction_date", "")
        doc.valid_till = kwargs.get("valid_till", "")

        items = kwargs.get("items", [])
        if isinstance(items, str):
            items = json.loads(items)
        for item in items:
            doc.append(
                "items",
                {
                    "item_code": item.get("item_code"),
                    "qty": item.get("qty", 1),
                    "rate": item.get("rate", 0),
                },
            )

        doc.insert(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name}}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Create Quotation Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

def _handle_get_customers(**kwargs) -> str:
    """List/search Customers with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        customer_group = kwargs.get("customer_group")
        territory = kwargs.get("territory")
        search = kwargs.get("search")
        limit = int(kwargs.get("limit", 20))

        if customer_group:
            filters.append(["Customer", "customer_group", "=", customer_group])
        if territory:
            filters.append(["Customer", "territory", "=", territory])

        or_filters = []
        if search:
            or_filters = [
                ["Customer", "name", "like", f"%{search}%"],
                ["Customer", "customer_name", "like", f"%{search}%"],
                ["Customer", "customer_group", "like", f"%{search}%"],
            ]

        fields = [
            "name",
            "customer_name",
            "customer_type",
            "customer_group",
            "territory",
            "default_currency",
            "disabled",
        ]

        customers = frappe.get_all(
            "Customer",
            fields=fields,
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(customers), "results": customers}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Customers Error: {e}", "ERPNext Tool")
        return _error(str(e))


def _handle_get_customer(**kwargs) -> str:
    """Get a single Customer by name/ID with linked addresses and contacts."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Customer", name):
            return _error(f"Customer {name} not found")

        doc = frappe.get_doc("Customer", name)
        result = doc.as_dict()

        # Linked addresses via Dynamic Link
        address_links = frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": name,
                "parenttype": "Address",
            },
            fields=["parent"],
        )
        result["addresses"] = []
        for link in address_links:
            addr = frappe.get_doc("Address", link.parent)
            result["addresses"].append(addr.as_dict())

        # Linked contacts via Dynamic Link
        contact_links = frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": name,
                "parenttype": "Contact",
            },
            fields=["parent"],
        )
        result["contacts"] = []
        for link in contact_links:
            contact = frappe.get_doc("Contact", link.parent)
            result["contacts"].append(contact.as_dict())

        return json.dumps({"success": True, "results": result}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Customer Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# GL Entry (read-only)
# ---------------------------------------------------------------------------

def _handle_get_account_ledger(**kwargs) -> str:
    """Query GL Entries for an account with running balance. GL Entry is read-only."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        account = kwargs.get("account")
        if not account:
            return _error("account is required")

        filters = [["GL Entry", "account", "=", account]]
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        party_type = kwargs.get("party_type")
        party = kwargs.get("party")
        limit = int(kwargs.get("limit", 50))

        if from_date:
            filters.append(["GL Entry", "posting_date", ">=", from_date])
        if to_date:
            filters.append(["GL Entry", "posting_date", "<=", to_date])
        if party_type:
            filters.append(["GL Entry", "party_type", "=", party_type])
        if party:
            filters.append(["GL Entry", "party", "=", party])

        fields = [
            "name",
            "account",
            "party_type",
            "party",
            "posting_date",
            "debit",
            "credit",
            "voucher_type",
            "voucher_no",
            "cost_center",
            "remarks",
        ]

        entries = frappe.get_all(
            "GL Entry",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="posting_date asc, creation asc",
        )

        running_balance = 0.0
        for entry in entries:
            running_balance += float(entry.get("debit", 0) or 0) - float(entry.get("credit", 0) or 0)
            entry["running_balance"] = running_balance

        return json.dumps({"success": True, "count": len(entries), "results": entries}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get Account Ledger Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Journal Entry
# ---------------------------------------------------------------------------

def _handle_create_journal_entry(**kwargs) -> str:
    """Create a draft Journal Entry with account lines."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        doc = frappe.new_doc("Journal Entry")
        doc.voucher_type = kwargs.get("voucher_type", "Journal Entry")
        doc.posting_date = kwargs.get("posting_date", "")
        doc.company = kwargs.get("company", "")
        doc.user_remark = kwargs.get("user_remark", "")

        accounts = kwargs.get("accounts", [])
        if isinstance(accounts, str):
            accounts = json.loads(accounts)
        for acc in accounts:
            doc.append(
                "accounts",
                {
                    "account": acc.get("account"),
                    "debit_in_account_currency": acc.get("debit_in_account_currency", 0),
                    "credit_in_account_currency": acc.get("credit_in_account_currency", 0),
                    "party_type": acc.get("party_type", ""),
                    "party": acc.get("party", ""),
                    "cost_center": acc.get("cost_center", ""),
                },
            )

        doc.insert(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name}}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Create Journal Entry Error: {e}", "ERPNext Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Request for Quotation
# ---------------------------------------------------------------------------

def _handle_get_rfqs(**kwargs) -> str:
    """List Request for Quotation documents with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        status = kwargs.get("status")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        limit = int(kwargs.get("limit", 20))

        if status:
            filters.append(["Request for Quotation", "status", "=", status])
        if from_date:
            filters.append(["Request for Quotation", "transaction_date", ">=", from_date])
        if to_date:
            filters.append(["Request for Quotation", "transaction_date", "<=", to_date])

        fields = ["name", "company", "transaction_date", "status"]

        rfqs = frappe.get_all(
            "Request for Quotation",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="transaction_date desc",
        )

        return json.dumps({"success": True, "count": len(rfqs), "results": rfqs}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Get RFQs Error: {e}", "ERPNext Tool")
        return _error(str(e))


def handle_action(**kwargs) -> str:
    action = kwargs.get("action", "").strip().lower()
    dispatch = {
        "list_sales_invoices": _handle_get_sales_invoices,
        "get_sales_invoice": _handle_get_sales_invoice,
        "create_sales_invoice": _handle_create_sales_invoice,
        "list_purchase_invoices": _handle_get_purchase_invoices,
        "get_purchase_invoice": _handle_get_purchase_invoice,
        "list_payments": _handle_get_payments,
        "create_payment": _handle_create_payment,
        "list_customers": _handle_get_customers,
        "get_customer": _handle_get_customer,
        "list_quotations": _handle_get_quotations,
        "create_quotation": _handle_create_quotation,
        "list_rfqs": _handle_get_rfqs,
        "get_ledger": _handle_get_account_ledger,
        "create_journal_entry": _handle_create_journal_entry,
    }
    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Valid: {valid}"}, default=str)
    return handler(**kwargs)
