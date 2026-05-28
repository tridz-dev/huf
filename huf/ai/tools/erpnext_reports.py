"""
ERPNext integration tools for built-in script reports.
Uses frappe.desk.query_report.run – read-only analytical tools.
"""

import json
import frappe


def _erpnext_installed():
    try:
        return "erpnext" in frappe.get_installed_apps()
    except Exception:
        return False


def _error(msg):
    return json.dumps({"success": False, "error": msg})


def _run_report(report_name, filters):
    """Helper to run an ERPNext query report and return a serializable result."""
    from frappe.desk.query_report import run as run_report

    # Remove empty string values to avoid report errors
    cleaned = {k: v for k, v in filters.items() if v != ""}

    result = run_report(
        report_name=report_name,
        filters=cleaned,
        ignore_prepared_report=True,
    )

    # Serialize columns and rows safely
    columns = []
    for col in result.get("columns", []):
        if isinstance(col, dict):
            columns.append({
                "label": col.get("label", ""),
                "fieldname": col.get("fieldname", ""),
                "fieldtype": col.get("fieldtype", ""),
                "width": col.get("width", 0),
            })
        elif isinstance(col, str):
            columns.append({"label": col, "fieldname": col, "fieldtype": "Data"})
        else:
            columns.append({"label": str(col), "fieldname": str(col), "fieldtype": "Data"})

    rows = result.get("result", [])
    serializable_rows = []
    for row in rows:
        if isinstance(row, dict):
            serializable_rows.append({k: (v if v is not None else "") for k, v in row.items()})
        elif hasattr(row, "__dict__"):
            serializable_rows.append({k: (v if v is not None else "") for k, v in row.__dict__.items()})
        else:
            serializable_rows.append({"value": str(row)})

    return {"success": True, "results": serializable_rows, "columns": columns}


# ---------------------------------------------------------------------------
# Financial Statements
# ---------------------------------------------------------------------------

