"""Permission-first tool selection adapter for the Decision Runtime."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from huf.ai.decision.candidates import constrain_selected_tool, get_tool_candidates
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionRequest, DecisionResponse, DecisionStatus, QuestionKind


def select_authorized_tool(
	runtime: DecisionRuntime,
	request: DecisionRequest,
	backend: Any | str,
	allowed_tools: Iterable[Any],
) -> tuple[str | None, DecisionResponse]:
	"""Shortlist an authorized tool, then re-check authorization after selection.

	``allowed_tools`` must already come from the permission-aware registry. The runtime
	never receives raw Agent configuration or caller-supplied candidates.
	"""
	candidates = get_tool_candidates(allowed_tools)
	if not candidates:
		return None, DecisionResponse(status=DecisionStatus.UNAVAILABLE, identity=request.identity)
	request = replace(
		request,
		candidates=candidates,
		candidate_source=CandidateSource.AUTHORITATIVE_RESOLVER,
		candidate_resolver_id="permission_aware_tool_registry",
	)
	response = runtime.evaluate(request, backend)
	if response.status != DecisionStatus.SUCCESS:
		return None, response
	for answer in response.answers.values():
		if answer.kind != QuestionKind.SELECT:
			continue
		selected = answer.value if isinstance(answer.value, str) else None
		return constrain_selected_tool(selected or "", allowed_tools), response
	return None, response
