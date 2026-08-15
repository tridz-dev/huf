# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Copy legacy ``Agent Trigger`` rows into the ``Automation`` + ``Automation Trigger`` schema.

One Agent Trigger becomes one Automation (the "what to run": agent + a *snapshot*
of the agent's resolved prompt) plus one Automation Trigger (the "when to run":
schedule / doc-event / webhook / app-event configuration copied across field by
field).

Design notes
------------
*   **Non-destructive.**  Agent Trigger rows are never written to or deleted —
    the legacy doctype stays read-only for the whole compatibility window.
*   **Idempotent.**  ``Automation Trigger`` is autonamed ``field:trigger_name``,
    so the migrated trigger carries the *same* name as its source Agent Trigger.
    That name is the migration key: if it already exists, the row is skipped.
*   **Traceability.**  No new field was added to either doctype.  Both already
    expose a ``metadata`` JSON field, so provenance is written there as
    ``metadata.migrated_from = {"doctype": "Agent Trigger", "name": ...}``.
    That is the least invasive of the two options in the brief (no schema
    change, no extra migration of the DDL).
*   **Prompt snapshot.**  ``Automation.instruction`` is filled from
    ``huf.ai.prompt_resolver.resolve_prompt(agent_doc)`` — the *currently*
    resolved text, frozen at migration time — and tagged with
    ``metadata.migrated_from_agent_prompt = true``.  It is deliberately not a
    live reference back to the Agent.