def handle_balance_sheet(**kwargs) -> str:
    """Run ERPNext Balance Sheet report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        if not company:
            return _error("company is required")

        filters = {
            "company": company,
            "fiscal_year": kwargs.get("fiscal_year", ""),
            "from_fiscal_year": kwargs.get("from_fiscal_year", ""),
            "to_fiscal_year": kwargs.get("to_fiscal_year", ""),
            "periodicity": kwargs.get("periodicity", ""),
            "accumulated_values": int(kwargs.get("accumulated_values", 1)),
        }

        return json.dumps(_run_report("Balance Sheet", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Balance Sheet Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_profit_and_loss(**kwargs) -> str:
    """Run ERPNext Profit and Loss Statement report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        if not company:
            return _error("company is required")

        filters = {
            "company": company,
            "fiscal_year": kwargs.get("fiscal_year", ""),
            "periodicity": kwargs.get("periodicity", ""),
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
        }

        return json.dumps(_run_report("Profit and Loss Statement", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Profit and Loss Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_trial_balance(**kwargs) -> str:
    """Run ERPNext Trial Balance report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        if not company:
            return _error("company is required")

        filters = {
            "company": company,
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "show_zero_values": int(kwargs.get("show_zero_values", 0)),
        }

        return json.dumps(_run_report("Trial Balance", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Trial Balance Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Accounts Reports
# ---------------------------------------------------------------------------

def handle_general_ledger(**kwargs) -> str:
    """Run ERPNext General Ledger report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        if not company:
            return _error("company is required")

        filters = {
            "company": company,
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "account": kwargs.get("account", ""),
            "party_type": kwargs.get("party_type", ""),
            "party": kwargs.get("party", ""),
            "voucher_no": kwargs.get("voucher_no", ""),
            "group_by": kwargs.get("group_by", ""),
        }

        result = _run_report("General Ledger", filters)
        rows = result.get("results", [])
        if len(rows) > int(kwargs.get("limit", 500)):
            rows = rows[: int(kwargs.get("limit", 500))]
            result["results"] = rows
            result["truncated"] = True

        return json.dumps(result)
    except Exception as e:
        frappe.log_error(f"ERPNext General Ledger Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_accounts_receivable(**kwargs) -> str:
    """Run ERPNext Accounts Receivable report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        if not company:
            return _error("company is required")

        filters = {
            "company": company,
            "report_date": kwargs.get("report_date", ""),
            "ageing_based_on": kwargs.get("ageing_based_on", "Due Date"),
            "range1": int(kwargs.get("range1", 30)),
            "range2": int(kwargs.get("range2", 60)),
            "range3": int(kwargs.get("range3", 90)),
            "customer": kwargs.get("customer", ""),
            "payment_terms_template": kwargs.get("payment_terms_template", ""),
        }

        return json.dumps(_run_report("Accounts Receivable", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Accounts Receivable Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_accounts_payable(**kwargs) -> str:
    """Run ERPNext Accounts Payable report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        if not company:
            return _error("company is required")

        filters = {
            "company": company,
            "report_date": kwargs.get("report_date", ""),
            "ageing_based_on": kwargs.get("ageing_based_on", "Due Date"),
            "range1": int(kwargs.get("range1", 30)),
            "range2": int(kwargs.get("range2", 60)),
            "range3": int(kwargs.get("range3", 90)),
            "supplier": kwargs.get("supplier", ""),
        }

        return json.dumps(_run_report("Accounts Payable", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Accounts Payable Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_bank_reconciliation(**kwargs) -> str:
    """Run ERPNext Bank Reconciliation Statement report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        company = kwargs.get("company")
        account = kwargs.get("account")
        if not company:
            return _error("company is required")
        if not account:
            return _error("account is required")

        filters = {
            "company": company,
            "account": account,
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "include_pos_transactions": int(kwargs.get("include_pos_transactions", 0)),
        }

        return json.dumps(_run_report("Bank Reconciliation Statement", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Bank Reconciliation Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Sales Reports
# ---------------------------------------------------------------------------

def handle_sales_register(**kwargs) -> str:
    """Run ERPNext Sales Register report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        if not from_date:
            return _error("from_date is required")
        if not to_date:
            return _error("to_date is required")

        filters = {
            "company": kwargs.get("company", ""),
            "from_date": from_date,
            "to_date": to_date,
            "customer": kwargs.get("customer", ""),
            "item_code": kwargs.get("item_code", ""),
        }

        return json.dumps(_run_report("Sales Register", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Sales Register Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_sales_order_analysis(**kwargs) -> str:
    """Run ERPNext Sales Order Analysis report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = {
            "company": kwargs.get("company", ""),
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "customer": kwargs.get("customer", ""),
            "item_code": kwargs.get("item_code", ""),
            "status": kwargs.get("status", ""),
        }

        return json.dumps(_run_report("Sales Order Analysis", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Sales Order Analysis Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_customer_acquisition(**kwargs) -> str:
    """Run ERPNext Customer Acquisition and Loyalty report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = {
            "company": kwargs.get("company", ""),
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "customer_group": kwargs.get("customer_group", ""),
            "territory": kwargs.get("territory", ""),
        }

        return json.dumps(_run_report("Customer Acquisition and Loyalty", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Customer Acquisition Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Stock / Inventory Reports
# ---------------------------------------------------------------------------

def handle_stock_balance_report(**kwargs) -> str:
    """Run ERPNext Stock Balance report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = {
            "company": kwargs.get("company", ""),
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "item_code": kwargs.get("item_code", ""),
            "warehouse": kwargs.get("warehouse", ""),
            "item_group": kwargs.get("item_group", ""),
        }

        return json.dumps(_run_report("Stock Balance", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Stock Balance Report Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_stock_ledger_report(**kwargs) -> str:
    """Run ERPNext Stock Ledger report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        if not from_date:
            return _error("from_date is required")
        if not to_date:
            return _error("to_date is required")

        filters = {
            "company": kwargs.get("company", ""),
            "from_date": from_date,
            "to_date": to_date,
            "item_code": kwargs.get("item_code", ""),
            "warehouse": kwargs.get("warehouse", ""),
            "voucher_no": kwargs.get("voucher_no", ""),
        }

        return json.dumps(_run_report("Stock Ledger", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Stock Ledger Report Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_item_wise_sales(**kwargs) -> str:
    """Run ERPNext Item-wise Sales Register report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = {
            "company": kwargs.get("company", ""),
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "item_code": kwargs.get("item_code", ""),
            "customer": kwargs.get("customer", ""),
        }

        return json.dumps(_run_report("Item-wise Sales Register", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Item-wise Sales Error: {e}", "ERPNext Report Tool")
        return _error(str(e))


def handle_gross_profit(**kwargs) -> str:
    """Run ERPNext Gross Profit report."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = {
            "company": kwargs.get("company", ""),
            "from_date": kwargs.get("from_date", ""),
            "to_date": kwargs.get("to_date", ""),
            "group_by": kwargs.get("group_by", ""),
        }

        return json.dumps(_run_report("Gross Profit", filters))
    except Exception as e:
        frappe.log_error(f"ERPNext Gross Profit Error: {e}", "ERPNext Report Tool")
        return _error(str(e))
