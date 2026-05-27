"""
CRM integration tools for Frappe CRM (FCRM).
Uses direct Frappe DocType APIs – no external HTTP calls.
"""

import json
import frappe


def _crm_installed():
    try:
        return "crm" in frappe.get_installed_apps()
    except Exception:
        return False


def _error(msg):
    return json.dumps({"success": False, "error": msg})


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

def handle_get_leads(**kwargs) -> str:
    """List leads with optional filters (status, assigned_to, search query)."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        filters = {}
        status = kwargs.get("status")
        lead_owner = kwargs.get("assigned_to") or kwargs.get("lead_owner")
        search = kwargs.get("search")
        limit = int(kwargs.get("limit", 20))

        if status:
            filters["status"] = status
        if lead_owner:
            filters["lead_owner"] = lead_owner

        or_filters = []
        if search:
            or_filters = [
                ["CRM Lead", "lead_name", "like", f"%{search}%"],
                ["CRM Lead", "email", "like", f"%{search}%"],
                ["CRM Lead", "mobile_no", "like", f"%{search}%"],
                ["CRM Lead", "organization", "like", f"%{search}%"],
            ]

        fields = [
            "name",
            "lead_name",
            "first_name",
            "last_name",
            "email",
            "mobile_no",
            "status",
            "lead_owner",
            "organization",
            "source",
            "modified",
        ]

        leads = frappe.get_all(
            "CRM Lead",
            fields=fields,
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(leads), "results": leads})
    except Exception as e:
        frappe.log_error(f"CRM Get Leads Error: {e}", "CRM Tool")
        return _error(str(e))


def handle_get_lead(**kwargs) -> str:
    """Get a single lead by name/ID with all fields."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        name = kwargs.get("name") or kwargs.get("lead_id")
        if not name:
            return _error("name or lead_id is required")

        if not frappe.db.exists("CRM Lead", name):
            return _error(f"Lead {name} not found")

        doc = frappe.get_doc("CRM Lead", name)
        return json.dumps({"success": True, "results": doc.as_dict()})
    except Exception as e:
        frappe.log_error(f"CRM Get Lead Error: {e}", "CRM Tool")
        return _error(str(e))