"""

import json

import frappe


PATCH_TITLE = "Migrate Agent Triggers to Automations"

#: Fields whose name and meaning are identical on both trigger doctypes.
TRIGGER_FIELD_MAP = (
	"trigger_type",
	"status",
	"disabled",
	"disabled_reason",
	"is_virtual",
	"source_system",
	# Schedule
	"scheduled_interval",
	"interval_count",
	"last_execution",
	"next_execution",
	# Doc Event
	"reference_doctype",
	"doc_event",
	"prompt_field",
	"condition",
	# Webhook
	"webhook_slug",
	"webhook_key",
	# App Event
	"app_name",
	"event_name",
)

#: Agent Trigger.status -> Automation.status (the two Selects differ).
AUTOMATION_STATUS_MAP = {
	"Active": "Active",
	"Draft": "Draft",
	"Disabled": "Paused",
	"Error": "Error",
}


def execute():
	if not frappe.db.table_exists("Agent Trigger"):
		return

	report = {"total": 0, "migrated": 0, "skipped": 0, "failed": 0, "ambiguous": 0}

	names = frappe.get_all("Agent Trigger", pluck="name", order_by="creation asc")
	report["total"] = len(names)

	for name in names:
		try:
			outcome = _migrate_one(name)
		except Exception as error:
			report["failed"] += 1
			frappe.db.rollback()
			frappe.log_error(
				title=PATCH_TITLE,
				message=f"Agent Trigger '{name}' could not be migrated: {error}\n\n"
				f"{frappe.get_traceback()}",
			)
			continue

		report[outcome] += 1
		if outcome == "migrated":
			# Commit per row so one bad row cannot roll back the good ones.
			frappe.db.commit()

	summary = (
		f"{PATCH_TITLE}: total={report['total']} migrated={report['migrated']} "
		f"skipped={report['skipped']} failed={report['failed']} "
		f"ambiguous={report['ambiguous']}"
	)
	print(summary)
	if report["failed"] or report["ambiguous"]:
		frappe.log_error(title=PATCH_TITLE, message=summary)

	return report


def _migrate_one(agent_trigger_name):
	"""Migrate a single Agent Trigger. Returns 'migrated' | 'skipped' | 'ambiguous'."""
	existing = frappe.db.get_value(
		"Automation Trigger", agent_trigger_name, ["name", "metadata"], as_dict=True
	)
	if existing:
		if _migrated_from(existing.metadata) == agent_trigger_name:
			# Already produced by an earlier run of this patch.
			return "skipped"
		# Somebody hand-created an Automation Trigger under this name; do not
		# touch it and do not create a duplicate under a different name either,
		# because we could not tell the two apart on the next run.
		frappe.log_error(
			title=PATCH_TITLE,
			message=f"Automation Trigger '{agent_trigger_name}' already exists but was not "
			f"created by this patch (metadata.migrated_from missing/different). "
			f"Left untouched — migrate it by hand if needed.",
		)
		return "ambiguous"

	source = frappe.get_doc("Agent Trigger", agent_trigger_name)
	automation = _create_automation(source)
	_create_automation_trigger(source, automation)
	return "migrated"


def _create_automation(source):
	instruction = _snapshot_agent_prompt(source.agent)

	automation = frappe.new_doc("Automation")
	automation.automation_name = _unique_automation_name(source)
	automation.agent = source.agent
	# Placeholder; the real snapshot is written below, bypassing sanitisation.
	automation.instruction = "(migrating)"
	automation.description = f"Migrated from Agent Trigger '{source.name}'."
	automation.status = AUTOMATION_STATUS_MAP.get(source.status or "", "Draft")
	automation.disabled = source.disabled or 0
	automation.source_system = source.source_system
	automation.is_virtual = source.is_virtual or 0
	automation.conversation_mode = "New"
	automation.metadata = json.dumps(
		{
			"migrated_from_agent_prompt": True,
			"migrated_from": {"doctype": "Agent Trigger", "name": source.name},
		}
	)
	automation.insert(ignore_permissions=True)

	# ``Automation.instruction`` is a Long Text field, so Frappe runs
	# ``sanitize_html`` over it on save and silently eats angle-bracket
	# placeholders that are common in prompts (``<Table Name>``, ``<agent name>``).
	# The snapshot has to be byte-identical to the resolved prompt, so write it
	# straight to the column instead of through the document layer.
	frappe.db.set_value(
		"Automation", automation.name, "instruction", instruction, update_modified=False
	)
	automation.instruction = instruction
	return automation


def _create_automation_trigger(source, automation):
	trigger = frappe.new_doc("Automation Trigger")
	trigger.trigger_name = source.name  # keeps the migration key stable
	trigger.automation = automation.name

	for fieldname in TRIGGER_FIELD_MAP:
		trigger.set(fieldname, source.get(fieldname))

	# Agent Trigger only ever expressed interval schedules; the new doctype
	# splits that into schedule_type + the legacy interval fields.
	if (source.trigger_type or "") == "Schedule" and source.scheduled_interval:
		trigger.schedule_type = "Interval"

	metadata = _as_dict(source.metadata)
	metadata["migrated_from"] = {"doctype": "Agent Trigger", "name": source.name}
	trigger.metadata = json.dumps(metadata)

	for row in source.get("file_attachments") or []:
		trigger.append(
			"file_attachments",
			{
				"source_type": row.source_type,
				"child_table": row.child_table,
				"field_name": row.field_name,
			},
		)

	trigger.insert(ignore_permissions=True)
	return trigger


def _snapshot_agent_prompt(agent_name):
	"""Return the agent's currently resolved prompt text, frozen as a snapshot."""
	from huf.ai.prompt_resolver import resolve_prompt

	text = None
	try:
		text = resolve_prompt(frappe.get_doc("Agent", agent_name))
	except Exception as error:
		frappe.log_error(
			title=PATCH_TITLE,
			message=f"Could not resolve prompt for Agent '{agent_name}': {error}",
		)

	if not (text or "").strip():
		# Automation.instruction is mandatory, so never leave it blank.
		return f"(No prompt configured on Agent '{agent_name}' at migration time.)"

	return text


def _unique_automation_name(source):
	"""Automation is autonamed on automation_name, so avoid clashing with existing rows."""
	base = (source.trigger_name or source.name or source.agent or "Automation").strip()
	candidate = base
	suffix = 2
	while frappe.db.exists("Automation", candidate):
		candidate = f"{base} ({suffix})"
		suffix += 1
	return candidate


def _as_dict(value):
	data = value
	if isinstance(data, str):
		try:
			data = json.loads(data or "{}")
		except (ValueError, TypeError):
			return {}
	return data if isinstance(data, dict) else {}


def _migrated_from(metadata):
	source = _as_dict(metadata).get("migrated_from")
	if isinstance(source, dict):
		return source.get("name")
	return None
