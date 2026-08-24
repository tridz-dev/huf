# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Whitelisted API endpoints for the Automation doctype and its Automation
Trigger children.

Thin wrappers around ``huf.ai.automation_service`` (domain logic) and
``huf.ai.automation_runner.run_automation`` (execution). Every endpoint
resolves "the current user" from ``frappe.session.user`` and enforces
permissions via ``frappe.has_permission`` / a document's own
``has_permission`` check -- a ``user`` value supplied by the client is
never trusted for permission-sensitive operations. This mirrors the
conventions used in ``huf.ai.project_api``.
"""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai import automation_service, automation_runtime_flag


def _ensure_agent_automations_editable(agent_name):
	"""Block non-admins from creating/editing/deleting Automations or
	Automation Triggers that target a locked system agent.

	This is the Automation-model analog of
	``Agent._validate_system_agent_immutability()``'s ``protected_fields``
	check (huf/huf/doctype/agent/agent.py). Since Automation is a separate
	doctype rather than an Agent child table, that check can't cover it --
	Automations pointing at a system agent need their own guard here, or a
	non-admin could freely create/edit/delete automations (this track's
	replacement for the old Triggers tab) on an agent whose own identity
	fields are otherwise locked. Mirrors the same bypass conditions
	(seeding/install/migrate, System Manager role).
	"""
	if not agent_name:
		return
	if (
		frappe.flags.in_seeding
		or frappe.flags.in_install
		or frappe.flags.in_migrate
		or "System Manager" in frappe.get_roles()
	):
		return
	is_system = frappe.db.get_value("Agent", agent_name, "is_system")
	if is_system:
		frappe.throw(
			_(
				"Only System Managers can create or modify automations for the "
				"system agent '{0}'."
			).format(agent_name),
			frappe.PermissionError,
			title=_("System Agent Protected"),
		)

# Fields a client may set when creating/updating an Automation Trigger.
# ``automation`` and ``trigger_type`` are handled explicitly by
# create_trigger; everything else here is passed straight through.
_TRIGGER_FIELDS = (
    # NOTE: trigger_name deliberately excluded — Automation Trigger's
    # autoname is field:trigger_name, so a plain doc.set()+doc.save() would
    # silently desync doc.name from doc.trigger_name instead of renaming.
    # Renaming (if ever needed) must go through frappe.rename_doc()
    # explicitly, not this generic field-update path.
    "disabled",
    "schedule_type",
    "cron_expression",
    "run_at",
    "scheduled_interval",
    "timezone",
    "start_at",
    "end_at",
    "misfire_policy",
    "interval_count",
    "reference_doctype",
    "doc_event",
    "prompt_field",
    "prompt_field_mode",
    "condition",
    "webhook_slug",
    "webhook_key",
    "allowed_methods",
    "auth_mode",
    "signature_header",
    "secret",
    "response_mode",
    "app_name",
    "event_name",
    "event_source",
    "payload_mapping",
    "source_system",
    "metadata",
    "disabled_reason",
)


# ---------------------------------------------------------------------------
# Automation CRUD / lifecycle
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_automations(agent: str | None = None, status: str | None = None) -> list[dict]:
    """
    List Automations visible to the current user.

    Args:
        agent: Optional Agent name to filter to.
        status: Optional status filter (Draft/Active/Paused/Error/Archived).

    Returns:
        list of dicts with automation summary fields.
    """
    if not frappe.has_permission("Automation", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    return automation_service.list_automations(agent=agent, status=status)


@frappe.whitelist()
def get_automation(automation: str) -> dict:
    """
    Get a single Automation.

    Args:
        automation: Automation name.

    Returns:
        dict of the automation's fields.
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("read"):
        frappe.throw(_("You do not have permission to view this automation."), frappe.PermissionError)

    return doc.as_dict()


