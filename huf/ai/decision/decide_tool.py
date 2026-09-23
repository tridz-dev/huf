"""``decide`` tool -- the Agent Tool surface (D9, PLAN.md §3.6, §4.7).

The model can ask a bound ``Decision Policy`` a question mid-run, unlike every other
surface (Tool/Skill/Procedure Selection, Model Routing, RAG Filter, ...) where HUF's own
resolver decides when and what to ask. Because the caller is the model itself, this
surface is the sharpest governance edge in the programme (D9): the tool may only invoke a
policy the Agent's owner explicitly bound to it, only with a candidate set that is
validated (never widened) against what that policy declares, and its result is always
advisory -- it has no side effects and is never used to decide permissions.

This module holds the surface-specific logic (which policies are bound, request shaping,
response mapping); the model-facing ``@function_tool`` wrapper lives in
``agent_integration.py`` (``AgentManager._setup_tools``), which is also where the
registration gate -- an enabled binding *and* the site kill switch -- lives, so an agent
run with neither pays no import/query cost for this module at all.

Contract (mirrors ``huf.ai.decision.agent_surfaces`` but does NOT use
``decide_for_surface``'s narrowing -- I-DR1 there assumes HUF resolved the candidates;
here the model did, so this module is the one place a model-declared id becomes a
``huf.ai.decision.types.Option``):

- Registered only for policies bound via an enabled ``Agent Decision Binding`` row with
  ``surface="Agent Tool"`` and effective mode ``Enforce`` or ``Shadow``. ``Off`` bindings
  are excluded by definition; ``Advise`` is not a valid mode for this surface (it is not
  in ``huf.ai.decision.binding.ADVISE_SURFACES``) -- ``Agent.validate`` (T1.22) rejects it
  at save time, and :func:`_effective_binding_mode` re-applies the same downgrade here as a
  second, defensive check (mirroring ``resolve_agent_decision_binding``'s own rule) so a
  binding that reached this code some other way can never grant Advise on this surface.
- ``policy`` (the tool argument) must be one of the bound names; an unbound name is an
  *error result* with no call into ``service.run_policy`` at all (never a Python exception
  reaching the model).
- A policy with a ``select`` question expects the model to supply the live candidate set
  through the tool's ``candidates`` argument (this policy "takes runtime candidates"):
  those are capped by ``Decision Policy.max_candidates`` (0/unset = no limit) and must be
  non-empty after capping, or the call is an error result with no service call. A policy
  with only ``judge``/``score`` questions has nothing for the model to choose between --
  it "declares fixed options" -- so whatever ``candidates`` the model passed is ignored.
- Enforce: the mapped ``{answer, confidence, status}`` (plus an advisory note) is returned
  to the model. On any non-``success`` :class:`~huf.ai.decision.types.ServiceResult`
  (``disabled``, ``budget_exceeded``, ``timeout``, a backend failure, ...) the tool returns
  ``{"status": "unavailable", "answer": None}`` (PLAN.md §3.6 Agent Tool fallback column) --
  never the raw status/error text, which may carry backend detail not meant for the model.
- Shadow: the call still runs (through ``service.run_policy(..., mode="Shadow")``, which
  enqueues the shadow job and returns immediately) so it is logged, but the model always
  receives ``{"status": "shadow", "answer": None}`` regardless of what (if anything) the
  service call returns -- the whole point of Shadow is that the answer never reaches or
  influences the model.
- Output is advisory only: the tool has no side effects and its description (set in
  ``agent_integration.py``) says so; nothing here writes to any document or changes what
  other tools the model can call.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

import frappe

from huf.ai.decision import service
from huf.ai.decision.binding import ADVISE_SURFACES
from huf.ai.decision.types import CandidateSource, DecisionOrigin, DecisionStatus, Option, QuestionKind

SURFACE = "Agent Tool"

#: Advisory note returned with every successful answer -- the tool result is a suggestion,
#: never an instruction and never a permission grant (D9).
ADVISORY_NOTE = (
	"This is an advisory decision suggestion, not an instruction. It grants no permission "
	"and has no side effects; use your own judgement about whether and how to act on it."
)


class BoundPolicy(NamedTuple):
	"""One resolved ``Agent Tool`` binding, keyed by policy name."""

	policy: str
	mode: str  # "Enforce" or "Shadow" -- Off/Advise are never bound (see module docstring)
	latency_budget_ms: int | None


def _effective_binding_mode(binding: Any) -> str:
	"""Same Off/Advise downgrade rule as ``binding.resolve_agent_decision_binding``.

	Kept local (rather than imported) because that function resolves a *single* highest
	priority binding for a surface; the ``decide`` tool needs every bound policy name, not
	just one, so it scans ``decision_bindings`` itself and reuses only the mode rule.
	"""
	mode = getattr(binding, "mode", "Off") or "Off"
	if mode == "Advise" and SURFACE not in ADVISE_SURFACES:
		mode = "Off"
	return mode


def get_agent_tool_bindings(agent_doc: Any) -> dict[str, BoundPolicy]:
	"""Return every enabled ``Agent Tool`` binding in Enforce/Shadow, keyed by policy name.

	Never widens: rows with ``surface`` != ``"Agent Tool"``, ``enabled`` false, an empty
	``policy``, or an effective mode of Off (including Advise downgraded to Off) are
	dropped. When more than one enabled row names the same policy, the lowest ``priority``
	value wins (ties broken by leaving the first one seen), matching
	``resolve_agent_decision_binding``'s ordering.
	"""
	bindings = getattr(agent_doc, "decision_bindings", None) or ()
	resolved: dict[str, tuple[BoundPolicy, int]] = {}
	for binding in bindings:
		if not getattr(binding, "enabled", True):
			continue
		if getattr(binding, "surface", None) != SURFACE:
			continue
		mode = _effective_binding_mode(binding)
		if mode not in ("Enforce", "Shadow"):
			continue
		policy = getattr(binding, "policy", None)
		if not isinstance(policy, str) or not policy.strip():
			continue
		priority = max(0, int(getattr(binding, "priority", 100) or 0))
		existing = resolved.get(policy)
		if existing is None or priority < existing[1]:
			resolved[policy] = (
				BoundPolicy(
					policy=policy,
					mode=mode,
					latency_budget_ms=getattr(binding, "latency_budget_ms", None),
				),
				priority,
			)
	return {name: value[0] for name, value in resolved.items()}


def has_agent_tool_binding(agent_doc: Any) -> bool:
	"""True when the Agent has at least one policy the ``decide`` tool could call."""
	return bool(get_agent_tool_bindings(agent_doc))


def kill_switch_enabled() -> bool:
	"""``Agent Settings.decision_runtime_enabled`` (D12) -- same read ``service.run_policy``

	makes for the same setting; duplicated here (rather than imported) because the
	registration gate in ``agent_integration.py`` must decide *before* any policy/service
	call whether to build the tool at all, and importing ``service`` there is otherwise
	unnecessary for that decision.
	"""
	return bool(frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled"))


def decide_tool_enabled(agent_doc: Any) -> bool:
	"""Registration gate for ``agent_integration.py``: a bound policy AND the kill switch on."""
	return kill_switch_enabled() and has_agent_tool_binding(agent_doc)


class _PolicyShape(NamedTuple):
	takes_candidates: bool
	max_candidates: int  # 0 = no limit


def _policy_shape(policy_name: str) -> _PolicyShape:
	"""Whether a bound policy needs the model to supply candidates, and its cap.

	A ``select`` question is the only primitive that chooses among a candidate set,
	so a policy with one expects the model to pass ``candidates``; a policy with only
	``judge``/``score`` questions has nothing to choose between and "declares fixed
	options" (PLAN.md §3.6) -- whatever the model passes is ignored. Reads the same
	published ``Decision Policy Version`` ``service.run_policy`` would resolve, so this
	never disagrees with what the actual call does.
	"""
	from huf.ai.decision.policy import validate_policy_data

	policy_doc = frappe.get_cached_doc("Decision Policy", policy_name)
	version_name = policy_doc.current_version
	if not version_name:
		raise ValueError(f"Decision Policy {policy_name!r} has no published version")
	version_doc = frappe.get_cached_doc("Decision Policy Version", version_name)
	parsed = validate_policy_data(json.loads(version_doc.definition_json))
	takes_candidates = any(question.kind == QuestionKind.SELECT for question in parsed.questions)
	max_candidates = max(0, int(getattr(policy_doc, "max_candidates", 0) or 0))
	return _PolicyShape(takes_candidates=takes_candidates, max_candidates=max_candidates)


def _coerce_candidates(raw_candidates: Any) -> tuple[Option, ...]:
	if not raw_candidates:
		return ()
	options = []
	for item in raw_candidates:
		if isinstance(item, Option):
			options.append(item)
			continue
		if not isinstance(item, dict):
			raise ValueError("each candidate must be an object with an 'id'")
		candidate_id = item.get("id")
		if not isinstance(candidate_id, str) or not candidate_id.strip():
			raise ValueError("each candidate requires a non-empty string 'id'")
		description = item.get("description") or ""
		options.append(Option(candidate_id, str(description)))
	return tuple(options)


def _error(message: str) -> dict:
	return {"status": "error", "answer": None, "confidence": None, "error": message}


def run_decide(
	agent_doc: Any,
	*,
	policy: str,
	state: str,
	candidates: Any = None,
	origin: DecisionOrigin,
) -> dict:
	"""Core ``decide`` tool logic. Never raises -- always returns a model-safe dict.

	Called by the ``@function_tool``-wrapped closure in ``agent_integration.py`` with the
	Agent's own document and a :class:`DecisionOrigin` built from the current run/
	conversation, so this function stays pure Frappe-doc-in/dict-out and is easy to unit
	test without a live agent run.
	"""
	bound = get_agent_tool_bindings(agent_doc).get(policy)
	if bound is None:
		return _error(f"{policy!r} is not a policy bound to this Agent's decide tool.")

	try:
		shape = _policy_shape(policy)
	except Exception as exc:  # policy row/version missing or malformed -- never leak detail
		frappe.logger("huf").warning(f"decide tool: failed to read policy shape for {policy!r}: {exc!s}")
		return _error("policy definition could not be read")

	request_candidates: tuple[Option, ...] = ()
	candidate_source: CandidateSource | None = None
	if shape.takes_candidates:
		try:
			request_candidates = _coerce_candidates(candidates)
		except ValueError as exc:
			return _error(str(exc))
		if shape.max_candidates:
			request_candidates = request_candidates[: shape.max_candidates]
		if not request_candidates:
			return _error("this policy requires a non-empty 'candidates' list")
		candidate_source = CandidateSource.MODEL_SUPPLIED_CANDIDATES
	# else: fixed-option policy -- candidates ignored regardless of what was passed.

	result = service.run_policy(
		policy=policy,
		state=state,
		candidates=request_candidates,
		candidate_source=candidate_source,
		candidate_resolver_id="decide_tool" if candidate_source is not None else None,
		mode=bound.mode,
		surface=SURFACE,
		origin=origin,
		latency_budget_ms=bound.latency_budget_ms,
	)

	if bound.mode == "Shadow":
		# Logged via the shadow job; the model never sees the answer (D9/D14).
		return {"status": "shadow", "answer": None}

	response = result.response
	if response is None or response.status != DecisionStatus.SUCCESS:
		return {"status": "unavailable", "answer": None}

	answers = {
		question_id: {"value": answer.value, "confidence": answer.confidence}
		for question_id, answer in response.answers.items()
	}
	if len(answers) == 1:
		((_, only),) = answers.items()
		answer_value, confidence = only["value"], only["confidence"]
	else:
		answer_value, confidence = answers, None

	return {
		"status": "success",
		"answer": answer_value,
		"confidence": confidence,
		"note": ADVISORY_NOTE,
	}
