"""Trying ONE step on its own, with sample data (UX-16 "Test step").

Rules, in one place:

* Steps that only read, check or reshape data run for real. Steps that would send or change something outside the
  flow answer with the believable "Would send ..." output of :mod:`~huf.ai.flow.testrun.simulate`. An agent or an AI
  router makes a real call to the AI model. "Wait for approval" shows the card the approver would see and never
  pauses. A code step is not run here (it only runs through the audited worker, in a full test run).
* No Flow Run is created, so nothing shows up in a flow's run history. The step runs against :class:`StepTestRun`,
  a stand-in that keeps whatever the executors want to store on a run in memory.
* The step may take 30 seconds at most. Steps that can be slow (AI, web reads, loops) run in a background job that the
  queue stops at 30 seconds; quick steps run in the request.
* The output is shown with secrets hidden and at most 64 KB.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import frappe
from frappe import _

from huf.ai.flow.catalog import fields as cat
from huf.ai.flow.testrun import gate
from huf.ai.flow.testrun.effects import CHANGES, READS
from huf.ai.flow.testrun.step_sample import SOURCE_NONE, build_sample_input, clean_sample_input, pin_value, redact_output
from huf.ai.graph.error_copy import describe_exception

STEP_TIMEOUT_S = 30
RATE_LIMIT = 20
RATE_WINDOW_S = 60
AI_TYPES = ("agent.run", "router.llm")
#: Steps that can take long: they run in a background job that the queue stops at STEP_TIMEOUT_S.
SLOW_TYPES = ("agent.run", "router.llm", "foreach", "tool.call")
RESULT_TTL_S = 300
#: How long a request waits for the background worker to pick the job up before it says so.
START_WAIT_S = 10


class StepTestRun:
	"""Stands in for the Flow Run a step normally runs inside. Nothing here reaches the database."""

	doctype = "Flow Run"
	name = None
	run_mode = "Test"
	status = "Running"
	current_node_id = None
	conversation = None
	waiting = None
	context_json = None
	trigger_payload = None

	def __init__(self, flow_id: str):
		self.flow_id = flow_id
		self.owner = frappe.session.user
		self.last_agent_run = None

	def db_set(self, key, value=None, *args, **kwargs):
		for k, v in (key.items() if isinstance(key, dict) else [(key, value)]):
			setattr(self, k, v)

	def get(self, key, default=None):
		return getattr(self, key, default)

	def reload(self):
		return self


# --------------------------------------------------------------------------- permission and limits


def check_rate(user: str | None = None, limit: int = RATE_LIMIT) -> None:
	"""At most ``limit`` step tests a minute per person. Past it: a plain sentence."""
	user = user or frappe.session.user
	key = f"huf:step-test:{frappe.local.site}:{user}:{int(time.time() // RATE_WINDOW_S)}"
	try:
		cache = frappe.cache()
		count = cache.incr(key)
		if count == 1:
			cache.expire(key, RATE_WINDOW_S + 5)
	except Exception:
		return  # a cache hiccup must not stop people testing
	if count > limit:
		frappe.throw(_("You are testing steps very quickly. Wait a minute, then try again."), frappe.ValidationError)


def load_graph(flow_id: str) -> dict:
	raw = frappe.db.get_value("Flow Definition", flow_id, "definition_json")
	graph = json.loads(raw) if isinstance(raw, str) else raw
	return graph if isinstance(graph, dict) else {}


def find_node(graph: dict, node_id: str) -> dict:
	node = next((n for n in cat.graph_nodes(graph) if n["id"] == node_id), None)
	if node is None:
		frappe.throw(_("This step no longer exists. Reload the flow and try again."), frappe.DoesNotExistError)
	return node


def titles_of(graph: dict) -> dict[str, str]:
	from huf.ai.flow.catalog.api import _title

	return {n["id"]: _title(n) for n in cat.graph_nodes(graph)}


# --------------------------------------------------------------------------- what kind of step is this


def describe_step(node: dict) -> dict:
	"""``{"kind", "effect", "calls_ai", "simulated", "summary_hint"}``: how this step behaves when tested."""
	ntype = str(node.get("type") or "")
	config = node.get("config") or {}
	effect, simulated = READS, False
	if ntype == "tool.call" and config.get("tool_id"):
		effect = gate.effect_for_call(config["tool_id"], _literal_args(config.get("input")))
		simulated = effect != READS
	elif ntype in ("doc.create", "state.set", "state.delete"):
		effect, simulated = CHANGES, True
	elif ntype == "code.run":
		effect, simulated = CHANGES, True
	return {
		"kind": ntype,
		"effect": effect,
		"calls_ai": ntype in AI_TYPES,
		"simulated": simulated,
		"approval": ntype == "human.approval",
		"trigger": ntype.startswith("trigger."),
	}


def _literal_args(value: Any) -> dict:
	"""The step's own settings with references left out: enough to tell which action a multi-action tool will do."""
	if not isinstance(value, dict):
		return {}
	return {k: v for k, v in value.items() if not (isinstance(v, dict) and ("$from" in v or "$template" in v))}