def handle_create_lead(**kwargs) -> str:
    """Create a new lead."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        first_name = kwargs.get("first_name")
        if not first_name:
            return _error("first_name is required")

        last_name = kwargs.get("last_name", "")
        lead_name = kwargs.get("lead_name") or f"{first_name} {last_name}".strip()

        doc = frappe.new_doc("CRM Lead")
        doc.first_name = first_name
        doc.last_name = last_name
        doc.lead_name = lead_name
        doc.email = kwargs.get("email", "")
        doc.mobile_no = kwargs.get("mobile_no", "")
        doc.lead_owner = kwargs.get("lead_owner", "")
        doc.source = kwargs.get("source", "")
        doc.organization = kwargs.get("organization", "")
        doc.status = kwargs.get("status", "New")
        doc.insert(ignore_permissions=True)

        notes = kwargs.get("notes", "")
        if notes:
            note = frappe.new_doc("FCRM Note")
            note.title = kwargs.get("note_title", "Note")
            note.content = notes
            note.reference_doctype = "CRM Lead"
            note.reference_docname = doc.name
            note.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": doc.name, "lead_name": doc.lead_name}})
    except Exception as e:
        frappe.log_error(f"CRM Create Lead Error: {e}", "CRM Tool")
        return _error(str(e))


def handle_update_lead(**kwargs) -> str:
    """Update lead fields."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        name = kwargs.get("name") or kwargs.get("lead_id")
        if not name:
            return _error("name or lead_id is required")
        if not frappe.db.exists("CRM Lead", name):
            return _error(f"Lead {name} not found")

        doc = frappe.get_doc("CRM Lead", name)
        updatable = [
            "first_name",
            "last_name",
            "lead_name",
            "email",
            "mobile_no",
            "phone",
            "status",
            "lead_owner",
            "source",
            "organization",
            "website",
            "territory",
            "industry",
            "job_title",
            "annual_revenue",
            "no_of_employees",
            "gender",
            "salutation",
            "converted",
        ]
        for field in updatable:
            if field in kwargs:
                setattr(doc, field, kwargs[field])

        doc.save(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name, "lead_name": doc.lead_name}})
    except Exception as e:
        frappe.log_error(f"CRM Update Lead Error: {e}", "CRM Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------

def handle_get_deals(**kwargs) -> str:
    """List deals with optional filters."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        filters = {}
        status = kwargs.get("status")
        deal_owner = kwargs.get("deal_owner")
        organization = kwargs.get("organization")
        search = kwargs.get("search")
        limit = int(kwargs.get("limit", 20))

        if status:
            filters["status"] = status
        if deal_owner:
            filters["deal_owner"] = deal_owner
        if organization:
            filters["organization"] = organization

        or_filters = []
        if search:
            or_filters = [
                ["CRM Deal", "organization", "like", f"%{search}%"],
                ["CRM Deal", "lead_name", "like", f"%{search}%"],
                ["CRM Deal", "email", "like", f"%{search}%"],
            ]

        fields = [
            "name",
            "organization",
            "status",
            "deal_owner",
            "deal_value",
            "expected_deal_value",
            "probability",
            "expected_closure_date",
            "closed_date",
            "modified",
        ]

        deals = frappe.get_all(
            "CRM Deal",
            fields=fields,
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(deals), "results": deals})
    except Exception as e:
        frappe.log_error(f"CRM Get Deals Error: {e}", "CRM Tool")
        return _error(str(e))


def handle_create_deal(**kwargs) -> str:
    """Create a deal from a lead or standalone."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        doc = frappe.new_doc("CRM Deal")

        lead = kwargs.get("lead")
        if lead:
            if not frappe.db.exists("CRM Lead", lead):
                return _error(f"Lead {lead} not found")
            doc.lead = lead
            lead_doc = frappe.get_doc("CRM Lead", lead)
            doc.lead_name = lead_doc.lead_name
            doc.organization_name = lead_doc.organization
            # Try to link existing CRM Organization; leave blank if not found
            if lead_doc.organization and frappe.db.exists("CRM Organization", lead_doc.organization):
                doc.organization = lead_doc.organization
            doc.email = lead_doc.email
            doc.mobile_no = lead_doc.mobile_no
            doc.phone = lead_doc.phone
            doc.first_name = lead_doc.first_name
            doc.last_name = lead_doc.last_name
            doc.salutation = lead_doc.salutation
            doc.gender = lead_doc.gender
            doc.source = lead_doc.source
            doc.territory = lead_doc.territory
            doc.industry = lead_doc.industry
            doc.annual_revenue = lead_doc.annual_revenue
            doc.no_of_employees = lead_doc.no_of_employees
            doc.job_title = lead_doc.job_title
            doc.website = lead_doc.website

        # Override with explicit kwargs if provided
        if "organization_name" in kwargs:
            doc.organization_name = kwargs["organization_name"]
        if "organization" in kwargs:
            org = kwargs["organization"]
            if org and frappe.db.exists("CRM Organization", org):
                doc.organization = org
            elif org and not doc.organization_name:
                doc.organization_name = org

        doc.status = kwargs.get("status", "Qualification")
        doc.deal_owner = kwargs.get("deal_owner", "")
        doc.deal_value = kwargs.get("deal_value", 0)
        doc.expected_deal_value = kwargs.get("expected_deal_value", 0)
        doc.probability = kwargs.get("probability", 0)
        doc.expected_closure_date = kwargs.get("expected_closure_date", "")
        doc.closed_date = kwargs.get("closed_date", "")
        doc.email = kwargs.get("email", doc.email or "")
        doc.mobile_no = kwargs.get("mobile_no", doc.mobile_no or "")
        doc.first_name = kwargs.get("first_name", doc.first_name or "")
        doc.last_name = kwargs.get("last_name", doc.last_name or "")

        doc.insert(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name, "organization": doc.organization_name or doc.organization}})
    except Exception as e:
        frappe.log_error(f"CRM Create Deal Error: {e}", "CRM Tool")
        return _error(str(e))


