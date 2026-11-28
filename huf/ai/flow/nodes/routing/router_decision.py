"""``router.decision`` node, Decision mode: ask the Decision runtime which candidate node comes next.

Config ``decision`` (when absent the node keeps its rule mode, see ``nodes/routing/switch.py``)::

    {
        "candidates": [{"node_id": "billing", "label": "Billing question"}, ...],  # two or more
        "instructions": "Pick the team that should handle this message",
        "minimum_confidence": 0.7,           # optional
        "uncertain_next": "review",          # taken on any doubt or failure
        "backend": "fake",                   # registered Decision backend id
        "state": {...},                      # optional JSON state for the backend
    }

Every failure routes to ``uncertain_next`` with a reason; routing never sends (G5). The AI kill switch
(``huf.ai.run_budget.assert_ai_enabled``) and the current run budget's deadline are checked before the
backend is called, so a disabled site or an expired run never reaches a provider.
"""

from __future__ import annotations

from typing import Any

from huf.ai.decision.flow_router import resolve_decision_route
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import (
	CandidateSource,
	DecisionPolicy,
	DecisionRequest,
	Option,
	Question,
	QuestionKind,
	StateBinding,
)

QUESTION_ID = "route"


def uses_decision(config: dict) -> bool:
	"""A ``router.decision`` node runs in Decision mode only when it configures ``decision``."""
	return isinstance((config or {}).get("decision"), dict)


def exec_router_decision(flow_run, node: dict, config: dict, settings: dict, context=None, *, backend: Any = None) -> dict:
	"""Run the Decision mode when configured, else the rule mode (``exec_switch``)."""
	if not uses_decision(config):
		from huf.ai.flow.nodes.routing.switch import exec_switch

		return exec_switch(flow_run, node, config, settings, context)
	return exec_decision_route(config["decision"], backend=backend)


def exec_decision_route(decision: dict, *, backend: Any = None, runtime: DecisionRuntime | None = None) -> dict:
	uncertain_next = decision.get("uncertain_next")
	if not uncertain_next:
		return {"status": "failed", "error": "Choose which path to take when the decision is uncertain, then run again."}
	candidates = _candidates(decision)
	if len(candidates) < 2:
		return {"status": "failed", "error": "Add at least two paths for the decision to choose from, then run again."}

	blocked = _ai_blocked()
	if blocked:
		return _uncertain(uncertain_next, blocked)

	try:
		request = _request(decision, candidates)
	except (TypeError, ValueError):
		return _uncertain(uncertain_next, "decision_config_invalid")
	response = (runtime or DecisionRuntime()).evaluate(request, backend or decision.get("backend") or "")
	route = resolve_decision_route(
		response,
		candidate_node_ids={c["node_id"] for c in candidates},
		uncertain_next=uncertain_next,
		minimum_confidence=_confidence(decision.get("minimum_confidence")),
	)
	return _result(route)


def _ai_blocked() -> str | None:
	"""Reason code when AI must not run now: kill switch off, or the run budget's deadline passed."""
	from huf.ai.run_budget import (
		AI_DISABLED,
		AIDisabled,
		RunBudgetExceeded,
		assert_ai_enabled,
		peek_current_budget,
	)

	try:
		assert_ai_enabled()
	except AIDisabled:
		return AI_DISABLED
	except Exception:  # noqa: BLE001 - a kill switch must not fail open
		return AI_DISABLED
	budget = peek_current_budget()
	if budget is not None:
		try:
			budget.check_deadline()
		except AIDisabled:
			return AI_DISABLED
		except RunBudgetExceeded:
			return "budget_exceeded"
	return None


def _candidates(decision: dict) -> list[dict]:
	seen, out = set(), []
	for item in decision.get("candidates") or []:
		if not isinstance(item, dict) or not isinstance(item.get("node_id"), str) or not item["node_id"]:
			continue
		if item["node_id"] in seen:
			continue
		seen.add(item["node_id"])
		out.append({"node_id": item["node_id"], "label": str(item.get("label") or item["node_id"])})
	return out


def _request(decision: dict, candidates: list[dict]) -> DecisionRequest:
	question = Question(
		id=QUESTION_ID,
		kind=QuestionKind.SELECT,
		instructions=str(decision.get("instructions") or "Choose the best next step"),
		options=tuple(Option(c["node_id"], c["label"]) for c in candidates),
	)
	policy = DecisionPolicy(
		policy_id=str(decision.get("policy_id") or "flow-router"),
		questions=(question,),
		state_bindings=(StateBinding("request", "$"),),
	)
	return DecisionRequest(
		policy=policy,
		state=decision.get("state") or {},
		surface="flow.router",
		candidate_source=CandidateSource.POLICY_OPTIONS,
	)


def _confidence(value) -> float | None:
	try:
		return None if value in (None, "") else float(value)
	except (TypeError, ValueError):
		return None


def _uncertain(next_node_id: str, reason: str) -> dict:
	return _result({"status": "uncertain", "next_node_id": next_node_id, "reason": reason})


def _result(route: dict) -> dict:
	return {
		"status": "success",
		"next_node_id": route["next_node_id"],
		"output": {"decision": route["status"], "reason": route["reason"], "node_id": route["next_node_id"]},
	}
