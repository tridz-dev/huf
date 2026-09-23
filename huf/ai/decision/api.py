"""Whitelisted HTTP API for the Decision Runtime (PLAN.md §4.8, PR 2A).

Every function here is ``@frappe.whitelist()`` and capability-checked with
``huf.permissions.has_capability`` -- no DocType-permission-only endpoint. This is the
surface ``frontend/src/api/decisionApi.ts`` (not yet written) and the public API (PLAN.md
§3.12) both call; nothing else in HUF should construct a ``Decision Call`` query or call
``huf.ai.decision.service.run_policy`` directly on a caller's behalf.

Capabilities (PLAN.md §3.17):
    decision.run    -- run published policies (Playground/API), list/see own-origin calls.
    decision.author -- author/validate ad-hoc policy definitions, publish policy versions
                       is *not* included (that is decision.admin, PLAN.md §5.2 placement
                       table: "publish/retire policies" -> decision.admin).
    decision.admin  -- everything decision.author can plus pin a deployment, see all
                       Decision Calls regardless of origin, see raw/state fields on a call,
                       publish policy versions, see disabled/all Decision Models and their
                       deployments.

PR 9 hardens external-API auth: per-``Decision Policy`` ``allow_api_access`` opt-in and a
``@rate_limit`` decorator on ``run_decision`` (pattern at ``agent_integration.py:1153``,
PLAN.md §3.12). Neither is implemented here -- ``run_decision`` below is left as a plain
``@frappe.whitelist()`` (HUF's normal session/API-key auth applies, D17) with a NOTE(PR 9
hook) marking exactly where the opt-in check and the rate-limit decorator belong.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from huf.ai.decision import service
from huf.ai.decision.errors import DecisionError
from huf.ai.decision.policy import validate_policy_data
from huf.ai.decision.types import CandidateSource, DecisionOrigin, Option
from huf.permissions import has_capability

# -- Shared helpers ------------------------------------------------------------------------


def _require(capability: str) -> None:
	"""Throw a PermissionError unless the current session user holds ``capability``."""
	if not has_capability(frappe.session.user, capability):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _is_admin(user: str | None = None) -> bool:
	return has_capability(user or frappe.session.user, "decision.admin")


def _json_arg(value: Any) -> Any:
	"""Decode a JSON-string argument (how dict/list kwargs usually arrive over HTTP).

	Matches the existing convention (e.g. ``huf/ai/flow_api.py``:
	``json.loads(x) if isinstance(x, str) else x``) -- a caller that already passed a
	dict/list (Desk JS, or a Python test calling the function directly) is left alone.
	"""
	if isinstance(value, str):
		stripped = value.strip()
		if not stripped:
			return None
		return json.loads(stripped)
	return value


# -- run_decision ----------------------------------------------------------------------------


@frappe.whitelist()
def run_decision(
	policy: str | None = None,
	definition: Any = None,
	decision_model: str | None = None,
	state: Any = None,
	candidates: Any = None,
	candidate_source: str | None = None,
	candidate_resolver_id: str | None = None,
	policy_version: str | None = None,
	pinned_deployment: str | None = None,
	latency_budget_ms: int | None = None,
	surface: str | None = None,
	origin_type: str = "Playground",
) -> dict:
	"""Run one decision for the Playground or a public-API caller.

	Thin, capability-checked wrapper around ``huf.ai.decision.service.run_policy`` --
	always ``mode="Manual"`` (the label the Playground/API path uses, PLAN.md §4.7 point
	4/service.py docstring) and always ``origin.owner_user = frappe.session.user``. Advise
	is never offered here (D18: "Not offered for ... the public API: the UI hides it and
	the server rejects it") -- there is no ``mode`` parameter at all, so a caller cannot
	even ask for it.

	Args:
		policy: ``Decision Policy`` docname. Mutually exclusive with ``definition``. Runs
			the resolved published version (or ``policy_version`` if pinned). Requires
			``decision.run``.
		definition: Ad-hoc policy JSON (mapping, or a JSON string -- see ``_json_arg``) in
			the shape ``huf.ai.decision.policy.validate_policy_data`` accepts. Mutually
			exclusive with ``policy``. Requires ``decision.author`` in addition to
			``decision.run`` (PLAN.md §3.5 "Permissions": "decision.run for published
			policies and ad-hoc" is the Playground copy, but ad-hoc authoring itself is
			gated by ``decision.author`` everywhere else in the plan -- §3.17's grants row
			for ``decision.author`` is "Playground with ad-hoc"; ``decision.run`` alone
			only ever names "published policies").
		decision_model: ``Decision Model`` docname. Required with ``definition``; optional
			override with ``policy``.
		state: Opaque provider-visible state (text or JSON), passed through unchanged.
		candidates: Closed candidate/option list for select/score questions -- a JSON
			string or list of ``{"id": ..., "description": ...}`` mappings.
		candidate_source: One of ``huf.ai.decision.types.CandidateSource`` values, required
			whenever ``candidates`` is non-empty and a select question is present.
		candidate_resolver_id: Declared provenance detail alongside ``candidate_source``.
		policy_version: Explicit ``Decision Policy Version`` docname (D10 pinning).
			Requires ``policy``.
		pinned_deployment: Narrow the chain to one ``Decision Deployment``. Requires
			``decision.admin`` (PLAN.md §3.5: "ad-hoc against a pinned deployment requires
			decision.admin" -- applied here to any pin, ad-hoc or not, since pinning a
			deployment is an admin-level override of the normal failover chain either way).
		latency_budget_ms: Overrides the surface default deadline.
		surface: Passed straight through to ``run_policy`` for its latency-budget lookup
			and telemetry (``Decision Call.surface``). Defaults to ``"API"`` when
			``origin_type == "API"``, else ``"Playground"`` -- there is no
			``Agent Decision Binding`` surface for a Manual call, so this is a free-form
			label, not one of the ``ADVISE_SURFACES``/latency-table names (Manual can never
			hit the Advise check, D18/§4.7 point 4).
		origin_type: ``"Playground"`` or ``"API"`` (``Decision Call.origin_type`` Select
			options that have no other required origin field, decision_call.json).

	Returns:
		JSON-safe dict: ``{"status", "decision_call", "fallback_action", "response"}``.
		``response`` mirrors ``ServiceResult.response`` (``DecisionResponse``) with answers,
		probabilities, confidence, gate result, resolved identity (provider / deployment /
		provider model id), failover chain, latency, tokens, cost -- everything PLAN.md
		§3.5 point 5 lists for the Playground result panel. Each answer's
		``backend_metadata`` (the closest thing to a "raw backend payload" that reaches
		this module -- see the persisted ``Decision Call.answer_json`` note in
		``huf.ai.decision.persistence``) is included only when the caller holds
		``decision.admin`` (PLAN.md §3.5: "Raw response (Advanced) only with
		decision.admin").

	Raises:
		frappe.PermissionError: missing ``decision.run`` (always required), missing
			``decision.author`` (ad-hoc ``definition``), or missing ``decision.admin``
			(``pinned_deployment``).
		frappe.ValidationError: bad ``origin_type``.
		ValueError: bad call shape, propagated from ``run_policy`` (both/neither of
			``policy``/``definition``, missing ``decision_model`` for ad-hoc, unresolvable
			policy/version/model, bad ``candidates``/``candidate_source`` shape).
	"""
	# NOTE(PR 9 hook): when the caller is not a Desk session (external API, Authorization
	# header) this is the point to check `Decision Policy.allow_api_access` on the resolved
	# `policy` (403 if unset) and to apply `@rate_limit(key="policy", limit=60,
	# seconds=60)` (PLAN.md §3.12) -- neither is implemented in PR 2A.
	_require("decision.run")

	if origin_type not in ("Playground", "API"):
		frappe.throw(_("origin_type must be Playground or API"))

	decoded_definition = _json_arg(definition)
	if decoded_definition is not None:
		# Ad-hoc authoring is always decision.author, on top of the decision.run every
		# run_decision caller needs (PLAN.md §3.17 grants row for decision.author).
		_require("decision.author")

	if pinned_deployment:
		_require("decision.admin")

	decoded_candidates = _json_arg(candidates) or []
	if not isinstance(decoded_candidates, (list, tuple)):
		frappe.throw(_("candidates must be a list"))
	parsed_candidates = tuple(
		item if isinstance(item, Option) else Option(id=str(item["id"]), description=str(item.get("description", "")))
		for item in decoded_candidates
	)

	candidate_source_enum = CandidateSource(candidate_source) if candidate_source else None

	resolved_surface = surface or ("API" if origin_type == "API" else "Playground")

	origin = DecisionOrigin(origin_type=origin_type, owner_user=frappe.session.user)

	result = service.run_policy(
		policy=policy,
		definition=decoded_definition,
		decision_model=decision_model,
		state=state,
		candidates=parsed_candidates,
		candidate_source=candidate_source_enum,
		candidate_resolver_id=candidate_resolver_id,
		mode=service.MODE_MANUAL,
		surface=resolved_surface,
		origin=origin,
		policy_version=policy_version,
		pinned_deployment=pinned_deployment,
		latency_budget_ms=int(latency_budget_ms) if latency_budget_ms else None,
	)

	return _serialize_service_result(result, include_raw=_is_admin())


def _serialize_service_result(result: "service.ServiceResult", *, include_raw: bool) -> dict:
	status = result.status
	return {
		"status": status.value if hasattr(status, "value") else status,
		"decision_call": result.decision_call,
		"fallback_action": result.fallback_action,
		"response": _serialize_response(result.response, include_raw=include_raw),
	}


def _serialize_response(response: Any, *, include_raw: bool) -> dict | None:
	if response is None:
		return None
	return {
		"status": response.status.value if hasattr(response.status, "value") else response.status,
		"answers": {qid: _serialize_answer(answer, include_raw=include_raw) for qid, answer in response.answers.items()},
		"identity": _serialize_identity(response.identity),
		"requested_identity": _serialize_identity(response.requested_identity),
		"backend_adapter": response.backend_adapter,
		"requested_model": response.requested_model,
		"requested_model_version": response.requested_model_version,
		"resolved_model": response.resolved_model,
		"resolved_model_version": response.resolved_model_version,
		"usage": _serialize_usage(response.usage),
		"latency_ms": response.latency_ms,
		"error_code": response.error_code,
		"policy_fallback_action": response.policy_fallback_action,
		"gate_result": response.gate_result,
		"deployment_selection_source": response.deployment_selection_source,
		"deployment_fallback_count": response.deployment_fallback_count,
		"deployment_fallback_chain": list(response.deployment_fallback_chain),
	}


def _serialize_answer(answer: Any, *, include_raw: bool) -> dict:
	data = {
		"question_id": answer.question_id,
		"kind": answer.kind.value if hasattr(answer.kind, "value") else answer.kind,
		"value": answer.value,
		"probabilities": dict(answer.probabilities) if answer.probabilities else None,
		"confidence": answer.confidence,
	}
	if include_raw and answer.backend_metadata:
		data["backend_metadata"] = dict(answer.backend_metadata)
	return data


def _serialize_identity(identity: Any) -> dict:
	return {
		"model_class": identity.model_class,
		"model_family": identity.model_family,
		"canonical_model": identity.canonical_model,
		"canonical_version": identity.canonical_version,
		"provider": identity.provider,
		"deployment": identity.deployment,
		"provider_model_id": identity.provider_model_id,
	}


def _serialize_usage(usage: Any) -> dict:
	return {
		"input_tokens": usage.input_tokens,
		"output_tokens": usage.output_tokens,
		"cost": usage.measured_cost,
		"cost_source": usage.cost_source,
	}


# -- list_decision_models ---------------------------------------------------------------------


@frappe.whitelist()
def list_decision_models() -> list[dict]:
	"""List Decision Models for the Playground picker and the Decision tab (PLAN.md §5.3).

	Requires ``decision.run`` (the Playground model picker's own gate, PLAN.md §5.2). A
	caller without ``decision.admin`` only sees ``enabled`` models and gets no deployment
	detail -- deployments (health, provider, pricing) are the Decision tab's job, gated
	``decision.admin`` in the placement table (§5.2 row "Canonical models, deployments,
	failover order, health, Test Connection"). A ``decision.admin`` caller sees every
	model (enabled or not, for management) plus its full deployment chain.

	Returns:
		list of dicts, one per ``Decision Model``:
		``name, model_key, model_name, family, canonical_version, display_name, enabled,
		context_limit, state_limit`` always; ``deployments`` (list of
		``name, deployment_name, provider, provider_model_id, wire_protocol, enabled,
		is_default_for_model, priority, health_status, last_healthcheck,
		latency_budget_ms``, ordered by ``priority``) only for ``decision.admin``.
	"""
	_require("decision.run")
	admin = _is_admin()

	filters: dict[str, Any] = {} if admin else {"enabled": 1}
	models = frappe.get_list(
		"Decision Model",
		filters=filters,
		fields=[
			"name", "model_key", "model_name", "family", "canonical_version",
			"display_name", "enabled", "context_limit", "state_limit",
		],
		order_by="model_name asc",
	)

	if not admin:
		return models

	deployments_by_model: dict[str, list[dict]] = {}
	for row in frappe.get_list(
		"Decision Deployment",
		fields=[
			"name", "deployment_name", "decision_model", "provider", "provider_model_id",
			"wire_protocol", "enabled", "is_default_for_model", "priority", "health_status",
			"last_healthcheck", "latency_budget_ms",
		],
		order_by="decision_model asc, priority asc",
	):
		deployments_by_model.setdefault(row.pop("decision_model"), []).append(row)

	for model in models:
		model["deployments"] = deployments_by_model.get(model["name"], [])

	return models


# -- Decision Call read APIs (D5) ------------------------------------------------------------

_DECISION_CALL_LIST_FIELDS = (
	"name", "call_id", "status", "surface", "policy", "policy_version", "mode",
	"origin_type", "decision_model", "resolved_provider", "resolved_deployment",
	"resolved_model", "started_at", "ended_at", "latency_ms", "confidence", "cost",
	"error_code", "agent", "agent_run", "flow_run", "automation", "conversation",
)

_DECISION_CALL_FILTER_FIELDS = frozenset(
	{
		"surface", "policy", "policy_version", "mode", "status", "origin_type",
		"decision_model", "agent", "agent_run", "flow_run", "automation", "conversation",
		"owner_user",
	}
)

# Fields kept out of both list and detail unless the caller holds decision.admin (D5:
# "Raw backend payload and state_snapshot visible only with decision.admin"). answer_json
# is the closest thing to a raw payload that reaches a Decision Call row -- each
# DecisionAnswer (incl. backend_metadata) is persisted into it via `_json_default`'s
# `str(value)` fallback (huf.ai.decision.persistence.persist), so it can carry provider
# diagnostic detail beyond the normalized answer/probabilities/confidence fields below.
_DECISION_CALL_ADMIN_ONLY_FIELDS = ("answer_json", "state_snapshot", "question_snapshot", "state_hash")

_DECISION_CALL_DETAIL_FIELDS = (
	*_DECISION_CALL_LIST_FIELDS,
	"policy_fingerprint", "resolved_provider_model_id", "resolved_model_version",
	"backend_adapter", "flow_node_id", "owner_user", "shadow_of", "candidate_count",
	"candidate_ids_json", "probabilities_json", "input_tokens", "output_tokens",
	"cost_source", "gate_result", "fallback_action", "deployment_selection_source",
	"deployment_fallback_chain", "deployment_fallback_count", "error_message",
)


@frappe.whitelist()
def get_decision_call(name: str) -> dict:
	"""Return one ``Decision Call`` for the Executions detail view (PLAN.md §3.13).

	Visibility is D5 (``huf.huf.doctype.decision_call.decision_call.has_permission``,
	wired via ``hooks.py`` in T2A.14, reused here through ``doc.check_permission`` rather
	than re-implementing the origin-ownership check): ``decision.admin`` or the owner of
	the originating Agent Run / Flow Run / Automation, or the call's own ``owner_user``
	for an origin-less (Playground/API) call.

	Requires ``decision.run`` in addition to the D5 row-level check -- a user who somehow
	owns the origin run but has never been granted ``decision.run`` still should not reach
	Decision Runtime data (mirrors the ``decision.run`` gate on every other read here).

	``answer_json``, ``state_snapshot``, ``question_snapshot`` and ``state_hash`` are
	included only for ``decision.admin`` callers (D5's "raw backend payload and
	state_snapshot" clause -- see ``_DECISION_CALL_ADMIN_ONLY_FIELDS``).
	"""
	_require("decision.run")

	doc = frappe.get_doc("Decision Call", name)
	doc.check_permission("read")

	data = {field: doc.get(field) for field in _DECISION_CALL_DETAIL_FIELDS}
	if _is_admin():
		for field in _DECISION_CALL_ADMIN_ONLY_FIELDS:
			data[field] = doc.get(field)
	return data


@frappe.whitelist()
def list_decision_calls(
	filters: Any = None,
	limit_start: int = 0,
	limit_page_length: int = 50,
	order_by: str = "started_at desc",
) -> dict:
	"""List ``Decision Call`` rows for the Executions "Decisions" tab (PLAN.md §3.13).

	Row visibility is D5, enforced by ``frappe.get_list``'s normal permission-query-
	conditions pass (``get_permission_query_conditions`` from
	``huf.huf.doctype.decision_call.decision_call``, wired in ``hooks.py`` by T2A.14) --
	not reimplemented here. Never includes ``answer_json``/``state_snapshot`` (list rows
	only ever carry the normalized summary fields in
	``_DECISION_CALL_LIST_FIELDS``, so there is nothing to admin-gate at list level; detail
	is where D5's raw/state clause applies, via ``get_decision_call``).

	Args:
		filters: mapping (or JSON string) of exact-match filters, restricted to
			``_DECISION_CALL_FILTER_FIELDS`` (surface, policy, policy_version, mode,
			status, origin_type, decision_model, agent, agent_run, flow_run, automation,
			conversation, owner_user).
		limit_start / limit_page_length: pagination; ``limit_page_length`` capped at 200.
		order_by: defaults to newest first.

	Returns:
		``{"rows": [...], "total": int, "limit_start": int, "limit_page_length": int}``.
	"""
	_require("decision.run")

	decoded_filters = _json_arg(filters) or {}
	if not isinstance(decoded_filters, dict):
		frappe.throw(_("filters must be a mapping"))
	unknown = set(decoded_filters) - _DECISION_CALL_FILTER_FIELDS
	if unknown:
		frappe.throw(_("Unsupported filter fields: {0}").format(", ".join(sorted(unknown))))

	limit_page_length = min(int(limit_page_length or 50), 200)
	limit_start = max(int(limit_start or 0), 0)

	rows = frappe.get_list(
		"Decision Call",
		filters=decoded_filters,
		fields=list(_DECISION_CALL_LIST_FIELDS),
		order_by=order_by,
		limit_start=limit_start,
		limit_page_length=limit_page_length,
	)
	total = frappe.get_list(
		"Decision Call",
		filters=decoded_filters,
		fields=["count(name) as total"],
	)[0]["total"]

	return {"rows": rows, "total": total, "limit_start": limit_start, "limit_page_length": limit_page_length}


# -- Policy authoring ---------------------------------------------------------------------


@frappe.whitelist()
def validate_policy_definition(definition: Any) -> dict:
	"""Validate an ad-hoc/draft policy definition without saving or running it.

	Requires ``decision.author`` (policy authoring, PLAN.md §3.17). Thin wrapper around
	``huf.ai.decision.policy.validate_policy_data`` -- the same validator ``Decision
	Policy.validate`` and ``run_decision``'s ad-hoc path use, so "valid here" means "will
	be accepted by both save and run".

	Args:
		definition: policy JSON (mapping, or a JSON string) in the
			``validate_policy_data`` shape (``policy_id``, ``questions``, ...).

	Returns:
		On success: ``{"valid": True, "policy_id", "fingerprint", "question_count",
		"question_ids", "required_modalities"}``.
		On failure: ``{"valid": False, "error_code", "message"}`` -- never raises for an
		invalid *definition* (a bad shape is an expected authoring-time result, not a
		server error); still raises ``frappe.PermissionError`` for a missing capability
		and propagates ``TypeError``/``json.JSONDecodeError`` for a malformed argument
		(not a policy-shape problem).
	"""
	_require("decision.author")

	data = _json_arg(definition)
	if not isinstance(data, dict):
		frappe.throw(_("definition must be a JSON object"))

	try:
		policy = validate_policy_data(data)
	except DecisionError as exc:
		return {"valid": False, "error_code": exc.code.value, "message": str(exc)}

	return {
		"valid": True,
		"policy_id": policy.policy_id,
		"fingerprint": policy.fingerprint,
		"question_count": len(policy.questions),
		"question_ids": [question.id for question in policy.questions],
		"required_modalities": sorted(policy.required_modalities),
	}


@frappe.whitelist()
def publish_policy_version(policy: str) -> dict:
	"""Publish a ``Decision Policy``'s current ``definition_json`` as a new version.

	Requires ``decision.admin`` (PLAN.md §5.2 placement table: publish is decision.admin,
	stricter than ``decision.author``'s create/edit-Draft grant). Thin wrapper around the
	existing whitelisted ``Decision Policy.publish_version`` doc method (T2A -- policy.py
	is out of this task's file scope, so publishing logic itself is not duplicated here);
	this function only adds the capability gate and a stable function-style entry point
	for ``decisionApi.ts`` and the public API docs, matching how the other functions in
	this module are called (``huf.ai.decision.api.<name>``, not ``run_doc_method``).

	Args:
		policy: ``Decision Policy`` docname.

	Returns:
		``{"policy": <docname>, "version": <new Decision Policy Version docname>}``.
	"""
	_require("decision.admin")

	doc = frappe.get_doc("Decision Policy", policy)
	doc.check_permission("write")
	version_name = doc.publish_version()

	return {"policy": doc.name, "version": version_name}
