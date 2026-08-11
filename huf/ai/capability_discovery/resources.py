"""App-scoped resource (DocType) discovery for HUF app capability discovery.

Builds ranked resource lists and per-resource capability detail (generated
actions/events, related resources) for a single provider app, using
Module Def -> app_name ownership (huf.ai.capabilities.apps.app_owns_doctype)
as the source of truth for "which DocTypes belong to this app".
"""

import frappe

from huf.ai.capabilities import ranking
from huf.ai.capabilities.apps import app_owns_doctype
from huf.ai.capabilities.events import generate_events_for_resource
from huf.ai.capabilities.models import make_capability_descriptor

RESOURCE_SCOPES = ("recommended", "discovered", "all")
RECOMMENDED_CAP = 20
RELATED_RESOURCES_CAP = 5


def get_app_resources(app_name, scope="recommended") -> list:
    """Return ranked resource dicts for the DocTypes owned by app_name.

    scope="recommended" returns only top-ranked, eligible resources (visibility
    "recommended", capped at RECOMMENDED_CAP). scope="discovered" adds "normal"
    visibility resources. scope="all" returns every app-owned DocType
    (including child tables/singles) regardless of eligibility or score.
    Always sorted by score descending.
    """
    if scope not in RESOURCE_SCOPES:
        raise ValueError(f"scope must be one of {RESOURCE_SCOPES}, got {scope!r}")

    exposed_tables = _get_exposed_tables(app_name)
    candidates = [
        _build_resource(doctype, exposed_tables)
        for doctype in _get_app_doctypes(app_name)
    ]
    candidates.sort(key=lambda r: r["score"], reverse=True)

    if scope == "all":
        for r in candidates:
            r.pop("_eligible", None)
        return candidates

    eligible = [r for r in candidates if r["_eligible"]]
    if scope == "recommended":
        results = [r for r in eligible if r["visibility"] == "recommended"][:RECOMMENDED_CAP]
    else:  # discovered
        results = [r for r in eligible if r["visibility"] in ("recommended", "normal")]

    for r in results:
        r.pop("_eligible", None)
    return results


def describe_resource(app_name, doctype) -> dict:
    """Build CapabilityResourceDetail-shaped detail for one app-owned DocType.

    Raises frappe.PermissionError if doctype is not owned by app_name (a
    manifest or caller cannot cross app ownership boundaries, per plan §6.2).
    """
    if not app_owns_doctype(app_name, doctype):
        raise frappe.PermissionError(f"DocType '{doctype}' is not owned by app '{app_name}'")

    meta = frappe.get_meta(doctype)
    return {
        "doctype": doctype,
        "title": meta.name,
        "generated_actions": _build_generated_actions(app_name, doctype, meta),
        "generated_events": generate_events_for_resource(app_name, doctype, submittable=bool(meta.is_submittable)),
        "related_resources": _get_related_resources(app_name, meta),
    }


def _build_resource(doctype, exposed_tables) -> dict:
    meta = frappe.get_meta(doctype)
    is_exposed = doctype in exposed_tables
    eligible = ranking.is_eligible_business_object(meta)
    submittable = bool(meta.is_submittable)
    link_count = _count_incoming_links(doctype)
    score = ranking.score_resource(
        meta, is_exposed=is_exposed, submittable=submittable, link_count=link_count
    )
    visibility = ranking.visibility_for_score(score, is_exposed=is_exposed)
    return {
        "doctype": doctype,
        "title": meta.name,
        "score": score,
        "visibility": visibility,
        "is_exposed": is_exposed,
        "submittable": submittable,
        "_eligible": eligible,
    }


def _get_app_doctypes(app_name: str) -> list:
    """All DocTypes owned by app_name via Module Def -> app_name."""
    modules = frappe.get_all("Module Def", filters={"app_name": app_name}, pluck="name")
    if not modules:
        return []
    return frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name")


def _get_exposed_tables(app_name: str) -> set:
    raw = frappe.db.get_value("HUF App", {"source_app": app_name}, "exposed_tables")
    if not raw:
        return set()
    return {t.strip() for t in raw.split(",") if t.strip()}


def _count_incoming_links(doctype: str) -> int:
    """Number of distinct other DocTypes with a Link field pointing at doctype."""
    rows = frappe.get_all(
        "DocField",
        filters={"fieldtype": "Link", "options": doctype},
        pluck="parent",
        distinct=True,
    )
    return len(rows)


def _build_generated_actions(app_name, doctype, meta) -> list:
    specs = [
        ("read", "Read", "read"),
        ("search", "Search", "read"),
        ("create", "Create", "write"),
        ("update", "Update", "write"),
    ]
    if meta.is_submittable:
        specs.append(("submit", "Submit", "write"))
        specs.append(("cancel", "Cancel", "destructive"))

    return [
        make_capability_descriptor(
            kind="action",
            source_app=app_name,
            source_type="generated",
            source_key=f"{doctype}.{action_key}",
            title=f"{title} {doctype}",
            resource_doctype=doctype,
            mutation_level=mutation_level,
            visibility="normal",
            actionability="actionable_now",
        )
        for action_key, title, mutation_level in specs
    ]


def _get_related_resources(app_name, meta) -> list:
    """Distinct linked DocTypes also owned by app_name, capped at RELATED_RESOURCES_CAP."""
    related = []
    for field in meta.get_link_fields():
        linked_doctype = field.options
        if not linked_doctype or linked_doctype == meta.name:
            continue
        if linked_doctype in related:
            continue
        if not app_owns_doctype(app_name, linked_doctype):
            continue
        related.append(linked_doctype)
        if len(related) >= RELATED_RESOURCES_CAP:
            break
    return related
