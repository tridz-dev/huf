# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Domain logic for the Automation doctype.

Plain Python functions, no HTTP/whitelisting concerns and no permission
checks (those belong to the calling layer -- see ``huf.ai.automation_api``,
which is the whitelisted, permission-checked wrapper around this module).

Separation of concerns:
- ``create_automation``   -> validated creation, always starts in Draft
- ``update_automation``   -> validated field updates on an existing doc
- ``validate_automation`` -> raises on invalid/incomplete configuration
- ``pause_automation``    -> Active/Error -> Paused
- ``resume_automation``   -> Paused -> Active
- ``resolve_automation``  -> load-by-name with existence checks factored out
- ``list_automations``    -> filtered listing

Trigger CRUD (Automation Trigger child records) is intentionally out of
scope here -- ``automation_api.py`` talks to the Automation Trigger doctype
directly, the same way ``project_api.py`` talks to Conversation Pin
directly, since there is no meaningfully separate "trigger domain logic"
beyond straightforward doc CRUD.
"""

from __future__ import annotations

import frappe
from frappe import _

# Fields on Automation that a caller is allowed to set at creation time,
# beyond the required automation_name / agent / instruction.
_CREATABLE_FIELDS = (
    "description",
    "model_override",
    "project",
    "run_as_user",
    "input_template",
    "source_system",
    "is_virtual",
    "metadata",
    "conversation_mode",
    "conversation",
    "notify_user",
    "disabled",
)

# Fields an existing Automation may be updated through. Deliberately
# excludes bookkeeping fields (last_run, last_execution, last_status,
# next_execution, total_runs, last_error) and status, which is only ever
# changed via pause_automation/resume_automation/archive so that state
# transitions stay centralized.
_UPDATABLE_FIELDS = (
    "automation_name",
    "description",
    "agent",
    "model_override",
    "project",
    "run_as_user",
    "instruction",
    "input_template",
    "source_system",
    "is_virtual",
    "metadata",
    "conversation_mode",
    "conversation",
    "notify_user",
    "disabled",
)

_LIST_FIELDS = [
    "name",
    "automation_name",
    "status",
    "disabled",
    "agent",
    "project",
    "conversation_mode",
    "last_execution",
    "last_status",
    "next_execution",
    "total_runs",
    "modified",
]


def create_automation(automation_name: str, agent: str, instruction: str, **other_fields):
    """
    Create a new Automation. Always starts in Draft status regardless of
    any ``status`` passed in ``other_fields`` -- callers use
    ``pause_automation``/``resume_automation`` to move it out of Draft.

    Args:
        automation_name: unique human-readable name (required).
        agent: Agent this automation runs as (required).
        instruction: instruction text sent to the agent (required).
        **other_fields: any of ``_CREATABLE_FIELDS``; unknown keys are
            ignored rather than raising, so callers can pass through a
            client payload without pre-filtering it.

    Returns:
        The inserted Automation doc.
    """
    if not automation_name or not automation_name.strip():
        frappe.throw(_("Automation Name is required"))
    if not agent:
        frappe.throw(_("Agent is required"))
    if not instruction or not instruction.strip():
        frappe.throw(_("Instruction is required"))

    doc_fields = {
        "doctype": "Automation",
        "automation_name": automation_name.strip(),
        "agent": agent,
        "instruction": instruction,
        "status": "Draft",
    }
    for fieldname in _CREATABLE_FIELDS:
        if fieldname in other_fields and other_fields[fieldname] is not None:
            doc_fields[fieldname] = other_fields[fieldname]

    doc = frappe.get_doc(doc_fields)
    validate_automation(doc)
    doc.insert()

    return doc


def update_automation(automation, **fields):
    """
    Update an existing Automation with a validated set of fields.

    Args:
        automation: Automation name, or an already-loaded Automation doc.
        **fields: any of ``_UPDATABLE_FIELDS``; unknown keys are ignored.
            Passing a field explicitly as ``None`` is a no-op (there is no
            "clear this field" signal here beyond passing ``""``), matching
            ``project_api.update_project``'s convention.

    Returns:
        The saved Automation doc.
    """
    doc = automation if hasattr(automation, "doctype") else frappe.get_doc("Automation", automation)

    changed = False
    for fieldname in _UPDATABLE_FIELDS:
        if fieldname not in fields:
            continue
        value = fields[fieldname]
        if value is None:
            continue
        doc.set(fieldname, value)
        changed = True

    if changed:
        validate_automation(doc)
        doc.save()

    return doc


def validate_automation(automation_doc) -> None:
    """
    Raise ``frappe.ValidationError`` if ``automation_doc`` is not in a
    runnable configuration. Called from ``create_automation`` and
    ``update_automation`` before insert/save; safe to call standalone too
    (e.g. before ``run_automation_now``).

    Checks:
        - agent and instruction are present (mirrors automation_runner's
          own guards, checked here too so bad config is caught at
          save-time rather than only at run-time).
        - conversation_mode is one of the doctype's allowed options.
        - conversation_mode == "Dedicated" does not require a pre-existing
          ``conversation`` -- automation_runner._resolve_conversation_routing
          creates one lazily on first run and persists it back onto the
          Automation. What *is* required is that automation_name be set,
          since the lazy-creation path keys the conversation's external_id
          off it (``automation:{automation.name}``).
    """
    if not automation_doc.agent:
        frappe.throw(_("Automation must have an Agent configured."))

    if not automation_doc.instruction or not str(automation_doc.instruction).strip():
        frappe.throw(_("Automation must have an Instruction."))

    conversation_mode = automation_doc.conversation_mode or "New"
    if conversation_mode not in ("New", "Dedicated", "No-UI"):
        frappe.throw(_("Invalid Conversation Mode: {0}").format(conversation_mode))

    if conversation_mode == "Dedicated" and not automation_doc.automation_name:
        frappe.throw(
            _("A Dedicated-mode Automation needs an Automation Name before it can be run, so its conversation can be identified.")
        )

    if automation_doc.conversation and conversation_mode != "Dedicated":
        frappe.throw(_("Conversation can only be set when Conversation Mode is Dedicated."))


def pause_automation(automation):
    """
    Pause an Automation (status -> Paused). Idempotent: pausing an
    already-Paused automation is a no-op.

    Args:
        automation: Automation name, or an already-loaded doc.

    Returns:
        The Automation doc.
    """
    doc = resolve_automation(automation) if isinstance(automation, str) else automation

    if doc.status == "Archived":
        frappe.throw(_("Cannot pause an Archived automation."))

    if doc.status != "Paused":
        doc.db_set("status", "Paused", update_modified=True)
        doc.reload()

    return doc


def resume_automation(automation):
    """
    Resume a paused (or draft/error) Automation (status -> Active).

    Args:
        automation: Automation name, or an already-loaded doc.

    Returns:
        The Automation doc.
    """
    doc = resolve_automation(automation) if isinstance(automation, str) else automation

    if doc.status == "Archived":
        frappe.throw(_("Cannot resume an Archived automation."))

    if doc.disabled:
        frappe.throw(_("Cannot resume a disabled automation; enable it first."))

    validate_automation(doc)

    if doc.status != "Active":
        doc.db_set("status", "Active", update_modified=True)
        doc.reload()

    return doc


def resolve_automation(automation_name: str):
    """
    Load an Automation by name with a clear not-found error, factored out
    so ``automation_api.py`` (and anything else that needs an Automation
    doc by name) does not each re-implement the existence check.

    Note: this does *not* perform permission checks -- callers that expose
    this over HTTP (automation_api.py) are responsible for calling
    ``doc.has_permission(...)`` themselves, matching project_api.py's
    convention of keeping permission checks at the whitelisted layer.

    Args:
        automation_name: Automation name.

    Returns:
        The Automation doc.
    """
    if not automation_name:
        frappe.throw(_("Automation is required"))

    if not frappe.db.exists("Automation", automation_name):
        frappe.throw(_("Automation {0} does not exist").format(automation_name), frappe.DoesNotExistError)

    return frappe.get_doc("Automation", automation_name)


def list_automations(agent: str | None = None, status: str | None = None) -> list[dict]:
    """
    List Automations, optionally filtered by agent and/or status. Does not
    apply permissions beyond the caller's own doctype-level Automation
    read permission (enforced by ``frappe.get_list``); row-level
    visibility follows normal Frappe permission rules for the doctype.

    Args:
        agent: Optional Agent name to filter to.
        status: Optional status filter (Draft/Active/Paused/Error/Archived).

    Returns:
        list of dicts with summary fields, most recently modified first.
    """
    filters = {}
    if agent:
        filters["agent"] = agent
    if status:
        filters["status"] = status

    return frappe.get_list(
        "Automation",
        filters=filters,
        fields=_LIST_FIELDS,
        order_by="modified desc",
    )
