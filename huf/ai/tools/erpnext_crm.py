"""
ERPNext CRM integration tools (Lead, Opportunity).
Different from standalone Frappe CRM (CRM Lead / CRM Deal).
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


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------

def _handle_get_leads(**kwargs) -> str:
    """List ERPNext leads with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        status = kwargs.get("status")
        lead_owner = kwargs.get("lead_owner")
        search = kwargs.get("search")
        limit = int(kwargs.get("limit", 20))

        if status:
            filters.append(["Lead", "status", "=", status])
        if lead_owner:
            filters.append(["Lead", "lead_owner", "=", lead_owner])

        or_filters = []
        if search:
            or_filters = [
                ["Lead", "lead_name", "like", f"%{search}%"],
                ["Lead", "company_name", "like", f"%{search}%"],
                ["Lead", "email_id", "like", f"%{search}%"],
            ]

        fields = [
            "name",
            "lead_name",
            "company_name",
            "email_id",
            "status",
            "lead_owner",
            "mobile_no",
            "territory",
            "modified",
        ]

        leads = frappe.get_all(
            "Lead",
            fields=fields,
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(leads), "results": leads}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Get Leads Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


def _handle_get_lead(**kwargs) -> str:
    """Get a single ERPNext Lead by name/ID with all fields."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Lead", name):
            return _error(f"Lead {name} not found")

        doc = frappe.get_doc("Lead", name)
        return json.dumps({"success": True, "results": doc.as_dict()}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Get Lead Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


def _handle_create_lead(**kwargs) -> str:
    """Create a new ERPNext Lead."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        lead_name = kwargs.get("lead_name")
        if not lead_name:
            return _error("lead_name is required")

        doc = frappe.new_doc("Lead")
        doc.lead_name = lead_name
        doc.company_name = kwargs.get("company_name", "")
        doc.email_id = kwargs.get("email_id", "")
        doc.mobile_no = kwargs.get("mobile_no", "")
        doc.phone = kwargs.get("phone", "")
        doc.lead_owner = kwargs.get("lead_owner", "")
        doc.status = kwargs.get("status", "Lead")
        doc.type = kwargs.get("type", "")
        doc.market_segment = kwargs.get("market_segment", "")
        doc.industry = kwargs.get("industry", "")
        doc.territory = kwargs.get("territory", "")
        doc.website = kwargs.get("website", "")
        doc.insert(ignore_permissions=True)

        return json.dumps(
            {"success": True, "results": {"name": doc.name, "lead_name": doc.lead_name}}
        )
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Create Lead Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


def _handle_update_lead(**kwargs) -> str:
    """Update fields on an existing ERPNext Lead."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Lead", name):
            return _error(f"Lead {name} not found")

        doc = frappe.get_doc("Lead", name)
        updatable = [
            "status",
            "lead_owner",
            "email_id",
            "mobile_no",
            "territory",
            "qualification_status",
            "company_name",
            "phone",
            "website",
            "industry",
            "market_segment",
            "type",
        ]
        for field in updatable:
            if field in kwargs:
                setattr(doc, field, kwargs[field])

        doc.save(ignore_permissions=True)
        return json.dumps(
            {"success": True, "results": {"name": doc.name, "lead_name": doc.lead_name}}
        )
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Update Lead Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Opportunity
# ---------------------------------------------------------------------------

def _handle_get_opportunities(**kwargs) -> str:
    """List ERPNext Opportunities with optional filters."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        filters = []
        status = kwargs.get("status")
        party_name = kwargs.get("party_name")
        from_date = kwargs.get("from_date")
        limit = int(kwargs.get("limit", 20))

        if status:
            filters.append(["Opportunity", "status", "=", status])
        if party_name:
            filters.append(["Opportunity", "party_name", "=", party_name])
        if from_date:
            filters.append(["Opportunity", "expected_closing", ">=", from_date])

        fields = [
            "name",
            "title",
            "party_name",
            "customer_name",
            "status",
            "opportunity_amount",
            "sales_stage",
            "probability",
            "expected_closing",
        ]

        opportunities = frappe.get_all(
            "Opportunity",
            fields=fields,
            filters=filters,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps(
            {"success": True, "count": len(opportunities), "results": opportunities}
        )
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Get Opportunities Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


def _handle_create_opportunity(**kwargs) -> str:
    """Create a new ERPNext Opportunity."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        opportunity_from = kwargs.get("opportunity_from")
        party_name = kwargs.get("party_name")
        if not opportunity_from:
            return _error("opportunity_from is required")
        if not party_name:
            return _error("party_name is required")

        doc = frappe.new_doc("Opportunity")
        doc.opportunity_from = opportunity_from
        doc.party_name = party_name
        doc.title = kwargs.get("title", "")
        doc.opportunity_type = kwargs.get("opportunity_type", "")
        doc.expected_closing = kwargs.get("expected_closing", "")
        doc.opportunity_amount = float(kwargs.get("opportunity_amount", 0))
        doc.sales_stage = kwargs.get("sales_stage", "")
        doc.probability = float(kwargs.get("probability", 0))
        doc.currency = kwargs.get("currency", "")
        doc.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": doc.name}}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Create Opportunity Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


def _handle_update_opportunity(**kwargs) -> str:
    """Update fields on an existing ERPNext Opportunity."""
    if not _erpnext_installed():
        return _error("ERPNext is not installed.")

    try:
        name = kwargs.get("name")
        if not name:
            return _error("name is required")
        if not frappe.db.exists("Opportunity", name):
            return _error(f"Opportunity {name} not found")

        doc = frappe.get_doc("Opportunity", name)
        updatable = [
            "status",
            "opportunity_amount",
            "sales_stage",
            "probability",
            "expected_closing",
            "order_lost_reason",
        ]
        for field in updatable:
            if field in kwargs:
                if field in ("opportunity_amount", "probability"):
                    setattr(doc, field, float(kwargs[field]))
                else:
                    setattr(doc, field, kwargs[field])

        doc.save(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name}}, default=str)
    except Exception as e:
        frappe.log_error(f"ERPNext CRM Update Opportunity Error: {e}", "ERPNext CRM Tool")
        return _error(str(e))


def handle_action(**kwargs) -> str:
    action = kwargs.get("action", "").strip().lower()
    dispatch = {
        "list_leads": _handle_get_leads,
        "get_lead": _handle_get_lead,
        "create_lead": _handle_create_lead,
        "update_lead": _handle_update_lead,
        "list_opportunities": _handle_get_opportunities,
        "create_opportunity": _handle_create_opportunity,
        "update_opportunity": _handle_update_opportunity,
    }
    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Valid: {valid}"}, default=str)
    return handler(**kwargs)
