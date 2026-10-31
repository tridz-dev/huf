# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Execute code in Flows: the rules around the ``code.run`` step.

A Flow may run a piece of Python inside the same sandbox agents use (``huf.ai.tools.code_execution``),
but only when an administrator has turned it on, only for flows published by someone who may add
code to flows, and only with an Execution Profile. This module owns everything that is about
*whether* and *how the result comes back*; the sandbox itself is not here.

Two switches, both off by default, and both must be on to publish or run a code step:

* the server switch, site config ``huf_python_execution_enabled`` (set with ``bench set-config`` by
  whoever runs the server). It is the hard kill switch the agent tool already honours;
* ``Agent Settings.allow_code_in_flows``, which only a System Manager can change (field permission
  level 1).

Trust rule. The code and the profile of a step are read from the definition the run pinned when it
started (the published flow), never from run input. A step's ``inputs`` reach the code as data (the
``inputs`` variable) and cannot change what runs. Publishing needs ``flows.publish_sensitive`` and
``flows.execute_code``; at run time the owner of the flow must still hold ``flows.execute_code`` and
``code_execution.run``. Every refusal is a plain sentence, because it ends up on the step.

The pure helpers (``code_nodes``, ``fingerprint``, ``error_text`` ...) do not touch the database.
"""

from __future__ import annotations

import json
import os
import shutil
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from huf.ai.flow.support.code_node_result import DEFAULT_TIMEOUT_S, error_text, output_from_call  # noqa: F401

NODE_TYPE = "code.run"
EXECUTE_CAPABILITY = "flows.execute_code"
PUBLISH_CAPABILITY = "flows.publish_sensitive"
RUN_CAPABILITY = "code_execution.run"

DEFAULT_PROFILE = "Flow Scratch"
MAX_CODE_BYTES = 64 * 1024
#: How many code steps one run may execute: a ceiling that stops a loop from running code forever.
MAX_CODE_RUNS_PER_FLOW_RUN = 20
#: How long a run waits for a worker to pick a queued step up (on top of the step's own wall limit).
QUEUE_GRACE_S = 300
#: A scratch folder older than this is a leftover (the step removes its own on every outcome).
SCRATCH_MAX_AGE_S = 24 * 3600

SERVER_SWITCH_OFF = _(
	"Code execution is turned off on this server. A server administrator has to turn it on first."
)
SETTING_OFF = _("Code in Flows is turned off. A system administrator can turn it on in Settings.")


# ---------------------------------------------------------------------------
# Switches and who may do what
# ---------------------------------------------------------------------------


def server_switch_on() -> bool:
	"""The site config kill switch (``huf_python_execution_enabled``), default off."""
	from huf.ai.tools.code_execution import _is_site_enabled

	return _is_site_enabled()


def setting_on() -> bool:
	"""``Agent Settings.allow_code_in_flows`` (a System Manager's choice), default off."""
	try:
		return bool(int(frappe.db.get_single_value("Agent Settings", "allow_code_in_flows") or 0))
	except Exception:
		return False


def switch_problem() -> str | None:
	"""Why code cannot be published or run right now, or None when both switches are on."""
	if not server_switch_on():
		return str(SERVER_SWITCH_OFF)
	if not setting_on():
		return str(SETTING_OFF)
	return None


def can_execute(user: str | None = None) -> bool:
	from huf.permissions import has_capability

	return has_capability(user or frappe.session.user, EXECUTE_CAPABILITY)


def _is_system_manager(user: str) -> bool:
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


@frappe.whitelist()
def get_code_flow_status() -> dict:
	"""What the editor needs to know before it offers the Execute code step.

	Open to every signed-in user (it reveals no secret: two booleans and the profile names), because
	the editor of a Huf Manager must hide the card and Agent Settings itself is not readable for them.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.AuthenticationError)
	user = frappe.session.user
	server_switch = server_switch_on()
	allowed = setting_on()
	enabled = server_switch and allowed
	can_exec = can_execute(user)
	profiles = []
	for row in frappe.get_all(
		"Execution Profile",
		fields=["name", "approval_mode", "filesystem_policy", "max_wall_time_s", "is_builtin", "disabled"],
		order_by="is_builtin desc, name asc",
		limit_page_length=200,
	):
		reason = _profile_reason(row)
		profiles.append(
			{
				"name": row.name,
				"approval_mode": row.approval_mode,
				"filesystem_policy": row.filesystem_policy,
				"max_wall_time_s": int(row.max_wall_time_s or DEFAULT_TIMEOUT_S),
				"is_builtin": bool(row.is_builtin),
				"usable": reason is None,
				"reason": reason,
			}
		)
	return {
		"server_switch": server_switch,
		"allowed": allowed,
		"enabled": enabled,
		"can_execute": can_exec,
		"can_manage": _is_system_manager(user),
		"available": enabled and can_exec,
		"max_code_bytes": MAX_CODE_BYTES,
		"default_profile": DEFAULT_PROFILE,
		"default_timeout_s": DEFAULT_TIMEOUT_S,
		"profiles": profiles,
	}


def _profile_reason(row) -> str | None:
	"""Why a profile cannot be used by a Flow step (None when it can)."""
	if row.get("disabled"):
		return "This profile is turned off."
	if row.get("approval_mode") == "Never Allow":
		return "This profile never allows code to run."
	if row.get("filesystem_policy") == "Shared Directory":
		return "A Flow step has no conversation to share a folder with."
	return None


def profile_problem(profile_name) -> str | None:
	"""A plain sentence when ``profile_name`` cannot run a Flow step, else None."""
	if not isinstance(profile_name, str) or not profile_name.strip():
		return str(_("Pick an execution profile for this step."))
	row = frappe.db.get_value(
		"Execution Profile",
		profile_name,
		["name", "approval_mode", "filesystem_policy", "disabled", "max_wall_time_s"],
		as_dict=True,
	)
	if not row:
		return str(_("The execution profile {0} no longer exists.").format(profile_name))
	reason = _profile_reason(row)
	if reason:
		return str(_("The execution profile {0} cannot be used here: {1}").format(profile_name, _(reason)))
	return None


# ---------------------------------------------------------------------------
# Reading a definition
# ---------------------------------------------------------------------------


def code_nodes(defn) -> list[dict]:
	"""Every ``code.run`` node of a graph, in order."""
	nodes = defn.get("nodes") if isinstance(defn, dict) else None
	return [n for n in (nodes or []) if isinstance(n, dict) and n.get("type") == NODE_TYPE]


def fingerprint(node: dict) -> str:
	"""Identity of what a step runs: its id, code, profile and time limit (its inputs are data, not authority)."""
	config = node.get("config") if isinstance(node.get("config"), dict) else {}
	shape = {"code": config.get("code"), "profile": config.get("profile"), "timeout_s": config.get("timeout_s")}
	return json.dumps([node.get("id"), node.get("type"), shape], sort_keys=True, default=str)


def config_problems(node: dict) -> list[str]:
	"""Static problems of one step's own settings (no database), as plain sentences."""
	config = node.get("config") if isinstance(node.get("config"), dict) else {}
	label = node.get("_label") or node.get("id")
	problems = []
	code = config.get("code")
	if not isinstance(code, str) or not code.strip():
		problems.append(_("{0}: add the Python code to run.").format(label))
	elif len(code.encode("utf-8")) > MAX_CODE_BYTES:
		problems.append(_("{0}: the code is longer than {1} KB.").format(label, MAX_CODE_BYTES // 1024))
	timeout = config.get("timeout_s")
	if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1):
		problems.append(_("{0}: the time limit must be a whole number of seconds.").format(label))
	if not isinstance(config.get("inputs", {}), dict):
		problems.append(_("{0}: inputs must be a list of name and value pairs.").format(label))
	return [str(p) for p in problems]


def inside_loop(defn, node_id: str) -> bool:
	"""True when ``node_id`` is part of a loop body (a loop body cannot pause for code)."""
	for node in (defn.get("nodes") or []) if isinstance(defn, dict) else []:
		if isinstance(node, dict) and node.get("type") == "foreach":
			if node_id in ((node.get("config") or {}).get("body") or []):
				return True
	return False


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


def check_publish(defn, previous_defn=None, user: str | None = None) -> None:
	"""Raise unless ``defn`` may be Active with its code steps.

	Always: both switches are on, every step's settings and profile are sound, no step sits in a
	loop body. Only for steps that are new or changed since the Active version (``previous_defn``):
	the person publishing holds ``flows.execute_code`` (and ``flows.publish_sensitive``, checked by
	``publish_guard`` for every sensitive step). An edit therefore needs a person who may add code
	to publish it again; editing something else on an already published flow does not.
	"""
	steps = code_nodes(defn)
	if not steps:
		return
	user = user or frappe.session.user

	problem = switch_problem()
	if problem:
		frappe.throw(problem, frappe.ValidationError, title=_("Code cannot be published"))

	before = {fingerprint(n) for n in code_nodes(previous_defn)} if previous_defn is not None else set()
	problems: list[str] = []
	for node in steps:
		problems.extend(config_problems(node))
		if inside_loop(defn, node.get("id")):
			problems.append(
				str(_("{0}: an Execute code step cannot run inside a loop.").format(node.get("_label") or node.get("id")))
			)
		profile = (node.get("config") or {}).get("profile")
		reason = profile_problem(profile)
		if reason:
			problems.append(f"{node.get('_label') or node.get('id')}: {reason}")
		else:
			limit = frappe.db.get_value("Execution Profile", profile, "max_wall_time_s") or DEFAULT_TIMEOUT_S
			timeout = (node.get("config") or {}).get("timeout_s")
			if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout > limit:
				problems.append(
					str(
						_("{0}: the time limit is longer than the {1} seconds the profile allows.").format(
							node.get("_label") or node.get("id"), limit
						)
					)
				)
	if problems:
		frappe.throw("; ".join(problems), frappe.ValidationError, title=_("Execute code needs attention"))

	if any(fingerprint(n) not in before for n in steps) and not can_execute(user):
		frappe.throw(
			_(
				"This flow has an Execute code step. Only administrators who may run code in flows can publish "
				"it. Ask an admin to publish it for you."
			),
			frappe.PermissionError,
		)


def check_edit(defn, previous_defn, user: str | None = None) -> None:
	"""Raise unless ``user`` may save ``defn``: adding or changing a code step needs ``flows.execute_code``.

	Applies to drafts too, so nobody without the capability can write the code an admin later publishes.
	"""
	steps = code_nodes(defn)
	if not steps:
		return
	before = {fingerprint(n) for n in code_nodes(previous_defn)} if previous_defn is not None else set()
	if all(fingerprint(n) in before for n in steps):
		return
	if not can_execute(user):
		frappe.throw(
			_("You need permission to run code to add or change an Execute code step."), frappe.PermissionError
		)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_problem(flow_run, config: dict) -> str | None:
	"""Why the step may not run right now (a plain sentence), or None.

	Checked on every execution, not just at publish: both switches, the flow owner's capabilities (the
	owner is who the flow stands for; a role taken away after publishing stops the flow), and the
	step's own settings and profile, read from the run's pinned definition.
	"""
	problem = switch_problem()
	if problem:
		return problem
	owner = frappe.db.get_value("Flow Definition", getattr(flow_run, "flow_id", None), "owner")
	if not owner or not frappe.db.get_value("User", owner, "enabled"):
		return str(_("The owner of this flow is no longer an active user, so its code cannot run."))
	from huf.permissions import has_capability

	for capability in (EXECUTE_CAPABILITY, RUN_CAPABILITY):
		if not has_capability(owner, capability):
			return str(
				_("The owner of this flow ({0}) is no longer allowed to run code, so this step was not run.").format(
					owner
				)
			)
	problems = config_problems({"id": "this step", "config": config})
	if problems:
		return problems[0]
	return profile_problem(config.get("profile"))


def runs_so_far(flow_run_name: str) -> int:
	"""How many code executions this Flow Run has started (one audit row each), for the per-run cap."""
	runs = frappe.get_all("Agent Run", filters={"flow_run": flow_run_name}, pluck="name", limit_page_length=0)
	if not runs:
		return 0
	return frappe.db.count("Agent Tool Call", {"agent_run": ["in", runs], "tool": "run_python"})


# ---------------------------------------------------------------------------
# Turning the audit row into the step's output
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Getting the run going again
# ---------------------------------------------------------------------------


def flow_run_of_call(call_name: str) -> str | None:
	"""The Flow Run an ``Agent Tool Call`` belongs to (through its step's Agent Run), if any."""
	agent_run = frappe.db.get_value("Agent Tool Call", call_name, "agent_run")
	return frappe.db.get_value("Agent Run", agent_run, "flow_run") if agent_run else None


def schedule_continue(flow_run_name: str | None) -> None:
	"""Queue the continuation of a Flow Run parked on a code step (after the caller's commit).

	A separate job, not a call: the worker that ran the code has a hard time limit of its own and
	must not carry the rest of the flow.
	"""
	if not flow_run_name:
		return
	frappe.enqueue(
		"huf.ai.flow.code_node.continue_flow",
		queue="short",
		flow_run_name=flow_run_name,
		enqueue_after_commit=True,
		now=bool(getattr(frappe.flags, "in_test", False)),
	)


def continue_flow(flow_run_name: str) -> None:
	"""Job: move a Flow Run out of ``Waiting Code`` once its code step has finished."""
	from huf.ai.flow import engine

	try:
		engine.resume_code_node(flow_run_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Flow code step continue: {flow_run_name}")


def on_call_closed(call_name: str) -> None:
	"""A parked call was rejected or expired: tell the Flow Run waiting on it (no-op for an agent call)."""
	flow_run = flow_run_of_call(call_name)
	if flow_run:
		schedule_continue(flow_run)


def _fail_call(call_name: str, message: str) -> None:
	call = frappe.get_doc("Agent Tool Call", call_name)
	if call.status in ("Completed", "Failed"):
		return
	call.status = "Failed"
	call.exit_status = "Error"
	call.error_message = message
	call.save(ignore_permissions=True)


def sweep_code_waits(now=None) -> list[str]:
	"""Scheduler entry (every minute): the safety net for runs parked on a code step.

	* the step already finished (the worker's nudge was lost): continue the run;
	* the approval nobody decided has passed its deadline: expire it (which fails the step);
	* a queued step nobody picked up in time (no worker): fail the step with a message that says so.
	"""
	from huf.ai.flow import engine

	now = now or now_datetime()
	touched: list[str] = []
	for name in frappe.get_all("Flow Run", filters={"status": "Waiting Code"}, pluck="name", limit_page_length=200):
		try:
			waiting = engine._load_waiting(frappe.get_doc("Flow Run", name))
			call_name = waiting.get("agent_tool_call")
			if not call_name or not frappe.db.exists("Agent Tool Call", call_name):
				engine.fail_waiting_code_run(name, str(_("The code step lost its record, so the run was stopped.")))
				touched.append(name)
				continue
			call_status = frappe.db.get_value("Agent Tool Call", call_name, "status")
			if call_status in ("Completed", "Failed"):
				engine.resume_code_node(name)
				touched.append(name)
				continue
			deadline = waiting.get("timeout_at")
			if deadline and get_datetime(deadline) <= now:
				approval = waiting.get("approval")
				if approval and frappe.db.get_value("Agent Execution Approval", approval, "status") == "Pending":
					from huf.huf.doctype.agent_execution_approval.agent_execution_approval import _mark_expired

					_mark_expired(frappe.get_doc("Agent Execution Approval", approval))
				else:
					_fail_call(
						call_name,
						str(
							_(
								"The code did not start in time. A background worker may not be running; ask an "
								"administrator to check."
							)
						),
					)
				engine.resume_code_node(name)
				touched.append(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Flow code wait sweep: {name}")
	return touched


# ---------------------------------------------------------------------------
# Scratch folders
# ---------------------------------------------------------------------------


def purge_scratch(now_ts: float | None = None, max_age_s: int = SCRATCH_MAX_AGE_S) -> list[str]:
	"""Scheduler entry (daily): delete scratch folders older than a day (leftovers of a killed worker)."""
	from huf.ai.tools.code_execution import SCRATCH_SUBDIR, get_files_path

	base = os.path.join(get_files_path(is_private=True), SCRATCH_SUBDIR)
	if not os.path.isdir(base):
		return []
	cutoff = (now_ts or time.time()) - max_age_s
	removed = []
	for entry in os.scandir(base):
		try:
			if entry.is_dir(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < cutoff:
				shutil.rmtree(entry.path, ignore_errors=True)
				removed.append(entry.name)
		except OSError:
			continue
	return removed


def deadline_iso(wall_s: int, approval_expires_on=None) -> str:
	"""When a parked step is given up on: the approval's own expiry, else its wall limit plus the queue grace."""
	if approval_expires_on:
		return get_datetime(approval_expires_on).isoformat()
	return add_to_date(now_datetime(), seconds=int(wall_s) + QUEUE_GRACE_S).isoformat()