def handle_update_deal(**kwargs) -> str:
    """Update deal fields."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        name = kwargs.get("name") or kwargs.get("deal_id")
        if not name:
            return _error("name or deal_id is required")
        if not frappe.db.exists("CRM Deal", name):
            return _error(f"Deal {name} not found")

        doc = frappe.get_doc("CRM Deal", name)
        updatable = [
            "organization",
            "status",
            "deal_owner",
            "deal_value",
            "expected_deal_value",
            "probability",
            "expected_closure_date",
            "closed_date",
            "next_step",
            "email",
            "mobile_no",
            "phone",
            "website",
            "territory",
            "industry",
            "annual_revenue",
            "lost_reason",
            "lost_notes",
        ]
        for field in updatable:
            if field in kwargs:
                setattr(doc, field, kwargs[field])

        doc.save(ignore_permissions=True)
        return json.dumps({"success": True, "results": {"name": doc.name, "organization": doc.organization}})
    except Exception as e:
        frappe.log_error(f"CRM Update Deal Error: {e}", "CRM Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Notes & Tasks
# ---------------------------------------------------------------------------

def handle_add_note(**kwargs) -> str:
    """Add a note to a lead or deal."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        doctype = kwargs.get("doctype")
        docname = kwargs.get("docname")
        content = kwargs.get("content")
        if not all([doctype, docname, content]):
            return _error("doctype, docname, and content are required")

        if not frappe.db.exists(doctype, docname):
            return _error(f"Document {doctype} {docname} not found")

        note = frappe.new_doc("FCRM Note")
        note.title = kwargs.get("title", "Note")
        note.content = content
        note.reference_doctype = doctype
        note.reference_docname = docname
        note.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": note.name, "title": note.title}})
    except Exception as e:
        frappe.log_error(f"CRM Add Note Error: {e}", "CRM Tool")
        return _error(str(e))


def handle_add_task(**kwargs) -> str:
    """Create a task linked to a lead or deal."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        title = kwargs.get("title")
        reference_doctype = kwargs.get("reference_doctype")
        reference_docname = kwargs.get("reference_docname")
        if not all([title, reference_doctype, reference_docname]):
            return _error("title, reference_doctype, and reference_docname are required")

        if not frappe.db.exists(reference_doctype, reference_docname):
            return _error(f"Document {reference_doctype} {reference_docname} not found")

        task = frappe.new_doc("CRM Task")
        task.title = title
        task.reference_doctype = reference_doctype
        task.reference_docname = reference_docname
        task.assigned_to = kwargs.get("assigned_to", "")
        task.status = kwargs.get("status", "Todo")
        task.priority = kwargs.get("priority", "Medium")
        task.due_date = kwargs.get("due_date", "")
        task.description = kwargs.get("description", "")
        task.start_date = kwargs.get("start_date", "")
        task.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": task.name, "title": task.title}})
    except Exception as e:
        frappe.log_error(f"CRM Add Task Error: {e}", "CRM Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def handle_get_contacts(**kwargs) -> str:
    """List/search contacts. Optionally filter by deal to return CRM Contacts child rows."""
    if not _crm_installed():
        return _error("Frappe CRM app is not installed.")

    try:
        search = kwargs.get("search")
        deal = kwargs.get("deal")
        limit = int(kwargs.get("limit", 20))
        offset = int(kwargs.get("offset", 0))

        if deal:
            if not frappe.db.exists("CRM Deal", deal):
                return _error(f"Deal {deal} not found")

            filters = {"parenttype": "CRM Deal", "parent": deal}
            or_filters = []
            if search:
                or_filters = [
                    ["CRM Contacts", "full_name", "like", f"%{search}%"],
                    ["CRM Contacts", "email", "like", f"%{search}%"],
                    ["CRM Contacts", "mobile_no", "like", f"%{search}%"],
                ]

            fields = [
                "name",
                "contact",
                "full_name",
                "email",
                "mobile_no",
                "phone",
                "gender",
                "is_primary",
                "modified",
            ]

            contacts = frappe.get_all(
                "CRM Contacts",
                fields=fields,
                filters=filters,
                or_filters=or_filters or None,
                limit=limit,
                limit_start=offset,
                order_by="modified desc",
            )
        else:
            filters = {}
            or_filters = []
            if search:
                or_filters = [
                    ["Contact", "first_name", "like", f"%{search}%"],
                    ["Contact", "last_name", "like", f"%{search}%"],
                    ["Contact", "email_id", "like", f"%{search}%"],
                    ["Contact", "mobile_no", "like", f"%{search}%"],
                ]

            fields = [
                "name",
                "first_name",
                "last_name",
                "email_id",
                "mobile_no",
                "phone",
                "company_name",
                "modified",
            ]

            contacts = frappe.get_all(
                "Contact",
                fields=fields,
                filters=filters,
                or_filters=or_filters or None,
                limit=limit,
                limit_start=offset,
                order_by="modified desc",
            )

        return json.dumps({"success": True, "count": len(contacts), "results": contacts})
    except frappe.DoesNotExistError:
        return _error("Contact DocType does not exist on this site.")
    except Exception as e:
        frappe.log_error(f"CRM Get Contacts Error: {e}", "CRM Tool")
        return _error(str(e))
