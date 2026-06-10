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
    return json.dumps({"success": False, "error": msg}, default=str)


# Catalogue of available reports per module (used by list_reports)
REPORT_CATALOGUE = {
    "Accounts": [
        "Balance Sheet", "Profit and Loss Statement", "Trial Balance",
        "Cash Flow", "General Ledger", "Accounts Receivable",
        "Accounts Receivable Summary", "Accounts Payable", "Accounts Payable Summary",
        "Customer Ledger Summary", "Supplier Ledger Summary",
        "Sales Register", "Purchase Register",
        "Item-wise Sales Register", "Item-wise Purchase Register",
        "Gross Profit", "Gross and Net Profit Report", "Profitability Analysis",
        "Bank Reconciliation Statement", "Bank Clearance Summary",
        "Payment Ledger", "Budget Variance Report",
        "Trial Balance for Party", "Voucher-wise Balance",
    ],
    "Selling": [
        "Sales Analytics", "Sales Order Analysis", "Sales Order Trends",
        "Quotation Trends", "Lost Quotations", "Inactive Customers",
        "Customer Acquisition and Loyalty", "Customer Credit Balance",
        "Sales Person Commission Summary", "Territory-wise Sales",
        "Sales Payment Summary",
    ],
    "Buying": [
        "Purchase Analytics", "Purchase Order Analysis", "Purchase Order Trends",
        "Supplier Quotation Comparison", "Procurement Tracker",
        "Requested Items to Order and Receive",
    ],
    "Stock": [
        "Stock Balance", "Stock Ledger", "Stock Projected Qty",
        "Stock Ageing", "Item Shortage Report", "Total Stock Summary",
        "Warehouse Wise Stock Balance", "Stock Analytics",
        "Available Batch Report", "Batch-Wise Balance History",
        "BOM Stock Report", "Item Price Stock",
    ],
    "Manufacturing": [
        "BOM Explorer", "BOM Stock Report", "BOM Variance Report",
        "Work Order Summary", "Production Analytics",
        "Job Card Summary", "Production Planning Report",
    ],
    "CRM": [
        "Sales Pipeline Analytics", "Lead Details", "Lead Owner Efficiency",
        "Lost Opportunity", "Opportunity Summary by Sales Stage",
        "First Response Time for Opportunity", "Campaign Efficiency",
    ],
    "Helpdesk": [
        "Ticket Analytics", "Ticket Summary", "First Response Time for Tickets",
        "Support Hour Distribution",
    ],
    "Projects": [
        "Project Summary", "Timesheet Billing Summary", "Daily Timesheet Summary",
    ],
    "HR": [
        "Salary Register", "Monthly Attendance Sheet",
        "Employee Leave Balance", "Employee Analytics",
    ],
}


def handle_run_report(**kwargs) -> str:
    """Run any ERPNext/Frappe script report by name with filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")
    report_name = kwargs.get("report_name")
    try:
        if not report_name:
            return _error("report_name is required. Call erpnext_list_reports to see available reports.")

        # Parse filters - accept dict or JSON string
        filters = kwargs.get("filters", {})
        if isinstance(filters, str):
            try:
                filters = json.loads(filters)
            except Exception:
                return _error("filters must be a JSON object or dict")

        # Fill company default if not provided
        if not filters.get("company"):
            default_company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
            if default_company:
                filters["company"] = default_company

        # Auto-resolve dates from fiscal year if missing
        if not filters.get("from_date") and not filters.get("to_date"):
            fiscal_year = filters.get("fiscal_year")
            if not fiscal_year:
                fiscal_year = frappe.defaults.get_user_default("Fiscal Year") or frappe.db.get_single_value("Global Defaults", "current_fiscal_year")
            
            if fiscal_year:
                try:
                    fy_doc = None
                    if frappe.db.exists("Fiscal Year", fiscal_year):
                        fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
                    else:
                        fy_list = frappe.get_all("Fiscal Year", filters={"name": ("like", f"%{fiscal_year}%")}, limit=1)
                        if fy_list:
                            fy_doc = frappe.get_doc("Fiscal Year", fy_list[0].name)
                    
                    if fy_doc:
                        filters["from_date"] = fy_doc.year_start_date
                        filters["to_date"] = fy_doc.year_end_date
                        filters["period_start_date"] = fy_doc.year_start_date
                        filters["period_end_date"] = fy_doc.year_end_date
                        filters["fiscal_year"] = fy_doc.name
                except Exception:
                    pass

        # Set default periodicity for financial statements if missing
        if not filters.get("periodicity"):
            filters["periodicity"] = "Yearly"

        from frappe.desk.query_report import run as run_report
        result = run_report(report_name=report_name, filters=filters, ignore_prepared_report=True)
        return json.dumps({
            "success": True,
            "report_name": report_name,
            "columns": result.get("columns", []),
            "results": result.get("result", []),
            "count": len(result.get("result", [])),
        }, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext Report Error [{report_name}]: {e}", "ERPNext Reports Tool")
        return _error(str(e))


def handle_list_reports(**kwargs) -> str:
    """List available reports, optionally filtered by module or search keyword."""
    module = kwargs.get("module", "").strip()
    search = kwargs.get("search", "").strip().lower()
    
    if module:
        # case-insensitive match
        matched = {k: v for k, v in REPORT_CATALOGUE.items() if k.lower() == module.lower()}
        if search:
            for k in matched:
                matched[k] = [r for r in matched[k] if search in r.lower()]
                
        if not matched:
            available = list(REPORT_CATALOGUE.keys())
            return json.dumps({"success": False, "error": f"Module '{module}' not found. Available: {available}"}, default=str)
        return json.dumps({"success": True, "results": matched}, default=str)
        
    if search:
        matched = {}
        for mod, reports in REPORT_CATALOGUE.items():
            filtered = [r for r in reports if search in r.lower()]
            if filtered:
                matched[mod] = filtered
        return json.dumps({"success": True, "results": matched}, default=str)

    return json.dumps({"success": True, "results": REPORT_CATALOGUE}, default=str)
