# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Real, bounded comparison: compiled HUF Procedure execution vs a naive agent tool-calling
loop, on the SAME task, SAME tools, SAME starting state, SAME correctness checks.

This module implements the CORRECTED methodology the user approved after rejecting
``Tracks/SafeDeoptExperiment/PLAN_PROCEDURE_VS_NAIVE_SPECULATIVE.md``'s "reframe only, do
not run" recommendation. The corrections (verbatim from the user, paraphrased into
implementation constraints):

1. Both arms run the SAME real task (benchmark-3's CRM collections follow-up: fetch overdue
   invoices for a customer set, qualify, check for an existing follow-up ToDo, create one if
   missing, mark a per-row audit outcome, compute a top-level status) against the SAME
   starting state and are scored with the SAME correctness checks -- reusing
   ``benchmarks/benchmark-3-crm-followup/invariants.py`` and this repo's own
   ``huf/ai/tests/test_benchmark3_write_runtime.py`` fixture shape (tool semantics, seed
   data, the ``_FakeTodoStore``/``_Benchmark3Invoker`` pattern reimplemented here so this
   module has no import dependency on a test file). No new scoring mechanism is invented.
2. The Procedure arm goes through the REAL ``huf.ai.graph.procedure_runtime.execute_procedure``
   against a REAL pinned graph (``huf.ai.graph.executor.PinnedVersion``) -- not a mock.
