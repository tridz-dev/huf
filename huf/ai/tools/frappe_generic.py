# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Generic, doctype-agnostic Frappe tools for an LLM agent.

Unlike huf/ai/tools/erpnext*.py (which wrap a fixed, curated set of business
doctypes), these handlers accept an arbitrary ``doctype`` argument supplied by
the model at call time. That is exactly the shape of tool an agent can be led
into misusing - by a crafted prompt, a confused multi-step plan, or plain
hallucination - to read or write doctypes it was never meant to touch (User,
Role, Custom Script, ...). Every handler in this module MUST therefore run
through ``_check_doctype_allowed`` and ``_check_permission`` before it reads
or writes anything, and MUST go through ``frappe.get_list``/``frappe.get_doc``
(which apply permission-query conditions) rather than raw SQL.

``handle_create_record`` and ``handle_update_record`` do not write to the
database at all - see their docstrings. The write happens client-side, as the
logged-in user, through the normal Frappe REST path; this module only ever
validates and returns a draft payload for a create/update.
"""

import json

import frappe
from frappe.model import default_fields

logger = frappe.logger("huf")


# ---------------------------------------------------------------------------
# Shared security helpers - every handler below goes through both of these.
# ---------------------------------------------------------------------------

#: Exact doctype names (case-insensitive) that are never accessible through
#: this generic surface, regardless of the caller's roles. These are either
#: security-sensitive (User, Role, *Script, Property Setter, File — which
#: guards arbitrary file records, not just literal uploads) or would let an
#: agent read/manufacture privilege (Role Profile).
_DENYLISTED_DOCTYPES = {
    "user",
    "role",
    "role profile",
    "custom script",
    "server script",
    "property setter",
    "file",
}

#: Doctype name PREFIXES (case-insensitive) that are denied wholesale, since
#: individual doctype names under these families change across versions/apps
#: (e.g. "OAuth Client", "OAuth Bearer Token", "Integration Request",
#: "Integration Service") and an allowlist-by-exact-name would miss new ones.
_DENYLISTED_PREFIXES = ("oauth", "integration")


def _error(msg: str) -> str:
    return json.dumps({"success": False, "error": msg}, default=str)


def _check_doctype_allowed(doctype: str):
    """Return ``(meta, None)`` if ``doctype`` may be accessed through this
    module, or ``(None, error_json_str)`` if it is denied.

    Deny-by-default on top of the explicit denylist: any doctype that does
    not exist, or whose meta cannot be loaded, is denied rather than silently
    passed through.
    """
    if not doctype or not isinstance(doctype, str):
        return None, _error("'doctype' is required")

    normalized = doctype.strip().lower()
    if normalized in _DENYLISTED_DOCTYPES:
        return None, _error(f"Access to doctype '{doctype}' is not permitted through this tool.")
    if normalized.startswith(_DENYLISTED_PREFIXES):
        return None, _error(f"Access to doctype '{doctype}' is not permitted through this tool.")

    try:
        if not frappe.db.exists("DocType", doctype):
            return None, _error(f"DocType '{doctype}' does not exist.")
        meta = frappe.get_meta(doctype)
    except Exception as e:
        return None, _error(f"Could not load DocType '{doctype}': {e}")

    # Single doctypes (e.g. System Settings, Global Defaults) hold one
    # site-wide configuration row apiece rather than a set of business
    # records - listing/creating/updating "records" for one makes no sense
    # in this tool's model and often exposes sensitive site config.
    if meta.issingle:
        return None, _error(f"'{doctype}' is a Single doctype and is not accessible through this tool.")

    return meta, None


def _check_permission(doctype: str, ptype: str, doc=None):
    """Return an error JSON string if the current user lacks ``ptype``
    permission on ``doctype`` (optionally scoped to a specific ``doc`` name),
    or ``None`` if the check passes.

    Always goes through ``frappe.has_permission`` - the single source of
    truth for role permissions, user permissions, and permission-query
    conditions - never a hand-rolled role check.
    """
    try:
        allowed = frappe.has_permission(doctype, ptype=ptype, doc=doc)
    except Exception as e:
        return _error(f"Permission check failed for {doctype}: {e}")

    if not allowed:
        target = f"{doctype} {doc}" if doc else doctype
        return _error(f"You do not have '{ptype}' permission on {target}.")
    return None


def _permitted_fieldnames(doctype: str, permission_type: str = "read") -> set:
    """Fieldnames the current user's roles may access at their permlevel,
    per ``frappe.permissions.get_permitted_fields`` - the same permlevel
    gate ``frappe.get_list``/``frappe.client.get_list`` apply internally.

    NOT 100% verified against every Frappe version's exact signature/return
    shape (flagged in the implementation report) - wrapped defensively so a
    signature mismatch fails closed (returns "no extra fields visible")
    rather than silently leaking permlevel-restricted fields.
    """
    try:
        fields = frappe.permissions.get_permitted_fields(doctype=doctype, permission_type=permission_type)
        return set(fields)
    except Exception:
        logger.warning(f"frappe_generic: get_permitted_fields failed for {doctype}, falling back to permlevel-0 fields only")
        try:
            meta = frappe.get_meta(doctype)
            return {df.fieldname for df in meta.fields if not getattr(df, "permlevel", 0)}
        except Exception:
            return set()


def _filter_permitted(doctype: str, row: dict, permission_type: str = "read") -> dict:
    """Strip keys from ``row`` that the current user's roles cannot read at
    their permlevel. Standard doc fields (name, owner, creation, ...) are
    always kept since they carry no permlevel and are not user-defined.
    """
    permitted = _permitted_fieldnames(doctype, permission_type) | set(default_fields)
    return {k: v for k, v in row.items() if k in permitted}


def _describe_field(df) -> dict:
    """Build the JSON-safe description of one DocField used by
    handle_get_doctype_meta, including type-specific detail (Select options,
    Link target doctype, one level of recursive Table child meta).
    """
    field = {
        "fieldname": df.fieldname,
        "label": df.label,
        "fieldtype": df.fieldtype,
        "options": df.options,
        "reqd": bool(df.reqd),
        "read_only": bool(df.read_only),
        "depends_on": df.depends_on,
        "fetch_from": df.fetch_from,
    }

    if df.fieldtype == "Select":
        field["select_options"] = [opt for opt in (df.options or "").split("\n") if opt != ""]
    elif df.fieldtype == "Link":
        field["link_doctype"] = df.options
    elif df.fieldtype == "Table" and df.options:
        try:
            child_meta = frappe.get_meta(df.options)
            field["child_doctype"] = df.options
            field["child_fields"] = [
                _describe_field(child_df)
                for child_df in child_meta.fields
                if child_df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML", "Button")
            ]
        except Exception as e:
            field["child_doctype"] = df.options
            field["child_fields_error"] = str(e)

    return field


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_get_doctype_meta(**kwargs) -> str:
    """Return the field schema for a doctype: fieldname, label, fieldtype,
    options, reqd, read_only, depends_on, fetch_from - with Select options
    expanded, Link target doctypes named, and Table child doctypes described
    one level deep.
    """
    doctype = (kwargs.get("doctype") or "").strip()
    meta, err = _check_doctype_allowed(doctype)
    if err:
        return err

    err = _check_permission(doctype, "read")
    if err:
        return err

    fields = [
        _describe_field(df)
        for df in meta.fields
        if df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML", "Button")
    ]

    return json.dumps({
        "success": True,
        "doctype": doctype,
        "is_submittable": bool(meta.is_submittable),
        "title_field": meta.get("title_field"),
        "fields": fields,
    }, default=str)


def handle_list_records(**kwargs) -> str:
    """Generic list of records for a doctype, via frappe.get_list (which
    applies permission-query conditions), with permlevel field filtering and
    pagination.
    """
    doctype = (kwargs.get("doctype") or "").strip()
    meta, err = _check_doctype_allowed(doctype)
    if err:
        return err

    err = _check_permission(doctype, "read")
    if err:
        return err

    filters = kwargs.get("filters")
    if isinstance(filters, str) and filters.strip():
        try:
            filters = json.loads(filters)
        except Exception:
            return _error("'filters' must be a JSON object/list or a dict")

    requested_fields = kwargs.get("fields")
    if isinstance(requested_fields, str) and requested_fields.strip():
        try:
            requested_fields = json.loads(requested_fields)
        except Exception:
            return _error("'fields' must be a JSON list of fieldnames")

    permitted = _permitted_fieldnames(doctype, "read")
    if requested_fields:
        fields = [f for f in requested_fields if f in permitted or f in default_fields or f == "name"]
    else:
        fields = ["name"] + sorted(permitted - {"name"})

    try:
        limit_start = int(kwargs.get("limit_start") or 0)
        limit_page_length = int(kwargs.get("limit_page_length") or 20)
    except (TypeError, ValueError):
        return _error("'limit_start' and 'limit_page_length' must be integers")

    order_by = kwargs.get("order_by")

    try:
        data = frappe.get_list(
            doctype,
            filters=filters,
            fields=fields,
            limit_start=limit_start,
            limit_page_length=limit_page_length,
            order_by=order_by,
        )
        total_count = frappe.db.count(doctype, filters=filters)
    except frappe.PermissionError:
        return _error(f"You do not have permission to list {doctype} records.")
    except Exception as e:
        logger.warning(f"handle_list_records failed for {doctype}: {e}")
        return _error(str(e))

    return json.dumps({
        "success": True,
        "data": data,
        "total_count": total_count,
        "limit_start": limit_start,
        "limit_page_length": limit_page_length,
    }, default=str)


def handle_get_record(**kwargs) -> str:
    """Fetch one record by name, after a permission check, with
    permlevel-restricted fields stripped from the result."""
    doctype = (kwargs.get("doctype") or "").strip()
    name = kwargs.get("name")

    meta, err = _check_doctype_allowed(doctype)
    if err:
        return err
    if not name:
        return _error("'name' is required")

    err = _check_permission(doctype, "read", doc=name)
    if err:
        return err

    try:
        doc = frappe.get_doc(doctype, name)
    except frappe.DoesNotExistError:
        return _error(f"No {doctype} found with name '{name}'.")
    except frappe.PermissionError:
        return _error(f"You do not have permission to read {doctype} {name}.")
    except Exception as e:
        return _error(str(e))

    data = _filter_permitted(doctype, doc.as_dict(), "read")
    return json.dumps({"success": True, "doctype": doctype, "name": name, "data": data}, default=str)


def _validate_draft_values(meta, values: dict, doctype: str, action: str):
    """Allowlist ``values`` against the doctype's own fields and, for
    create, check that meta-mandatory fields are present. Returns
    ``(cleaned_values, None)`` or ``(None, error_json_str)``.
    """
    if not isinstance(values, dict):
        return None, _error("'values' must be a JSON object of fieldname/value pairs")

    valid_fieldnames = {df.fieldname for df in meta.fields}
    cleaned = {k: v for k, v in values.items() if k in valid_fieldnames}

    if action == "create":
        missing = [
            df.fieldname for df in meta.fields
            if df.reqd and not df.depends_on and df.fieldname not in cleaned
        ]
        if missing:
            return None, _error(f"Missing required field(s) for {doctype}: {', '.join(missing)}")

    return cleaned, None


def handle_create_record(**kwargs) -> str:
    """Validate a proposed new record and return a DRAFT payload only.

    This handler NEVER writes to the database. It checks create permission,
    allowlists ``values`` against the doctype's real fields, and checks
    meta-mandatory fields are present - then hands back
    ``{"draft": True, "action": "create", ...}`` for the caller to submit.
    The actual insert happens client-side, as the logged-in user, through the
    normal Frappe REST API (POST /api/resource/<doctype>) - never
    server-side from an agent tool call, since that would let a model insert
    records as an implicit superuser/service identity rather than the human
    who is actually driving the conversation.
    """
    doctype = (kwargs.get("doctype") or "").strip()
    values = kwargs.get("values")
    if isinstance(values, str) and values.strip():
        try:
            values = json.loads(values)
        except Exception:
            return _error("'values' must be a JSON object or dict")

    meta, err = _check_doctype_allowed(doctype)
    if err:
        return err

    err = _check_permission(doctype, "create")
    if err:
        return err

    cleaned, err = _validate_draft_values(meta, values or {}, doctype, "create")
    if err:
        return err

    return json.dumps({
        "success": True,
        "draft": True,
        "doctype": doctype,
        "values": cleaned,
        "action": "create",
    }, default=str)


def handle_update_record(**kwargs) -> str:
    """Validate a proposed field update and return a DRAFT payload only.

    Same no-server-side-write contract as handle_create_record: this checks
    write permission on the specific document, allowlists ``values``, and
    returns ``{"draft": True, "action": "update", ...}`` - the write itself
    happens client-side via the normal Frappe REST path (PUT
    /api/resource/<doctype>/<name>) as the logged-in user.
    """
    doctype = (kwargs.get("doctype") or "").strip()
    name = kwargs.get("name")
    values = kwargs.get("values")
    if isinstance(values, str) and values.strip():
        try:
            values = json.loads(values)
        except Exception:
            return _error("'values' must be a JSON object or dict")

    meta, err = _check_doctype_allowed(doctype)
    if err:
        return err
    if not name:
        return _error("'name' is required")

    err = _check_permission(doctype, "write", doc=name)
    if err:
        return err

    if not frappe.db.exists(doctype, name):
        return _error(f"No {doctype} found with name '{name}'.")

    cleaned, err = _validate_draft_values(meta, values or {}, doctype, "update")
    if err:
        return err

    return json.dumps({
        "success": True,
        "draft": True,
        "doctype": doctype,
        "name": name,
        "values": cleaned,
        "action": "update",
    }, default=str)


# ---------------------------------------------------------------------------
# render_frappe_view - emits a frappe-list/frappe-form/frappe-report
# <artifact> block, matching the templating pattern in
# huf/ai/tools/render_tools.py (structured JSON in, <artifact> markup out).
# ---------------------------------------------------------------------------

_VALID_VIEW_MODES = ("list", "form", "report")


def _escape_artifact_attr(value: str) -> str:
    """Same rationale as render_tools._escape_artifact_attr: the frontend
    artifact parser extracts the outer tag with a plain regex, so a raw
    quote/angle-bracket in a templated title would truncate/corrupt the tag.
    """
    if not value:
        return value
    return value.replace('"', "'").replace("<", "(").replace(">", ")")


def handle_render_frappe_view(**kwargs) -> str:
    """Fetch data/meta for a doctype and emit it as a frappe-list, frappe-form,
    or frappe-report <artifact> block for the frontend to render, instead of
    returning raw JSON for the model to reformat itself.

    Args (via kwargs):
        doctype (str): Target doctype.
        mode (str): One of "list", "form", "report".
        filters: Same shape as handle_list_records (list mode only).
        fields: Same shape as handle_list_records/handle_get_doctype_meta.

    Returns:
        The complete ``<artifact type="frappe-list|frappe-form|frappe-report"
        language="json">...</artifact>`` string on success, or a plain
        ``{"success": False, "error": ...}`` JSON string on failure (this
        handler is called directly by the model, same as the other handlers
        in this module - it does not raise).
    """
    doctype = (kwargs.get("doctype") or "").strip()
    mode = (kwargs.get("mode") or "").strip().lower()

    if mode not in _VALID_VIEW_MODES:
        return _error(f"'mode' must be one of {_VALID_VIEW_MODES}, got {mode!r}")

    meta, err = _check_doctype_allowed(doctype)
    if err:
        return err

    err = _check_permission(doctype, "read")
    if err:
        return err

    meta_json = json.loads(handle_get_doctype_meta(doctype=doctype))
    if not meta_json.get("success"):
        return json.dumps(meta_json, default=str)

    payload = {
        "doctype": doctype,
        "mode": mode,
        "meta": meta_json,
    }

    if mode == "list":
        list_json = json.loads(handle_list_records(
            doctype=doctype,
            filters=kwargs.get("filters"),
            fields=kwargs.get("fields"),
            limit_start=kwargs.get("limit_start", 0),
            limit_page_length=kwargs.get("limit_page_length", 20),
            order_by=kwargs.get("order_by"),
        ))
        if not list_json.get("success"):
            return json.dumps(list_json, default=str)
        payload["filters"] = kwargs.get("filters")
        payload["fields"] = list(list_json["data"][0].keys()) if list_json["data"] else (kwargs.get("fields") or [])
        payload["data"] = list_json["data"]
        payload["total_count"] = list_json["total_count"]
        artifact_type = "frappe-list"

    elif mode == "form":
        name = kwargs.get("name") or (kwargs.get("filters") or {}).get("name")
        if not name:
            return _error("'name' (or filters.name) is required for mode='form'")
        record_json = json.loads(handle_get_record(doctype=doctype, name=name))
        if not record_json.get("success"):
            return json.dumps(record_json, default=str)
        payload["data"] = record_json["data"]
        artifact_type = "frappe-form"

    else:  # report
        list_json = json.loads(handle_list_records(
            doctype=doctype,
            filters=kwargs.get("filters"),
            fields=kwargs.get("fields"),
            limit_start=kwargs.get("limit_start", 0),
            limit_page_length=kwargs.get("limit_page_length", 100),
            order_by=kwargs.get("order_by"),
        ))
        if not list_json.get("success"):
            return json.dumps(list_json, default=str)
        payload["filters"] = kwargs.get("filters")
        payload["fields"] = kwargs.get("fields")
        payload["data"] = list_json["data"]
        payload["total_count"] = list_json["total_count"]
        artifact_type = "frappe-report"

    title = _escape_artifact_attr(f"{doctype} ({mode})")
    body = json.dumps(payload, default=str)
    return f'<artifact type="{artifact_type}" language="json" title="{title}">\n{body}\n</artifact>'