@frappe.whitelist()
def create_automation(automation_name: str, agent: str, instruction: str, **kwargs) -> dict:
    """
    Create a new Automation (always starts in Draft status).

    Args:
        automation_name: unique human-readable name (required).
        agent: Agent this automation runs as (required).
        instruction: instruction text sent to the agent (required).
        **kwargs: any other creatable field (description, project,
            conversation_mode, model_override, run_as_user,
            input_template, notify_user, ...); unknown keys are ignored.

    Returns:
        dict of the created automation's fields.
    """
    if not frappe.has_permission("Automation", "create"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    _ensure_agent_automations_editable(agent)

    doc = automation_service.create_automation(automation_name, agent, instruction, **kwargs)

    return doc.as_dict()


@frappe.whitelist()
def update_automation(automation: str, **kwargs) -> dict:
    """
    Update an existing Automation. Only known, explicit fields are
    accepted -- arbitrary client-supplied field mutation is not allowed
    (see ``automation_service._UPDATABLE_FIELDS``).

    Args:
        automation: Automation name.
        **kwargs: any updatable field, if changing.

    Returns:
        dict of the updated automation's fields.
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to edit this automation."), frappe.PermissionError)

    _ensure_agent_automations_editable(doc.agent)

    doc = automation_service.update_automation(doc, **kwargs)

    return doc.as_dict()


@frappe.whitelist()
def archive_automation(automation: str) -> dict:
    """
    Archive an Automation (status transition, not a destructive delete).

    Args:
        automation: Automation name.

    Returns:
        dict of the archived automation's fields.
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to archive this automation."), frappe.PermissionError)

    doc.db_set("status", "Archived", update_modified=True)
    doc.reload()

    return doc.as_dict()


@frappe.whitelist()
def delete_automation(automation: str) -> dict:
    """
    Permanently delete an Automation. Only allowed while the automation is
    Draft or Archived -- an Active/Paused/Error automation must be
    archived first, so a live automation can never be deleted out from
    under a scheduler/webhook that references it.

    Args:
        automation: Automation name.

    Returns:
        dict with {"success": True}.
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("delete"):
        frappe.throw(_("You do not have permission to delete this automation."), frappe.PermissionError)

    _ensure_agent_automations_editable(doc.agent)

    if doc.status not in ("Draft", "Archived"):
        frappe.throw(
            _("Automation '{0}' must be Draft or Archived before it can be deleted (current status: {1}).").format(
                automation, doc.status
            )
        )

    frappe.delete_doc("Automation", automation)

    return {"success": True}


@frappe.whitelist()
def run_automation_now(automation: str) -> dict:
    """
    Run an Automation immediately (bypassing any trigger/schedule).

    Args:
        automation: Automation name.

    Returns:
        The dict returned by ``huf.ai.automation_runner.run_automation``
        (``success``, ``status``, ``agent_run_id``, ``conversation_id``, ...).
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to run this automation."), frappe.PermissionError)

    automation_service.validate_automation(doc)

    from huf.ai.automation_runner import run_automation

    return run_automation(automation, now=True, initiating_user=frappe.session.user)


@frappe.whitelist()
def pause_automation(automation: str) -> dict:
    """
    Pause an Automation (status -> Paused).

    Args:
        automation: Automation name.

    Returns:
        dict of the paused automation's fields.
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to pause this automation."), frappe.PermissionError)

    doc = automation_service.pause_automation(doc)

    return doc.as_dict()


@frappe.whitelist()
def resume_automation(automation: str) -> dict:
    """
    Resume a paused (or draft/error) Automation (status -> Active).

    Args:
        automation: Automation name.

    Returns:
        dict of the resumed automation's fields.
    """
    doc = automation_service.resolve_automation(automation)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to resume this automation."), frappe.PermissionError)

    doc = automation_service.resume_automation(doc)

    return doc.as_dict()


# ---------------------------------------------------------------------------
# Automation Trigger CRUD
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_triggers(automation: str) -> list[dict]:
    """
    List Automation Trigger rows for an Automation.

    Args:
        automation: Automation name.

    Returns:
        list of dicts with trigger summary fields.
    """
    automation_doc = automation_service.resolve_automation(automation)
    if not automation_doc.has_permission("read"):
        frappe.throw(_("You do not have permission to view this automation."), frappe.PermissionError)

    return frappe.get_list(
        "Automation Trigger",
        filters={"automation": automation},
        fields=[
            "name",
            "trigger_name",
            "automation",
            "status",
            "disabled",
            "trigger_type",
            "schedule_type",
            "cron_expression",
            "last_execution",
            "next_execution",
            "modified",
        ],
        order_by="modified desc",
    )


@frappe.whitelist()
def create_trigger(automation: str, trigger_type: str, **kwargs) -> dict:
    """
    Create an Automation Trigger for an Automation.

    Args:
        automation: Automation name (required).
        trigger_type: one of Schedule/Doc Event/Webhook/App Event/Manual
            (required).
        **kwargs: any other Automation Trigger field, per trigger_type
            (trigger_name, cron_expression, reference_doctype, doc_event,
            webhook_slug, app_name, event_name, ...); unknown keys are
            ignored.

    Returns:
        dict of the created trigger's fields.
    """
    automation_doc = automation_service.resolve_automation(automation)
    if not automation_doc.has_permission("write"):
        frappe.throw(_("You do not have permission to modify this automation."), frappe.PermissionError)

    _ensure_agent_automations_editable(automation_doc.agent)

    if not trigger_type or not trigger_type.strip():
        frappe.throw(_("Trigger Type is required"))

    if not frappe.has_permission("Automation Trigger", "create"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    # trigger_name is deliberately excluded from _TRIGGER_FIELDS (see the
    # comment on that tuple) so update_trigger can never silently desync
    # doc.name from it. But it is Automation Trigger's autoname source
    # (field:trigger_name) -- Frappe requires it be set at insert time, so
    # create_trigger (unlike update_trigger) still accepts it explicitly,
    # generating a reasonable default if the caller did not supply one.
    trigger_name = kwargs.get("trigger_name") or f"{automation}-{trigger_type}-{frappe.generate_hash(length=6)}"

    doc_fields = {
        "doctype": "Automation Trigger",
        "automation": automation,
        "trigger_type": trigger_type,
        "trigger_name": trigger_name,
    }
    for fieldname in _TRIGGER_FIELDS:
        if fieldname in kwargs and kwargs[fieldname] is not None:
            doc_fields[fieldname] = kwargs[fieldname]

    doc = frappe.get_doc(doc_fields)
    doc.insert()

    return doc.as_dict()


@frappe.whitelist()
def update_trigger(trigger: str, **kwargs) -> dict:
    """
    Update an existing Automation Trigger. Only known, explicit fields are
    accepted (see ``_TRIGGER_FIELDS``); ``automation`` cannot be
    reassigned through this endpoint.

    Args:
        trigger: Automation Trigger name.
        **kwargs: any updatable trigger field, if changing.

    Returns:
        dict of the updated trigger's fields.
    """
    doc = frappe.get_doc("Automation Trigger", trigger)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to edit this trigger."), frappe.PermissionError)

    _ensure_agent_automations_editable(frappe.db.get_value("Automation", doc.automation, "agent"))

    changed = False
    for fieldname in _TRIGGER_FIELDS:
        if fieldname not in kwargs:
            continue
        value = kwargs[fieldname]
        if value is None:
            continue
        doc.set(fieldname, value)
        changed = True

    if changed:
        doc.save()

    return doc.as_dict()


@frappe.whitelist()
def delete_trigger(trigger: str) -> dict:
    """
    Delete an Automation Trigger.

    Args:
        trigger: Automation Trigger name.

    Returns:
        dict with {"success": True}.
    """
    doc = frappe.get_doc("Automation Trigger", trigger)
    if not doc.has_permission("delete"):
        frappe.throw(_("You do not have permission to delete this trigger."), frappe.PermissionError)

    _ensure_agent_automations_editable(frappe.db.get_value("Automation", doc.automation, "agent"))

    frappe.delete_doc("Automation Trigger", trigger)

    return {"success": True}


@frappe.whitelist()
def list_scheduled_automations() -> list[dict]:
    """
    List Automations that have at least one enabled Schedule-type
    Automation Trigger. Intended for a future "Scheduled" UI; this task
    only needs the query itself to be correct.

    Returns:
        list of dicts with automation summary fields plus the matching
        trigger's schedule details (one row per Automation; if an
        Automation has multiple enabled Schedule triggers, the most
        recently modified one is used).
    """
    if not frappe.has_permission("Automation", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    trigger_rows = frappe.get_all(
        "Automation Trigger",
        filters={
            "trigger_type": "Schedule",
            "disabled": 0,
        },
        fields=[
            # "trigger" is a MariaDB reserved word, so this cannot be
            # aliased to "trigger" -- use "trigger_id" instead.
            "name as trigger_id",
            "automation",
            "schedule_type",
            "cron_expression",
            "run_at",
            "scheduled_interval",
            "next_execution",
            "modified",
        ],
        order_by="modified desc",
    )
    if not trigger_rows:
        return []

    # Keep only the most-recently-modified enabled Schedule trigger per
    # automation (rows are already ordered by modified desc).
    trigger_by_automation = {}
    for row in trigger_rows:
        trigger_by_automation.setdefault(row["automation"], row)

    automation_names = list(trigger_by_automation.keys())

    automations = frappe.get_list(
        "Automation",
        filters={"name": ["in", automation_names]},
        fields=[
            "name",
            "automation_name",
            "status",
            "disabled",
            "agent",
            "project",
            "last_execution",
            "last_status",
            "next_execution",
        ],
    )

    for automation in automations:
        trigger_row = trigger_by_automation.get(automation["name"], {})
        automation["trigger"] = trigger_row.get("trigger_id")
        automation["schedule_type"] = trigger_row.get("schedule_type")
        automation["cron_expression"] = trigger_row.get("cron_expression")
        automation["run_at"] = trigger_row.get("run_at")
        automation["scheduled_interval"] = trigger_row.get("scheduled_interval")
        automation["trigger_next_execution"] = trigger_row.get("next_execution")

    return automations


@frappe.whitelist()
def get_automation_runtime_mode() -> dict:
	"""
	Get the current automation trigger runtime mode.

	Returns:
		dict with {"mode": "new"} or {"mode": "legacy"}.
	"""
	return {"mode": automation_runtime_flag.automation_runtime_mode()}