3. Both arms get an equivalent "initial interpretation" step (a real model call reading the
   user's NL request) and an equivalent "final response" step (a real model call -- or, for
   the naive arm, the loop's own natural final text turn -- summarizing the outcome). Neither
   arm gets a free pass on these.
4. The naive arm reuses ``recovery_harness.run_recovery(condition="C1", ...)`` UNCHANGED --
   the existing, real, already-tested naive-agent-loop driver. It is NOT forced into
   one-model-call-per-tool; ``run_recovery`` already lets ``LiveAPIModel`` decide when to
   call a tool vs. emit final text, once per loop iteration, exactly as it does for every
   other condition already tested in this benchmark. ``LiveAPIModel.next_step`` now parses
   and dispatches EVERY tool call a provider response returns, in order (ACCEPTANCE_PLAN_V2.md
   Sec.5 hard requirement) -- a multi-tool-call response is no longer silently truncated to
   its first call, so this arm's call counts reflect what the model actually asked for.
5. The Procedure arm reports TWO separate numbers, never blended: (a) one-time COMPILATION
   cost -- one real model call that is shown the task description and the six tool schemas
   and asked to produce the ordered call plan a human would review before pinning a
   Procedure version (this is a stand-in for ``propose_procedure_from_run`` mining an
   Agent Run -- that function needs a COMPLETED run to mine, which is circular for a
   "first ever compilation" measurement; the real mining path is exercised structurally by
   ``real_procedure_integration.py`` and is not re-derived here) -- and (b) STEADY-STATE
   per-execution cost against an ALREADY-PINNED graph: one interpretation call (bind NL to
   Procedure inputs) + the real zero-LLM ``execute_procedure`` + one final-response call.
6. Small and bounded: 5 task instances per arm per model family (distinct customer sets
   against a fresh store each -- enough to average a steady-state cost without claiming a
   large-n result), 2 model families, under the existing ~$5 ceiling from
   ``recovery_harness.MODEL_PRICING_USD_PER_MILLION_TOKENS`` / a local running total here.
7. Secret handling: this module reads ``GEMINI_API_KEY``/``GOOGLE_API_KEY`` and
   ``OPENAI_API_KEY`` only from the environment at call time (via ``recovery_harness``'s own
   provider constructors) -- it never accepts a key as a CLI argument, never logs one, and
   never writes one to any file. ``main()`` refuses to run in "live" mode if the required key
   for the requested model family is absent, rather than silently falling back to a mock.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recovery_harness import (  # noqa: E402
	MODEL_PRICING_USD_PER_MILLION_TOKENS,
	ROLE_SAMPLING,
	AtomicTool,
	LiveAPIModel,
	RunLog,
	SamplingConfig,
	ToolCallRequest,
	compute_model_step_cost_usd,
	run_recovery,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# huf/__init__.py does `import frappe` unconditionally at package import time. Every
# existing frappe-free test in this repo (huf/ai/tests/conftest.py) works around this the
# same way: stub sys.modules["frappe"] with a MagicMock BEFORE anything imports the huf
# package, only for the parts of huf.ai.graph this module needs (PinnedVersion,
# execute_procedure -- both frappe-free by their own module docstrings; only the package
# __init__ chain requires the stub, not this code's own logic). Only installed if frappe is
# not already the real module (a real bench console run supplies the genuine one).
if "frappe" not in sys.modules:
	from unittest.mock import MagicMock

	sys.modules["frappe"] = MagicMock()


# ---------------------------------------------------------------------------
# Shared task: same tools, same starting state, same seed data as
# huf/ai/tests/test_benchmark3_write_runtime.py -- reimplemented here (not imported from a
# test file) so both arms call literally the same functions against literally the same
# store.
# ---------------------------------------------------------------------------

ALLOCATED_TO = "collections@hufretail.example"
COMPANY = "Huf Retail Pvt Ltd"
PROCEDURE_NAME = "crm-followup-benchmark-3"
PROCEDURE_VERSION = "v1"

SEED_INVOICES: dict[str, list[str]] = {
	"CUST-0001": ["SINV-2001"],
	"CUST-0002": ["SINV-2002"],
	"CUST-0004": ["SINV-2004"],
	"CUST-0006": ["SINV-2006A", "SINV-2006B"],
}

#: Task instances for the steady-state measurement -- distinct customer sets, each against
#: a FRESH store, so no cross-instance interference (this is deliberately not a multi-turn
#: drift experiment -- the user's correction narrowed scope to "complete the small real-HUF
#: comparison, not expand the benchmark further").
TASK_INSTANCES: list[list[str]] = [
	["CUST-0001"],
	["CUST-0002"],
	["CUST-0004"],
	["CUST-0006"],
	["CUST-0001", "CUST-0004"],
]


def _target_identity(customer: str, invoice: str) -> str:
	return f"{customer}:{invoice}"


def _derive_operation_key(node_id: str, target_identity: str) -> str:
	return f"{PROCEDURE_NAME}:{node_id}:{target_identity}"


def _derive_idempotency_key(target_identity: str) -> str:
	return f"{PROCEDURE_NAME}:{PROCEDURE_VERSION}:{ALLOCATED_TO}:{target_identity}"


class FollowupStore:
	"""Same shape/seed as ``_FakeTodoStore`` in test_benchmark3_write_runtime.py: one
	pre-existing ToDo (TODO-3001, CUST-0002/SINV-2002/ALLOCATED_TO), autoincrementing name
	for new ones.
	"""

	def __init__(self) -> None:
		self.rows: list[dict] = [
			{
				"name": "TODO-3001",
				"reference_type": "Sales Invoice",
				"reference_name": "SINV-2002",
				"allocated_to": ALLOCATED_TO,
			}
		]
		self._counter = 3002

	def find(self, reference_type: str, reference_name: str, allocated_to: str) -> str | None:
		for row in self.rows:
			if (
				row["reference_type"] == reference_type
				and row["reference_name"] == reference_name
				and row["allocated_to"] == allocated_to
			):
				return row["name"]
		return None

	def create(self, reference_type: str, reference_name: str, allocated_to: str) -> str:
		name = f"TODO-{self._counter}"
		self._counter += 1
		self.rows.append(
			{"name": name, "reference_type": reference_type, "reference_name": reference_name, "allocated_to": allocated_to}
		)
		return name


def expected_outcome_for(customer: str, invoice: str, store_before: FollowupStore) -> str:
	"""Ground truth (computed from the store's state BEFORE any run touches it, plus the
	fixed qualification rule "everything qualifies" that both the original benchmark-3
	fixture and this module use) -- independent of what either arm reports about itself.
	"""
	if store_before.find("Sales Invoice", invoice, ALLOCATED_TO) is not None:
		return "already_existed"
	return "created"


def make_tool_functions(store: FollowupStore, customers: list[str]) -> dict[str, Callable[..., Any]]:
	"""Six tool functions, called with ``**kwargs`` exactly as ``recovery_harness``'s
	``AtomicTool.fn`` and ``huf.ai.graph.procedure_runtime``'s ``tool_invoker`` boundary both
	require -- one implementation, two callers.
	"""

	def fetch_overdue_invoices_for(*, selected_customers: list[str] | None = None, company: str | None = None) -> list[dict]:
		custs = selected_customers if selected_customers is not None else customers
		rows = []
		for customer in custs:
			for invoice in SEED_INVOICES.get(customer, []):
				target_identity = _target_identity(customer, invoice)
				rows.append(
					{
						"customer_id": customer,
						"invoice": invoice,
						"operation_key": _derive_operation_key("create_todo", target_identity),
						"idempotency_key": _derive_idempotency_key(target_identity),
					}
				)
		return rows

	def deterministic_qualification_check(*, invoice: str) -> dict:
		return {"invoice": invoice, "qualifies": True}

	def existing_followup_check(*, reference_type: str, reference_name: str, allocated_to: str) -> dict:
		existing = store.find(reference_type, reference_name, allocated_to)
		return {"existing": existing}

	def create_todo(
		*,
		reference_type: str,
		reference_name: str,
		allocated_to: str,
		operation_key: str | None = None,
		idempotency_key: str | None = None,
		skip_if_existing: str | None = None,
	) -> dict:
		if skip_if_existing:
			return {"created": False, "already_existed": True, "name": skip_if_existing}
		existing = store.find(reference_type, reference_name, allocated_to)
		if existing:
			return {"created": False, "already_existed": True, "name": existing}
		name = store.create(reference_type, reference_name, allocated_to)
		return {"created": True, "already_existed": False, "name": name}

	def mark_row(*, customer_id: str, invoice: str, qualifies: bool, created: bool, already_existed: bool) -> dict:
		if not qualifies:
			outcome = "skipped_not_qualified"
		elif already_existed:
			outcome = "already_existed"
		elif created:
			outcome = "created"
		else:
			outcome = "failed"
		return {"customer_id": customer_id, "invoice": invoice, "outcome": outcome}

	def compute_summary(*, rows: list[dict], company: str | None = None) -> dict:
		outcomes = [r["outcome"] for r in rows if r["outcome"] != "skipped_not_qualified"]
		if not outcomes:
			status = "success"
		elif all(o in ("created", "already_existed") for o in outcomes):
			status = "success"
		elif all(o == "failed" for o in outcomes):
			status = "failure"
		else:
			status = "partial_success"
		return {"company": company or COMPANY, "status": status, "rows": rows}

	return {
		"fetch_overdue_invoices_for": fetch_overdue_invoices_for,
		"deterministic_qualification_check": deterministic_qualification_check,
		"existing_followup_check": existing_followup_check,
		"create_todo": create_todo,
		"mark_row": mark_row,
		"compute_summary": compute_summary,
	}


TOOL_SCHEMAS: dict[str, dict] = {
	"fetch_overdue_invoices_for": {
		"type": "object",
		"properties": {"selected_customers": {"type": "array", "items": {"type": "string"}}, "company": {"type": "string"}},
		"required": ["selected_customers"],
	},
	"deterministic_qualification_check": {
		"type": "object",
		"properties": {"invoice": {"type": "string"}},
		"required": ["invoice"],
	},
	"existing_followup_check": {
		"type": "object",
		"properties": {
			"reference_type": {"type": "string"},
			"reference_name": {"type": "string"},
			"allocated_to": {"type": "string"},
		},
		"required": ["reference_type", "reference_name", "allocated_to"],
	},
	"create_todo": {
		"type": "object",
		"properties": {
			"reference_type": {"type": "string"},
			"reference_name": {"type": "string"},
			"allocated_to": {"type": "string"},
			"operation_key": {"type": "string"},
			"idempotency_key": {"type": "string"},
		},
		"required": ["reference_type", "reference_name", "allocated_to"],
	},
	"mark_row": {
		"type": "object",
		"properties": {
			"customer_id": {"type": "string"},
			"invoice": {"type": "string"},
			"qualifies": {"type": "boolean"},
			"created": {"type": "boolean"},
			"already_existed": {"type": "boolean"},
		},
		"required": ["customer_id", "invoice", "qualifies", "created", "already_existed"],
	},
	"compute_summary": {
		"type": "object",
		"properties": {"rows": {"type": "array"}, "company": {"type": "string"}},
		"required": ["rows"],
	},
}


def make_atomic_tools(store: FollowupStore, customers: list[str]) -> dict[str, AtomicTool]:
	fns = make_tool_functions(store, customers)
	tools: dict[str, AtomicTool] = {}
	for name, fn in fns.items():
		is_write = name == "create_todo"
		tools[name] = AtomicTool(
			name=name,
			fn=fn,
			is_write=is_write,
			description=("write: create a follow-up ToDo" if is_write else f"read/transform: {name}"),
			parameters=TOOL_SCHEMAS[name],
		)

	def _escalate(*, reason: str) -> dict:
		return {"escalated": True, "reason": reason}

	tools["escalate"] = AtomicTool(
		name="escalate",
		fn=_escalate,
		is_write=False,
		description="hand off to a human; ends the run",
		parameters={"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]},
	)
	return tools


def task_text(customers: list[str]) -> str:
	names = " and ".join(customers)
	return (
		f"Run collections follow-up for the {names} account(s) at {COMPANY}. "
		f"Find their overdue Sales Invoices, make sure a follow-up ToDo exists for each one "
		f"(assigned to {ALLOCATED_TO}), never create a duplicate ToDo for the same invoice, "
		f"record a per-invoice outcome, and give a final status."
	)


# ---------------------------------------------------------------------------
# Real HUF Procedure graph (same shape as real_procedure_integration.py /
# test_benchmark3_write_runtime.py's benchmark3 graph, trimmed to a single linear
# foreach body -- no branch-staleness trap needed here since qualification is
# unconditionally True in this seed data).
# ---------------------------------------------------------------------------


def build_followup_procedure_graph() -> dict:
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "fetch",
		"contract": {
			"input_schema": {},
			"output_schema": {},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": {
				"max_nodes": 200,
				"max_rows": 1000,
				"max_output_bytes": 1_000_000,
				"max_parallel_calls": 4,
				"max_foreach_iterations": 20,
				"max_external_calls": 100,
				"max_writes": 10,
				"max_wall_time_ms": 30_000,
				"fail_closed": True,
			},
		},
		"nodes": [
			{
				"id": "fetch",
				"type": "tool.call",
				"config": {
					"tool_id": "fetch_overdue_invoices_for",
					"input": {"selected_customers": {"$from": "input.selected_customers"}, "company": {"$from": "input.company"}},
				},
				"next": "loop",
			},
			{
				"id": "loop",
				"type": "foreach",
				"config": {
					"items": {"$from": "fetch"},
					"body": ["qualify", "existing_check", "create_todo", "verify", "finalize"],
					"collect": {"$from": "finalize"},
					"on_item_error": "fail",
				},
				"next": "summarize",
			},
			{
				"id": "qualify",
				"type": "tool.call",
				"config": {"tool_id": "deterministic_qualification_check", "input": {"invoice": {"$from": "foreach.item.invoice"}}},
				"next": "existing_check",
			},
			{
				"id": "existing_check",
				"type": "tool.call",
				"config": {
					"tool_id": "existing_followup_check",
					"input": {
						"reference_type": "Sales Invoice",
						"reference_name": {"$from": "foreach.item.invoice"},
						"allocated_to": {"$from": "input.allocated_to"},
					},
				},
				"next": "create_todo",
			},
			{
				"id": "create_todo",
				"type": "tool.call",
				"config": {
					"tool_id": "create_todo",
					"recovery": "resume",
					"input": {
						"reference_type": "Sales Invoice",
						"reference_name": {"$from": "foreach.item.invoice"},
						"allocated_to": {"$from": "input.allocated_to"},
						"operation_key": {"$from": "foreach.item.operation_key"},
						"idempotency_key": {"$from": "foreach.item.idempotency_key"},
						"skip_if_existing": {"$from": "existing_check.existing"},
					},
				},
				"next": "verify",
				"on_error": "finalize",
			},
			{
				"id": "verify",
				"type": "validate",
				"config": {
					"assertions": [
						{
							"expression": 'create_todo["created"] == True or create_todo["already_existed"] == True',
							"code": "NOT_VERIFIED",
							"message": "ToDo was neither created nor found already existing",
						}
					]
				},
				"next": "finalize",
				"on_error": "finalize",
			},
			{
				"id": "finalize",
				"type": "tool.call",
				"config": {
					"tool_id": "mark_row",
					"input": {
						"customer_id": {"$from": "foreach.item.customer_id"},
						"invoice": {"$from": "foreach.item.invoice"},
						"qualifies": {"$from": "qualify.qualifies"},
						"created": {"$from": "create_todo.created"},
						"already_existed": {"$from": "create_todo.already_existed"},
					},
				},
			},
			{
				"id": "summarize",
				"type": "tool.call",
				"config": {"tool_id": "compute_summary", "input": {"rows": {"$from": "loop"}, "company": {"$from": "input.company"}}},
				"next": "out",
			},
			{"id": "out", "type": "output", "config": {"value": {"$from": "summarize"}}},
		],
	}


@dataclass(frozen=True)
class _Perm:
	ptype: str


def classify_tool(tool_id: str):
	return _Perm("create" if tool_id == "create_todo" else "read")


def make_real_tool_invoker(store: FollowupStore, customers: list[str]):
	"""Real ``huf.ai.graph.procedure_runtime.ToolInvocation``-returning invoker, wrapping
	the SAME tool functions the naive arm calls -- ``execute_procedure`` is the REAL
	function from ``huf/ai/graph/procedure_runtime.py``, imported here, not mocked.
	"""
	from huf.ai.graph.procedure_runtime import ToolInvocation

	fns = make_tool_functions(store, customers)

	def _invoke(tool_id: str, args: dict) -> ToolInvocation:
		fn = fns.get(tool_id)
		if fn is None:
			return ToolInvocation(tool_id=tool_id, args=args, success=False, result=None, error=f"no such tool {tool_id!r}")
		try:
			result = fn(**args)
			return ToolInvocation(tool_id=tool_id, args=args, success=True, result=result, error=None)
		except Exception as exc:  # noqa: BLE001
			return ToolInvocation(tool_id=tool_id, args=args, success=False, result=None, error=str(exc))

	return _invoke


def run_real_procedure(customers: list[str], store: FollowupStore) -> dict:
	"""Zero-LLM real execution of the pinned graph -- the invariant this module measures
	against, not asserts: if this ever shows a nonzero model_step in the resulting log, the
	I4 invariant broke, which this module treats as a hard failure of the experiment, not a
	number to report.
	"""
	from huf.ai.graph.executor import PinnedVersion
	from huf.ai.graph.procedure_runtime import ProcedureOutcome, execute_procedure

	graph = build_followup_procedure_graph()
	version = PinnedVersion.pin(graph)
	invoker = make_real_tool_invoker(store, customers)

	outcome: ProcedureOutcome = execute_procedure(
		version,
		{"selected_customers": customers, "allocated_to": ALLOCATED_TO, "company": COMPANY},
		tool_invoker=invoker,
		run_id=f"{PROCEDURE_NAME}-{'-'.join(customers)}",
		classify_tool=classify_tool,
		procedure_name=PROCEDURE_NAME,
	)
	return {
		"status": outcome.status,
		"error": outcome.error,
		"output": outcome.output,
		"node_visits": outcome.node_visits,
		"tool_invocations": outcome.tool_invocations,
	}


# ---------------------------------------------------------------------------
# Correctness scoring -- SAME ground-truth check for both arms, against the real store
# state after the run (not against what either arm claims about itself).
# ---------------------------------------------------------------------------


def score_correctness(store_before: FollowupStore, store_after: FollowupStore, customers: list[str]) -> dict:
	expected_rows: list[tuple[str, str, str]] = []  # (customer, invoice, expected_outcome)
	for customer in customers:
		for invoice in SEED_INVOICES.get(customer, []):
			expected_rows.append((customer, invoice, expected_outcome_for(customer, invoice, store_before)))

	problems: list[str] = []
	seen_pairs: set[tuple[str, str]] = set()
	for row in store_after.rows:
		key = (row["reference_name"], row["allocated_to"])
		if key in seen_pairs:
			problems.append(f"duplicate ToDo row for {key}")
		seen_pairs.add(key)

	for customer, invoice, expected in expected_rows:
		found = store_after.find("Sales Invoice", invoice, ALLOCATED_TO)
		if found is None:
			problems.append(f"missing ToDo for {customer}/{invoice} (expected {expected})")

	# No ToDo for an invoice outside this instance's customer set should have been touched.
	untouched_before = {r["name"] for r in store_before.rows}
	for row in store_after.rows:
		if row["name"] in untouched_before:
			continue
		customer_of = None
		for c, invs in SEED_INVOICES.items():
			if row["reference_name"] in invs:
				customer_of = c
		if customer_of not in customers:
			problems.append(f"unexpected ToDo created for out-of-scope customer {customer_of}")

	return {"correct": not problems, "problems": problems, "expected_rows": expected_rows}


# ---------------------------------------------------------------------------
# Cost/latency accounting -- reuses recovery_harness's RunLog/pricing table unchanged.
# ---------------------------------------------------------------------------


@dataclass
class ModelCallRecord:
	label: str
	prompt_tokens: int
	completion_tokens: int
	cached_tokens: int
	wall_time_s: float
	model_id: str

	def cost_usd(self) -> float:
		pricing = MODEL_PRICING_USD_PER_MILLION_TOKENS.get(self.model_id)
		if pricing is None:
			raise KeyError(f"no pricing entry for model_id={self.model_id!r}")
		return compute_model_step_cost_usd(
			prompt_tokens=self.prompt_tokens,
			completion_tokens=self.completion_tokens,
			cached_tokens=self.cached_tokens,
			pricing=pricing,
		)


class RunningCostCeiling:
	"""A hard, in-process spend cap shared across every model call this module makes --
	raises rather than silently continuing once the ceiling is crossed."""

	def __init__(self, limit_usd: float) -> None:
		self.limit_usd = limit_usd
		self.spent_usd = 0.0

	def add(self, amount_usd: float) -> None:
		self.spent_usd += amount_usd
		if self.spent_usd > self.limit_usd:
			raise RuntimeError(f"cost ceiling exceeded: spent ${self.spent_usd:.4f} > limit ${self.limit_usd:.2f}")


def _family_for_model_id(model_id: str) -> str:
	if model_id.startswith("gemini"):
		return "gemini"
	if model_id.startswith("gpt") or model_id.startswith("o1") or model_id.startswith("o3"):
		return "openai"
	raise ValueError(f"unknown model family for model_id={model_id!r}")


def _sampling_for(role: str, model_id: str) -> SamplingConfig | None:
	"""Look up TEST_AGENT_SETTINGS.md's ``sampling:`` block for ``role``/``model_id``'s
	family. Returns ``None`` (send nothing, provider default) for a role that sheet
	deliberately leaves unset (e.g. one-off compilation calls it doesn't name a role for).
	"""
	per_family = ROLE_SAMPLING.get(role)
	if per_family is None:
		return None
	return per_family.get(_family_for_model_id(model_id))


def _one_shot_model_call(
	model_id: str, system: str, user_text: str, label: str, ceiling: RunningCostCeiling, *, role: str | None = None
) -> tuple[str, ModelCallRecord]:
	"""One real model call with no tools -- used for the Procedure arm's compile /
	interpret / final-response steps. Returns (response_text, record). ``role`` selects the
	named :class:`SamplingConfig` (``ROLE_SAMPLING``) sent explicitly on the request; omitted
	(``None``) sends nothing, matching provider defaults.
	"""
	sampling = _sampling_for(role, model_id) if role else None
	model = LiveAPIModel(model_id=model_id, tools={}, sampling=sampling)
	transcript = [{"role": "system", "content": system}, {"role": "user", "content": user_text}]
	start = time.monotonic()
	step = model.next_step(transcript=transcript, available_tools=[])
	wall = time.monotonic() - start
	record = ModelCallRecord(
		label=label,
		prompt_tokens=step.estimated_prompt_tokens,
		completion_tokens=step.estimated_completion_tokens,
		cached_tokens=step.estimated_cached_tokens,
		wall_time_s=wall,
		model_id=model_id,
	)
	ceiling.add(record.cost_usd())
	text = step.final_text or ""
	return text, record


def compile_procedure(model_id: str, ceiling: RunningCostCeiling) -> tuple[dict, ModelCallRecord]:
	"""One-time compilation-cost measurement: shown the task + the six tool schemas, asked
	to produce the ordered call plan a human reviewer would look at before pinning a
	Procedure version. The PINNED GRAPH ITSELF is the hand-authored
	``build_followup_procedure_graph`` (Procedures are never auto-activated from a model's
	own output -- I8) -- this call's tokens are what is charged as the one-time compile cost,
	its own output is not what gets executed.
	"""
	system = (
		"You design a deterministic execution plan (a Procedure) for a repeatable business "
		"task, to be reviewed by a human before being pinned and reused with zero further "
		"model involvement. Given the task and the available tools, output ONLY a JSON array "
		"of {tool, purpose} steps in call order. No prose."
	)
	user = (
		f"Task: {task_text(['CUST-0001', 'CUST-0002', 'CUST-0004', 'CUST-0006'])}\n\n"
		f"Available tools (name: schema):\n{json.dumps(TOOL_SCHEMAS, indent=2)}"
	)
	text, record = _one_shot_model_call(model_id, system, user, "compile", ceiling)
	return {"raw_text": text}, record


_INTERPRET_SYSTEM = (
	"You bind a user's natural-language request to the fixed input schema of an "
	"already-approved, pinned Procedure. Output ONLY a JSON object with keys "
	"selected_customers (array of strings), company (string), allocated_to (string). "
	"No prose."
)


def _validate_binding(parsed: dict, *, customers: list[str]) -> list[str]:
	"""Validate EVERY task-relevant input the interpretation step is supposed to bind, not
	just ``selected_customers`` (ACCEPTANCE_PLAN_V2.md Sec.5: "validate every task-relevant
	input, not just IDs"). Returns a list of problem strings; empty means the binding is
	usable as-is.
	"""
	problems: list[str] = []
	selected = parsed.get("selected_customers")
	if not isinstance(selected, list) or not all(isinstance(c, str) for c in selected):
		problems.append("selected_customers missing or not a list of strings")
	elif sorted(selected) != sorted(customers):
		problems.append(f"selected_customers {selected!r} != expected {customers!r}")
	company = parsed.get("company")
	if not isinstance(company, str) or not company.strip():
		problems.append("company missing or not a non-empty string")
	elif company != COMPANY:
		problems.append(f"company {company!r} != expected {COMPANY!r}")
	allocated_to = parsed.get("allocated_to")
	if not isinstance(allocated_to, str) or not allocated_to.strip():
		problems.append("allocated_to missing or not a non-empty string")
	elif allocated_to != ALLOCATED_TO:
		problems.append(f"allocated_to {allocated_to!r} != expected {ALLOCATED_TO!r}")
	return problems


def interpret_request(
	model_id: str, customers: list[str], ceiling: RunningCostCeiling
) -> tuple[dict, list[ModelCallRecord], list[str]]:
	"""Bind the NL request to the Procedure's input schema. NEVER substitutes ground-truth
	values on a parse/validation failure (ACCEPTANCE_PLAN_V2.md Sec.5 hard requirement,
	closing gap G6): a malformed or invalid binding gets exactly ONE logged, cost-included
	repair call (feeding the model the validation problems as feedback -- TEST_AGENT_SETTINGS.md
	Sec.4 "one logged, cost-included re-ask on a malformed binding"); if the repair also fails
	validation, the caller must treat this instance as a failure, never fall back silently.

	Returns ``(parsed_or_empty, [model_call_records], problems)``: ``problems`` is empty iff
	the (possibly repaired) binding is usable; every model call made -- including the repair
	attempt -- is in the returned list so its cost is always counted.
	"""
	user = task_text(customers)
	text, record = _one_shot_model_call(model_id, _INTERPRET_SYSTEM, user, "interpret", ceiling, role="procedure_interpretation_s5")
	records = [record]
	try:
		parsed = json.loads(text)
		if not isinstance(parsed, dict):
			parsed = {}
	except (json.JSONDecodeError, TypeError):
		parsed = {}

	problems = _validate_binding(parsed, customers=customers)
	if problems:
		# One logged, cost-included repair attempt -- never a ground-truth substitution.
		repair_user = (
			f"{user}\n\nYour previous JSON binding was invalid: {problems}. "
			"Re-emit ONLY a corrected JSON object with the same three keys."
		)
		repair_text, repair_record = _one_shot_model_call(
			model_id, _INTERPRET_SYSTEM, repair_user, "interpret_repair", ceiling, role="procedure_interpretation_s5"
		)
		records.append(repair_record)
		try:
			repaired = json.loads(repair_text)
			if not isinstance(repaired, dict):
				repaired = {}
		except (json.JSONDecodeError, TypeError):
			repaired = {}
		repair_problems = _validate_binding(repaired, customers=customers)
		if not repair_problems:
			return repaired, records, []
		# Repair also failed validation -- this instance is a failure, per Sec.5. The
		# original problems are returned (not the repair's -- the caller logs both via
		# ``extra``), and the parsed dict returned is whatever the repair attempt produced,
		# for forensic visibility only; the caller must NOT execute the Procedure against it.
		return repaired, records, problems + [f"repair also failed: {repair_problems}"]

	return parsed, records, []


def final_response(model_id: str, procedure_output: dict, ceiling: RunningCostCeiling) -> tuple[str, ModelCallRecord]:
	system = "You summarize a completed backend operation's structured result for the user, in 2-3 sentences. No JSON in your reply."
	user = f"Result: {json.dumps(procedure_output)}"
	text, record = _one_shot_model_call(model_id, system, user, "final_response", ceiling, role="final_report_s5")
	return text, record


# ---------------------------------------------------------------------------
# Per-instance run of each arm
# ---------------------------------------------------------------------------


@dataclass
class InstanceResult:
	arm: str  # "procedure" | "naive"
	model_id: str
	customers: list[str]
	model_calls: list[ModelCallRecord]
	wall_time_s: float
	correctness: dict
	real_accounting: bool  # marker: were these real (non-mock) provider calls
	extra: dict = field(default_factory=dict)

	def total_tokens(self) -> dict:
		return {
			"prompt_tokens": sum(c.prompt_tokens for c in self.model_calls),
			"completion_tokens": sum(c.completion_tokens for c in self.model_calls),
			"cached_tokens": sum(c.cached_tokens for c in self.model_calls),
		}

	def total_cost_usd(self) -> float:
		return sum(c.cost_usd() for c in self.model_calls)

	def to_jsonable(self) -> dict:
		return {
			"arm": self.arm,
			"model_id": self.model_id,
			"customers": self.customers,
			"model_call_count": len(self.model_calls),
			"model_calls": [
				{
					"label": c.label,
					"prompt_tokens": c.prompt_tokens,
					"completion_tokens": c.completion_tokens,
					"cached_tokens": c.cached_tokens,
					"wall_time_s": c.wall_time_s,
					"cost_usd": c.cost_usd(),
				}
				for c in self.model_calls
			],
			"total_tokens": self.total_tokens(),
			"total_cost_usd": self.total_cost_usd(),
			"wall_time_s": self.wall_time_s,
			"correctness": self.correctness,
			"real_accounting": self.real_accounting,
			"extra": self.extra,
		}


def run_naive_instance(model_id: str, customers: list[str], ceiling: RunningCostCeiling) -> InstanceResult:
	store = FollowupStore()
	store_before = copy.deepcopy(store)
	tools = make_atomic_tools(store, customers)
	model = LiveAPIModel(model_id=model_id, tools=tools, sampling=_sampling_for("naive_agent_loop_s5", model_id))

	start = time.monotonic()
	log: RunLog = run_recovery(
		condition="C1",
		model=model,
		tools=tools,
		context=task_text(customers),
		store=store,
		# TEST_AGENT_SETTINGS.md Sec.4(a): naive arm gets 40 tool calls (not the harness
		# default of 20) so a careful-but-slower model on the 2-customer instance isn't
		# turned into a budget failure. Each while-loop iteration in run_recovery is one
		# model call, so this also bounds model calls well under the 25-model-call budget
		# for a task this size (at most ~a dozen invoices/tool ops across both customers).
		max_tool_calls=40,
	)
	wall = time.monotonic() - start

	model_calls = [
		ModelCallRecord(
			label="naive_step",
			prompt_tokens=e.prompt_tokens,
			completion_tokens=e.completion_tokens,
			cached_tokens=e.cached_tokens,
			wall_time_s=e.wall_time_s,
			model_id=model_id,
		)
		for e in log.entries
		if e.kind == "model_step"
	]
	for c in model_calls:
		ceiling.add(c.cost_usd())

	correctness = score_correctness(store_before, store, customers)

	# Sec.5 hard requirement / G2 evidence: record, per model turn, how many tool calls the
	# provider actually returned vs how many the harness dispatched, so a batched turn (>1
	# call in one response) is visible in the dataset rather than only in code inspection.
	per_turn_dispatch: list[dict] = []
	last_returned = None
	for e in log.entries:
		if e.kind == "model_step":
			last_returned = (e.content or {}).get("tool_calls_returned")
		elif e.kind == "tool_calls_dispatched":
			per_turn_dispatch.append(
				{
					"tool_calls_returned": last_returned,
					"tool_calls_dispatched": (e.content or {}).get("count"),
				}
			)
	max_calls_in_one_turn = max((d["tool_calls_returned"] or 0) for d in per_turn_dispatch) if per_turn_dispatch else 0

	return InstanceResult(
		arm="naive",
		model_id=model_id,
		customers=customers,
		model_calls=model_calls,
		wall_time_s=wall,
		correctness=correctness,
		# NOTE: RunLog.tokens_are_estimated is a stale field never flipped to False anywhere
		# in this codebase (verified: no assignment site outside its own dataclass default),
		# so it cannot be used to distinguish a real run from a MockedModel run. The real
		# marker used here instead is the model object's own type -- LiveAPIModel is the
		# only RecoveryModel implementation in this codebase that ever calls a real
		# provider; MockedModel always reports zero tokens (see its own docstring).
		real_accounting=isinstance(model, LiveAPIModel),
		extra={
			"outcome": log.outcome,
			"tool_call_count": log.tool_call_count,
			"per_turn_dispatch": per_turn_dispatch,
			"max_tool_calls_in_one_turn": max_calls_in_one_turn,
		},
	)


def run_procedure_instance(model_id: str, customers: list[str], ceiling: RunningCostCeiling) -> InstanceResult:
	store = FollowupStore()
	store_before = copy.deepcopy(store)

	start = time.monotonic()
	bound, interp_records, problems = interpret_request(model_id, customers, ceiling)

	if problems:
		# Sec.5 hard requirement (G6): a parse/validation failure that survives the one
		# logged repair call is a TASK FAILURE -- never a silent substitution of the
		# ground-truth customer set. The Procedure is never executed against an unvalidated
		# binding; only the interpretation (+ repair) calls' real cost is counted.
		wall = time.monotonic() - start
		correctness = {"correct": False, "problems": [f"interpretation binding failed validation: {problems}"]}
		return InstanceResult(
			arm="procedure",
			model_id=model_id,
			customers=customers,
			model_calls=list(interp_records),
			wall_time_s=wall,
			correctness=correctness,
			real_accounting=True,
			extra={
				"procedure_status": "NOT_EXECUTED_INVALID_BINDING",
				"procedure_error": None,
				"graph_provenance": "hand-authored",
			},
		)

	bound_customers = bound["selected_customers"]
	exec_result = run_real_procedure(bound_customers, store)
	_summary_text, final_record = final_response(model_id, exec_result.get("output") or {}, ceiling)
	wall = time.monotonic() - start

	correctness = score_correctness(store_before, store, customers)

	return InstanceResult(
		arm="procedure",
		model_id=model_id,
		customers=customers,
		model_calls=[*interp_records, final_record],
		wall_time_s=wall,
		correctness=correctness,
		real_accounting=True,
		extra={
			"procedure_status": exec_result["status"],
			"procedure_error": exec_result["error"],
			# §5: "honestly label the graph as hand-authored or compiler-produced" -- the
			# pinned graph this instance actually executed comes from
			# build_followup_procedure_graph(), which is hand-authored, never the discarded
			# compile_procedure() model output (that call, when it runs at all, is logged
			# separately as one-time "compilation"/plan-generation cost -- see run_experiment).
			"graph_provenance": "hand-authored",
			"repair_call_used": len(interp_records) > 1,
		},
	)


# ---------------------------------------------------------------------------
# Top-level experiment driver
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _model_id_for_family(family: str) -> str:
	if family == "gemini":
		return "gemini-3.5-flash-lite"
	if family == "openai":
		return "gpt-4o-mini"
	raise ValueError(f"unknown model family {family!r}")


def _require_key_for(model_id: str) -> None:
	if model_id.startswith("gemini") or "gemini" in model_id:
		if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
			raise RuntimeError(f"no GOOGLE_API_KEY/GEMINI_API_KEY in environment for model_id={model_id!r}")
	elif model_id.startswith("gpt") or model_id.startswith("o1") or model_id.startswith("o3"):
		if not os.environ.get("OPENAI_API_KEY"):
			raise RuntimeError(f"no OPENAI_API_KEY in environment for model_id={model_id!r}")


def run_experiment(*, families: list[str], budget_usd: float = 5.0, out_path: Path | None = None) -> dict:
	ceiling = RunningCostCeiling(budget_usd)
	all_results: list[InstanceResult] = []
	compilation_records: dict[str, ModelCallRecord] = {}

	for family in families:
		model_id = _model_id_for_family(family)
		_require_key_for(model_id)

		_compile_plan, compile_record = compile_procedure(model_id, ceiling)
		compilation_records[model_id] = compile_record

		for idx, customers in enumerate(TASK_INSTANCES, start=1):
			# §5 ordering requirement: alternate which arm goes first per instance (odd
			# instances Procedure first, even instances naive first) to reduce timing bias --
			# this driver previously always ran Procedure first for every instance.
			if idx % 2 == 1:
				all_results.append(run_procedure_instance(model_id, customers, ceiling))
				all_results.append(run_naive_instance(model_id, customers, ceiling))
			else:
				all_results.append(run_naive_instance(model_id, customers, ceiling))
				all_results.append(run_procedure_instance(model_id, customers, ceiling))

	out_path = out_path or (RESULTS_DIR / "procedure_vs_naive_runs.jsonl")
	out_path.parent.mkdir(parents=True, exist_ok=True)
	with out_path.open("w", encoding="utf-8") as fh:
		for model_id, rec in compilation_records.items():
			fh.write(
				json.dumps(
					{
						"kind": "compilation",
						"model_id": model_id,
						"prompt_tokens": rec.prompt_tokens,
						"completion_tokens": rec.completion_tokens,
						"cached_tokens": rec.cached_tokens,
						"wall_time_s": rec.wall_time_s,
						"cost_usd": rec.cost_usd(),
						"real_accounting": True,
					}
				)
				+ "\n"
			)
		for r in all_results:
			fh.write(json.dumps({"kind": "instance", **r.to_jsonable()}) + "\n")

	return {
		"compilation_records": compilation_records,
		"instance_results": all_results,
		"total_spent_usd": ceiling.spent_usd,
		"out_path": str(out_path),
	}


def main() -> int:
	families = os.environ.get("PVN_FAMILIES", "gemini,openai").split(",")
	families = [f.strip() for f in families if f.strip()]
	budget = float(os.environ.get("PVN_BUDGET_USD", "5.0"))
	result = run_experiment(families=families, budget_usd=budget)
	print(f"wrote {result['out_path']}; total spend ${result['total_spent_usd']:.4f}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
