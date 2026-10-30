"""Where a test run decides, step by step, to run something for real or to skip it.

Three entry points, one rule: ``reads`` run, ``changes`` and ``sends`` are skipped and answer with a simulated
output (see :mod:`~huf.ai.flow.testrun.simulate`).

* :func:`simulate_node` is called by the engine before it runs a node (``tool.call``, ``doc.create``, ``code.run``).
* :func:`agent_tool_gate` / :func:`mcp_tool_gate` are called by the tools an agent step uses, so an agent in a test
  run can look things up but cannot send or change anything.
* :func:`approval_extras` / :func:`notify_test_owner` shape a test run's approval pause.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable

import frappe

from huf.ai.flow.testrun import STORED_TEST
from huf.ai.flow.testrun.effects import CHANGES, READS, tool_effect
from huf.ai.flow.testrun.simulate import simulated_code, simulated_document, simulated_output, simulated_state

TEST_NOTE = "Test: you can approve this yourself"
# Code steps run for real only in the throw-away scratch profile (it has no network and no site access).
REAL_CODE_PROFILE = "Flow Scratch"

def _log_doubt(what: str, exc: BaseException) -> None:
	"""Every "I could not tell" on the test-or-real decision is logged, because the answer given is the safe one."""
	try:
		frappe.logger("huf").warning(f"Test-run gate could not tell ({what}); treating the call as a test: {exc!r}")
	except Exception:
		pass


def is_test_run(flow_run) -> bool:
	return str(getattr(flow_run, "run_mode", "") or "") == STORED_TEST


# --------------------------------------------------------------------------- testing one step on its own (UX-16)

_STEP_TEST_FLAG = "huf_step_test"


@contextmanager
def step_test_scope():
	"""While open, everything that runs in this request is a test of ONE step: reads run, sends and changes are skipped.

	There is no Flow Run behind such a test (nothing may show in the run history), so an agent's tools cannot learn
	"this is a test" from a run record. They read this flag instead (:func:`agent_run_is_test`). "Save data for later"
	steps are skipped too, inside a loop body as well.
	"""
	flags = frappe.local.flags
	before = getattr(flags, _STEP_TEST_FLAG, False)
	setattr(flags, _STEP_TEST_FLAG, True)
	try:
		yield
	finally:
		setattr(flags, _STEP_TEST_FLAG, before)


def step_test_active() -> bool:
	"""True while a one-step test is open. Fails CLOSED: if the flag cannot be read, assume a test."""
	try:
		return bool(getattr(frappe.local.flags, _STEP_TEST_FLAG, False))
	except Exception as exc:
		_log_doubt("step-test flag", exc)
		return True


def tool_type_of(tool_name: str) -> str | None:
	"""The Agent Tool Function type of a tool id (``GET``, ``Send Email`` ...), used to classify custom tools."""
	if not tool_name:
		return None
	try:
		return frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "types")
	except Exception:
		return None


def effect_for_call(tool_name: str, args: dict | None) -> str:
	from huf.ai.flow.testrun.effects import TOOL_EFFECTS

	return tool_effect(tool_name, args, None if tool_name in TOOL_EFFECTS else tool_type_of(tool_name))


def _success(output: dict) -> dict:
	return {"status": "success", "result": output, "output": output, "simulated": True}


def simulate_node(node: dict, resolve: Callable[[Any], Any]) -> dict | None:
	"""The simulated result of ``node`` in a test run, or ``None`` when the node runs for real.

	``resolve`` turns a node's ``$from`` / ``$template`` values into plain data (the run's context).
	A step that is misconfigured also returns ``None`` so the real executor reports the problem in its own words.
	"""
	ntype = node.get("type")
	config = node.get("config") or {}
	if ntype == "tool.call":
		tool_id = config.get("tool_id")
		if not tool_id:
			return None
		try:
			args = resolve(dict(config.get("input") or {}))
		except Exception as exc:
			# The real executor would fail on the same values and say so, but never trust that a send is
			# harmless: classify by the step's own literal settings, and only a plain read goes on to run.
			_log_doubt(f"resolving the inputs of {tool_id}", exc)
			args = _literal_args(config.get("input"))
		effect = effect_for_call(tool_id, args)
		if effect == READS and _decided_by_data(tool_id, config.get("input")):
			# The action (or HTTP method) comes from other data and could not be resolved: fail closed, like describe_step.
			effect = CHANGES
		if effect == READS:
			return None
		return _success(simulated_output(tool_id, effect, args))
	if ntype == "doc.create":
		return _success(simulated_document(config.get("doctype")))
	if ntype in ("state.set", "state.delete") and step_test_active():
		return _success(simulated_state(ntype, config.get("key")))
	if ntype == "code.run":
		if code_profile_is_scratch(config.get("profile")):
			return None
		return _success(simulated_code(config.get("profile")))
	return None


def code_profile_is_scratch(profile: Any) -> bool:
	"""True only for the throw-away profile "Flow Scratch" as it is shipped: a scratch folder, no network.

	The profile is a record that an administrator can edit, so the name alone is not enough: a "Flow Scratch"
	that was given a network policy, a shared folder or importable modules is treated like any other profile
	(its code is skipped in a test run). If the record cannot be read, the code is skipped.
	"""
	name = str(profile or REAL_CODE_PROFILE).strip() or REAL_CODE_PROFILE
	if name != REAL_CODE_PROFILE:
		return False
	try:
		row = frappe.db.get_value(
			"Execution Profile", name, ["filesystem_policy", "network_policy", "allowed_modules"], as_dict=True
		)
	except Exception as exc:
		_log_doubt("reading the Flow Scratch profile", exc)
		return False
	if not row:
		return True  # not created yet: the code step itself will say the profile is missing, nothing runs
	modules = row.get("allowed_modules")
	if isinstance(modules, str):
		try:
			modules = json.loads(modules) if modules.strip() else []
		except ValueError:
			return False
	return (row.get("filesystem_policy") or "Scratch Only") in ("Scratch Only", "None") and not row.get("network_policy") and not modules


def _decided_by_data(tool_id: str, value: Any) -> bool:
	from huf.ai.flow.testrun.step_test import decided_by_data

	return decided_by_data(tool_id, value)


def _literal_args(value: Any) -> dict:
	from huf.ai.flow.testrun.step_test import _literal_args as literal

	return literal(value)


# --------------------------------------------------------------------------- agents


def _run_context(ctx) -> dict:
	if isinstance(ctx, dict):
		return ctx
	inner = getattr(ctx, "context", None)
	return inner if isinstance(inner, dict) else {}


def agent_run_is_test(agent_run_id) -> bool:
	"""True when this Agent Run belongs to a test run of a flow, or runs inside a one-step test.

	Fails CLOSED (security round 2): if the records cannot be read (database error, timeout), the call is treated as a
	test, so a tool that would send or change something is simulated rather than run. The doubt is logged.
	"""
	if step_test_active():
		return True
	if not agent_run_id:
		return False
	try:
		flow_run = frappe.db.get_value("Agent Run", agent_run_id, "flow_run")
		return bool(flow_run) and frappe.db.get_value("Flow Run", flow_run, "run_mode") == STORED_TEST
	except Exception as exc:
		_log_doubt(f"looking up Agent Run {agent_run_id}", exc)
		return True


def agent_tool_gate(name: str, args: dict | None, ctx) -> str | None:
	"""JSON text an agent's tool call returns instead of running, or ``None`` to run it (not a test, or a read)."""
	if not agent_run_is_test(_run_context(ctx).get("agent_run_id")):
		return None
	effect = effect_for_call(name, args)
	if effect == READS:
		return None
	return json.dumps(simulated_output(name, effect, args), default=str)


# --------------------------------------------------------------------------- approvals


def approval_extras(flow_run) -> dict:
	"""Extra fields on a test run's ``waiting`` data: the note, and who may approve their own test."""
	if not is_test_run(flow_run):
		return {}
	return {"test_run": True, "test_note": TEST_NOTE, "test_owner": getattr(flow_run, "owner", None)}


def notify_test_owner(flow_run, waiting_data: dict) -> None:
	"""The only notification a test run sends: an in-app bell entry for the person testing. No email, no Slack."""
	owner = getattr(flow_run, "owner", None)
	if not owner or owner in ("Guest",):
		return
	try:
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		from huf.ai.flow.support.approval_card import build_card, flow_name_of

		card = build_card(waiting_data.get("flow_name") or flow_name_of(flow_run), waiting_data)
		enqueue_create_notification(
			frappe.db.get_value("User", owner, "email") or owner,
			{
				"type": "Assignment",
				"document_type": "Flow Run",
				"document_name": flow_run.name,
				"subject": f"Test: {card['headline']}",
				"email_content": f"<p>{TEST_NOTE}.</p>",
			},
		)
	except Exception as exc:
		frappe.logger("huf").warning(f"Could not add the test approval to the bell of {owner}: {exc}")