def fix_hint(error: str | None, node: dict) -> str | None:
	text = (error or "").lower()
	if not text:
		return None
	if "not connected" in text:
		return "Connect it in Integrations, then test again."
	if any(w in text for w in ("then run again", "choose ", "write ", "add at least", "is required", "needs a list")):
		return "Finish this step on the Setup tab, then test again."
	if "too quickly" in text or "wait a minute" in text:
		return "Wait a minute, then test again."
	return "Check the sample data above and this step's Setup tab, then test again."


# --------------------------------------------------------------------------- running


def _now_iso() -> str:
	return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_SIMULATED_KEYS = ("simulated", "summary", "note")


def _success(node: dict, output: Any, started: float, **extra) -> dict:
	safe, shortened = redact_output(output)
	# A pinned sample of a skipped step keeps the sample fields later steps read, not the "Would ..." wording.
	pinnable = {k: v for k, v in output.items() if k not in _SIMULATED_KEYS} if extra.get("mode") == "simulated" and isinstance(output, dict) else output
	return {
		"status": "success",
		"output": safe,
		"output_shortened": shortened,
		"pin_value": pin_value(pinnable) if output is not None else None,
		"duration_ms": int((time.monotonic() - started) * 1000),
		"error": None,
		"fix_hint": None,
		"tested_at": _now_iso(),
		**extra,
	}


def _failure(node: dict, error: str, started: float, **extra) -> dict:
	return {
		"status": "failed",
		"output": None,
		"output_shortened": False,
		"pin_value": None,
		"duration_ms": int((time.monotonic() - started) * 1000),
		"error": error,
		"fix_hint": fix_hint(error, node),
		"tested_at": _now_iso(),
		**extra,
	}


def _next_title(node: dict, result: dict, titles: dict[str, str]) -> str | None:
	target = result.get("next_node_id") or (node.get("next") if node.get("type") not in ("condition", "router.llm") else None)
	return titles.get(target) if target else None


def _run_real(graph: dict, node: dict, sample: dict, stub: StepTestRun) -> dict:
	"""Execute the node through the engine's own executors (reads run, sends are simulated by the test gate)."""
	from huf.ai.flow import engine

	context = engine.GraphContext(dict(sample.get("input") or {}), run_id=None)
	context.node_outputs = dict(sample.get("steps") or {})
	if "item" in sample:
		context.push_foreach(sample["item"], 0)
	settings = engine.FlowRunContext({}, flow_run=stub, version=engine.PinnedVersion.pin(graph), context=context)
	try:
		return engine._execute_node(stub, node, settings)
	except Exception as exc:
		return {"status": "failed", "error": describe_exception(exc)}


def _approval_preview(graph: dict, node: dict, sample: dict, stub: StepTestRun) -> dict:
	"""The card an approver would get for this step, from the sample data. Nothing pauses and nobody is told."""
	from huf.ai.flow import engine
	from huf.ai.flow.support.approval_card import api_card, waiting_fields

	config = node.get("config") or {}
	context = engine.GraphContext(dict(sample.get("input") or {}))
	context.node_outputs = dict(sample.get("steps") or {})
	message = engine.render_text_refs(config.get("message", ""), context)
	data = waiting_fields(stub, node, message, context.data, config, context, graph)
	card = api_card(data.get("flow_name"), {**data, "type": "approval"}, stub.flow_id)
	atype, role, users = config.get("approver_type"), config.get("approver_role"), config.get("approver_users") or []
	if atype == "role" and role:
		who = f"Anyone with the role {role}"
	elif atype == "user" and users:
		who = ", ".join(str(u) for u in users)
	else:
		who = "Only a System Manager"
	return {"title": card["title"], "note": card["note"], "facts": card["facts"], "who_can_decide": who}


