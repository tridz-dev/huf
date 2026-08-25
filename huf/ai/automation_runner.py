# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Canonical execution entrypoint for the Automation doctype.

Every trigger type (Manual, Schedule, Doc Event, Webhook, App Event) is
expected to eventually converge on :func:`run_automation` as its single
execution path. This module is intentionally independent of the legacy
``huf/ai/agent_scheduler.py`` and ``huf/ai/agent_hooks.py`` files, which
continue to drive the older "Agent Trigger" doctype unchanged. Nothing here
imports from, or is imported by, those two files.

Agent execution itself is delegated to the existing
``huf.ai.agent_integration.run_agent_sync`` entrypoint (the same function
used by the chat UI, flows, scheduled/legacy triggers, and integrations) so
Automation runs get identical Agent Run bookkeeping, provider/model
resolution, and queue-vs-direct execution semantics as every other caller.
"""

from uuid import uuid4

import frappe
from frappe import _


def run_automation(
	automation_name,
	trigger_name=None,
	trigger_context=None,
	initiating_user=None,
	now=False,
	commit=True,
):
	"""Execute an Automation by name.

	Args:
		automation_name: ``name`` of the Automation doc to run.
		trigger_name: ``name`` of the Automation Trigger that fired this run,
			if any (Manual runs from the UI may pass ``None``).
		trigger_context: optional dict of trigger-supplied variables made
			available to ``automation.input_template`` rendering (e.g. a
			webhook payload, a doc event's field values, a schedule's fire
			time). Never mutated.
		initiating_user: the user on whose behalf this run should execute.
			Falls back to ``automation.run_as_user``, then the current
			session user (mirrors the pattern in ``agent_hooks.run_agent_for_doc``).
			When no ``initiating_user`` is supplied and ``automation.run_as_user``
			would switch identity away from the Automation's own owner, the
			owner must hold the System Manager role — see
			``_check_run_as_user_permission`` — otherwise a
			``frappe.PermissionError`` is raised rather than silently running
			as the configured user.
		now: if truthy, forces immediate (non-queued) execution — passed
			straight through to ``run_agent_sync``.
		commit: if truthy (the default), ``_execute`` commits the current
			database transaction once bookkeeping is written. Top-level
			callers that own their own request/job transaction (scheduler
			ticks, webhook requests, app-event API calls, manual "Run now"
			calls) should keep the default so this run's writes are durable
			right away. Callers invoking this synchronously from inside
			another doctype's ``on_update``/``after_insert``/etc hook chain
			(the doc-event automation path) MUST pass ``commit=False`` — an
			explicit commit mid-hook would also commit the *caller's* still
			in-flight document save, which is not this function's
			transaction to commit and can leave the caller's document
			partially/inconsistently persisted if a later step in its own
			hook chain fails afterward. Frappe's own request/job-dispatch
			machinery commits at the end of the request/job regardless, so
			skipping the commit here is safe, not merely deferred.

	Returns:
		The dict returned by ``run_agent_sync`` (``success``, ``status``,
		``agent_run_id``, ``conversation_id``, ...), or ``None`` if execution
		raised before an Agent Run could be produced (the exception is
		swallowed here so bookkeeping — last_status/last_error/total_runs —
		always gets written; callers that need to see the traceback should
		inspect ``automation.last_error`` afterwards, or check the logs).
	"""
	if not automation_name:
		frappe.throw(_("Automation Name is required"))

	automation = frappe.get_doc("Automation", automation_name)

	if automation.disabled:
		frappe.throw(
			_("Automation '{0}' is disabled.").format(automation_name),
			frappe.ValidationError,
		)

	# Automatic triggers (Doc Event, Schedule, Webhook, App Event -- anything
	# that supplies a trigger_name) only run a "live" Automation. Manual runs
	# (trigger_name=None, from "Run now" or chat) are exempt so a Draft
	# automation can still be tested before it's activated. Without this
	# gate, `status` is purely decorative: pause_automation/archive_automation
	# only ever set `status`, never `disabled`, so a Paused or Archived
	# automation's triggers would keep firing exactly like an Active one.
	if trigger_name and automation.status != "Active":
		frappe.throw(
			_("Automation '{0}' is not Active (status: {1}) -- resume it to let triggers run.").format(
				automation_name, automation.status
			),
			frappe.ValidationError,
		)

	if not automation.agent:
		frappe.throw(
			_("Automation '{0}' has no agent configured.").format(automation_name),
			frappe.ValidationError,
		)

	trigger_context = dict(trigger_context or {})

	if not initiating_user and automation.run_as_user:
		_check_run_as_user_permission(automation)

	original_user = frappe.session.user
	run_user = initiating_user or automation.run_as_user
	switched_user = False
	if run_user and run_user != original_user:
		try:
			frappe.set_user(run_user)
			switched_user = True
		except frappe.DoesNotExistError:
			# Configured/initiating user no longer exists; continue as the
			# current session user rather than failing the whole run.
			pass

	try:
		return _execute(automation, trigger_name, trigger_context, now, commit)
	finally:
		if switched_user:
			frappe.set_user(original_user)


def _check_run_as_user_permission(automation):
	"""Guard against unchecked identity impersonation via ``run_as_user``.

	Only exercised when a trigger resolves the run identity purely from
	``automation.run_as_user`` — i.e. no caller-supplied ``initiating_user``
	took precedence (that's the case for Schedule/Doc Event/Webhook/App
	Event triggers per Stage 2; ``run_automation_now`` always passes
	``initiating_user=frappe.session.user`` and never reaches this check).

	Without this, an Automation's owner could type any user — including
	Administrator — into ``run_as_user`` and have every scheduled/webhook
	fire execute with that identity's permissions, with nothing verifying
	the owner is actually allowed to impersonate it.

	Mirrors this codebase's existing privileged-impersonation convention:
	only a System Manager may act as an identity other than their own (see
	``huf/huf/doctype/agent/agent.py``'s system-agent guards and
	``huf/ai/tools/builder.py``'s ``_require_builder_capability``, both of
	which gate privileged operations on ``"System Manager" in
	frappe.get_roles(...)``).
	"""
	run_as_user = automation.run_as_user
	owner = automation.owner

	if not run_as_user or run_as_user == owner:
		return

	if "System Manager" in frappe.get_roles(owner):
		return

	frappe.throw(
		_(
			"Automation '{0}' is configured to run as '{1}', but its owner "
			"'{2}' does not have the System Manager role required to run "
			"automations as another user."
		).format(automation.name, run_as_user, owner),
		frappe.PermissionError,
	)


def _execute(automation, trigger_name, trigger_context, now, commit=True):
	instruction = _resolve_instruction(automation, trigger_context)

	conversation_id, channel_id, external_id, skip_user_message = _resolve_conversation_routing(
		automation
	)

	from huf.ai.agent_integration import run_agent_sync

	result = None
	error_message = None
	try:
		result = run_agent_sync(
			agent_name=automation.agent,
			prompt=instruction,
			model=automation.model_override or None,
			channel_id=channel_id,
			external_id=external_id,
			conversation_id=conversation_id,
			skip_user_message=skip_user_message,
			run_kind="agent",
			now=now,
			project=automation.project or None,
		)
		if not result or not result.get("success", True):
			error_message = (result or {}).get("error") or _("Agent run did not complete successfully.")
	except Exception:
		error_message = frappe.get_traceback()
		frappe.log_error(
			title=f"Automation run failed: {automation.name}",
			message=error_message,
		)

	agent_run_id = (result or {}).get("agent_run_id")
	conversation_id_result = (result or {}).get("conversation_id")

	if agent_run_id:
		# Link the Agent Run back to this Automation / Automation Trigger
		# (fields added in task B4). run_agent_sync has no knowledge of
		# Automations, so this linkage happens as a follow-up write here.
		frappe.db.set_value(
			"Agent Run",
			agent_run_id,
			{
				"automation": automation.name,
				"automation_trigger": trigger_name,
			},
			update_modified=False,
		)

	if (
		automation.conversation_mode == "Dedicated"
		and not automation.conversation
		and conversation_id_result
	):
		automation.db_set("conversation", conversation_id_result, update_modified=False)

	_update_automation_bookkeeping(automation, agent_run_id, error_message)
	if trigger_name:
		_update_trigger_bookkeeping(trigger_name, error_message)

	if commit:
		# Only for top-level callers (scheduler/webhook/app-event/manual
		# "Run now") that own the current request/job transaction. Doc-event
		# callers run inside another doctype's hook chain and pass
		# commit=False — see run_automation()'s docstring for why.
		frappe.db.commit()

	return result


def _resolve_instruction(automation, trigger_context):
	"""Build the final instruction text sent to the agent.

	If ``automation.input_template`` is set, it is rendered as a Jinja
	template via ``frappe.render_template`` — the standard Frappe-wide
	templating convention (used for print formats, notifications, email
	templates, etc.). No template/variable-substitution helper already
	exists specifically in huf/ai/ (agent_hooks.py builds prompts with plain
	f-strings, not a reusable template), so this follows the platform-level
	convention rather than inventing a bespoke syntax.

	The template context exposes: every key from ``trigger_context``, plus
	``automation`` (the Automation doc) and ``instruction`` (the raw
	``automation.instruction`` text, for templates that want to interpolate
	it verbatim).
	"""
	instruction = automation.instruction or ""

	if automation.input_template:
		context = dict(trigger_context)
		context.setdefault("automation", automation)
		context.setdefault("instruction", instruction)
		try:
			rendered = frappe.render_template(automation.input_template, context, is_path=False)
		except Exception:
			frappe.log_error(
				title=f"Automation input_template render failed: {automation.name}",
				message=frappe.get_traceback(),
			)
		else:
			if rendered and rendered.strip():
				instruction = rendered
	elif trigger_context.get("_doc_event_supplement"):
		# Doc Event triggers (huf/ai/automation_hooks.py) compose an
		# event-specific supplement (event name, doc data, prompt_field
		# content, OCR/audio-transcribed attachment text) and pass it here
		# via this reserved trigger_context key. Per the plan's explicit
		# rule that prompt_field must not silently replace the Automation's
		# own instruction, the supplement is always APPENDED after
		# automation.instruction, never substituted for it — an
		# input_template (handled above) remains the only way to fully
		# override the default composition.
		instruction = (instruction + chr(10) + chr(10) + trigger_context["_doc_event_supplement"]).strip()

	if not instruction or not instruction.strip():
		frappe.throw(_("Automation '{0}' has no instruction to execute.").format(automation.name))

	return instruction


def _resolve_conversation_routing(automation):
	"""Decide conversation_id / channel_id / external_id / skip_user_message
	for run_agent_sync based on automation.conversation_mode.

	run_agent_sync has no native "always fresh" or "invisible" conversation
	concept; both are achieved here the same way the rest of the codebase
	does it (see huf/ai/memory_tools.py's background extraction call):
	  - a unique external_id forces ConversationManager to find no existing
	    session and create a brand new Agent Conversation.
	  - skip_user_message=True keeps the run's prompt out of the visible
	    chat history (used for "No-UI" runs).
	"""
	run_uuid = uuid4().hex[:12]
	channel_id = "automation"

	if automation.conversation_mode == "Dedicated":
		if automation.conversation:
			return automation.conversation, channel_id, f"automation:{automation.name}", False
		# No dedicated conversation recorded yet: use a stable external_id so
		# a concurrent/retried run for the same Automation still lands in one
		# conversation; the resulting conversation is then persisted back
		# onto automation.conversation by _execute() so later runs reuse it
		# via automation.conversation directly.
		return None, channel_id, f"automation:{automation.name}", False

	if automation.conversation_mode == "No-UI":
		return None, channel_id, f"automation-noui:{automation.name}:{run_uuid}", True

	# "New" (default): always start a fresh, unique conversation.
	return None, channel_id, f"automation-new:{automation.name}:{run_uuid}", False


def _update_automation_bookkeeping(automation, agent_run_id, error_message):
	automation.reload()
	updates = {
		"last_execution": frappe.utils.now_datetime(),
		"total_runs": (automation.total_runs or 0) + 1,
		"last_status": "Error" if error_message else "Active",
		"last_error": error_message or "",
	}
	if agent_run_id:
		updates["last_run"] = agent_run_id
	for fieldname, value in updates.items():
		automation.db_set(fieldname, value, update_modified=False)


def _update_trigger_bookkeeping(trigger_name, error_message):
	if not frappe.db.exists("Automation Trigger", trigger_name):
		return

	meta = frappe.get_meta("Automation Trigger")
	updates = {}
	if meta.has_field("last_execution"):
		updates["last_execution"] = frappe.utils.now_datetime()
	if error_message and meta.has_field("status"):
		updates["status"] = "Error"

	if not updates:
		return

	trigger_doc = frappe.get_doc("Automation Trigger", trigger_name)
	for fieldname, value in updates.items():
		trigger_doc.db_set(fieldname, value, update_modified=False)