def execute_step(flow_id: str, node_id: str, sample_input: Any = None) -> dict:
	"""Test one non-trigger step. Returns the result shape documented in FIELD_CONTRACT.md section 12."""
	graph = load_graph(flow_id)
	node = find_node(graph, node_id)
	titles = titles_of(graph)
	started = time.monotonic()
	info = describe_step(node)
	try:
		sample = clean_sample_input(sample_input) if sample_input is not None else None
	except ValueError as exc:
		return _failure(node, str(exc), started, **_meta(info, titles, node))
	empty: list[str] = []
	if sample is None:
		from huf.ai.flow.catalog.api import _latest_run

		built = build_sample_input(graph, node_id, _latest_run(flow_id), titles)
		sample = built["sample_input"]
		empty = [p["title"] for p in built["parts"] if p["source"] == SOURCE_NONE]
	stub = StepTestRun(flow_id)
	meta = {**_meta(info, titles, node), "warnings": [f"There is no sample for \"{t}\", so the step worked with empty data. Edit the sample, or run the flow once, to see a real answer." for t in empty]}
	if info["approval"]:
		return _success(node, None, started, **{**meta, "mode": "preview", "preview": _approval_preview(graph, node, sample, stub)})
	if node.get("type") == "code.run":
		from huf.ai.flow.testrun.simulate import simulated_code

		out = simulated_code((node.get("config") or {}).get("profile"))
		out["summary"] = "Would run your code (code runs when you use Test run on the whole flow)"
		return _success(node, out, started, **{**meta, "mode": "simulated", "summary": out["summary"]})
	with gate.step_test_scope():
		raw = _run_real(graph, node, sample, stub)
	return _shape(node, raw, started, meta, titles)


def _meta(info: dict, titles: dict, node: dict) -> dict:
	return {"effect": info["effect"], "calls_ai": info["calls_ai"], "mode": "real", "summary": None, "preview": None, "goes_to": None, "branch": None, "warnings": []}


def _shape(node: dict, raw: dict, started: float, meta: dict, titles: dict) -> dict:
	status = raw.get("status", "success")
	if status in ("waiting_approval", "waiting_user", "paused"):
		return _failure(node, "This step pauses the flow, so it cannot be tried on its own.", started, **meta)
	if status == "failed":
		return _failure(node, str(raw.get("error") or "The step failed without saying why."), started, **meta)
	output = raw.get("output", raw.get("result"))
	simulated = bool(raw.get("simulated") or (isinstance(output, dict) and output.get("simulated")))
	extra = dict(meta)
	if simulated:
		extra["mode"] = "simulated"
		extra["summary"] = (output or {}).get("summary") if isinstance(output, dict) else None
	if node.get("type") == "condition":
		extra["branch"] = "Yes" if raw.get("result") else "No"
	extra["goes_to"] = _next_title(node, raw, titles)
	return _success(node, output, started, **extra)


# --------------------------------------------------------------------------- background job for slow steps


def result_key(token: str) -> str:
	return f"huf:step-test-result:{frappe.local.site}:{token}"


def run_job(token: str, flow_id: str, node_id: str, sample_input: Any, deadline: float) -> None:
	"""Background-job body: run the step and leave the result where the request that started it is waiting."""
	if time.time() > deadline:
		return
	frappe.cache().set(result_key(token) + ":started", 1, ex=RESULT_TTL_S)
	try:
		result = execute_step(flow_id, node_id, sample_input)
	except Exception as exc:
		result = _failure({}, describe_exception(exc), time.monotonic())
	frappe.cache().set(result_key(token), json.dumps(result, default=str), ex=RESULT_TTL_S)


def needs_job(node: dict) -> bool:
	"""True when the step may take long enough to need the 30 second stop of the queue."""
	ntype = node.get("type")
	if ntype not in SLOW_TYPES:
		return False
	if ntype == "tool.call":
		return not describe_step(node)["simulated"]
	return True


def run_with_limit(flow_id: str, node_id: str, sample_input: Any) -> dict:
	"""Quick steps run here; slow ones run in a background job and are stopped after STEP_TIMEOUT_S."""
	node = find_node(load_graph(flow_id), node_id)
	inline = frappe.flags.in_test or frappe.flags.get("huf_step_test_inline") or not needs_job(node)
	if inline:
		return execute_step(flow_id, node_id, sample_input)
	import uuid

	token = uuid.uuid4().hex
	started = time.monotonic()
	deadline = time.time() + STEP_TIMEOUT_S + 5
	frappe.enqueue(
		"huf.ai.flow.testrun.step_test.run_job",
		queue="short",
		timeout=STEP_TIMEOUT_S,
		enqueue_after_commit=False,
		token=token,
		flow_id=flow_id,
		node_id=node_id,
		sample_input=sample_input,
		deadline=deadline,
	)
	meta = _meta(describe_step(node), {}, node)
	begin = time.time()
	while time.time() < deadline:
		raw = frappe.cache().get(result_key(token))
		if raw:
			frappe.cache().delete(result_key(token))
			return json.loads(raw if isinstance(raw, str) else raw.decode())
		if time.time() - begin > START_WAIT_S and not frappe.cache().get(result_key(token) + ":started"):
			return _failure(node, "The test could not start because the background worker is busy. Try again in a moment.", started, **meta)
		time.sleep(0.3)
	return _failure(node, f"This step took longer than {STEP_TIMEOUT_S} seconds, so the test was stopped.", started, **meta)
