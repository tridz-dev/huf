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
import math
import time
from datetime import timedelta
from typing import Any

import frappe
from frappe import _

from huf.ai.decision import service
from huf.ai.decision.deployment_loader import load_chain, invalidate_deployment_chain_cache
from huf.ai.decision.errors import DecisionError
from huf.ai.decision.policy import DecisionPolicy, validate_policy_data
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import (
	CandidateSource,
	DecisionIdentity,
	DecisionOrigin,
	DecisionRequest,
	DecisionStatus,
	Option,
	QuestionKind,
)
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
		state: Provider-visible state -- a mapping, or a JSON string encoding one (decoded
			via ``_json_arg`` the same way ``definition``/``candidates`` are). A policy's
			``state_bindings`` are looked up as dict keys, so a state that arrives as a raw
			(un-decoded) string fails every binding lookup with ``POLICY_INVALID``.
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
		state=_json_arg(state),
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


# -- Setup wizard & deployment health -------------------------------------------------------


@frappe.whitelist()
def get_setup_catalog() -> list[dict]:
	"""List catalog entries available for the setup wizard (PLAN.md §3.1).

	Requires ``decision.admin``. Returns only entries for providers that either:
	- Have a key configured on their ``AI Provider`` row, or
	- Use a local backend (no provider authentication required).

	Returns:
		List of dicts, one per available catalog entry:
		``provider_brand, model_name, canonical_model, model_family, model_class,
		wire_protocol, endpoint_path, base_url, provider_ready`` (True if the provider
		has a key, False if local).
	"""
	from huf.ai.decision import catalog

	_require("decision.admin")

	result = []
	seen = set()

	# Iterate through all catalog entries
	for entry in catalog._CATALOG.values():
		# Avoid duplicates (same brand/model pair)
		if (entry.provider_brand, entry.model_name) in seen:
			continue
		seen.add((entry.provider_brand, entry.model_name))

		# Check if the provider exists and has a key
		provider_rows = frappe.get_list(
			"AI Provider",
			filters={"provider_brand": entry.provider_brand},
			fields=["name", "api_key"],
			limit_page_length=1,
		)

		provider_ready = False
		if provider_rows:
			# Provider exists. Check if it has a key by looking at api_key field
			# (PLAN.md §3.1 "Providers with a key show Ready; without, Add key")
			provider_ready = bool(provider_rows[0].get("api_key"))

		result.append({
			"provider_brand": entry.provider_brand,
			"model_name": entry.model_name,
			"canonical_model": entry.canonical_model,
			"model_family": entry.model_family,
			"model_class": entry.model_class,
			"wire_protocol": entry.wire_protocol,
			"endpoint_path": entry.endpoint_path,
			"base_url": entry.base_url,
			"provider_ready": provider_ready,
		})

	return sorted(result, key=lambda x: (x["provider_brand"], x["model_name"]))


@frappe.whitelist()
def setup_deployment(
	provider: str,
	model_name: str,
	**kwargs: Any,
) -> dict:
	"""Set up a Decision Deployment idempotently (PLAN.md §3.1 step 3).

	Creates (or reuses) an ``AI Model`` (modality Decision) and the Class/Family/Model
	hierarchy from the catalog entry, creates a ``Decision Deployment``, and runs a test
	probe. If the probe passes, the deployment is enabled; if it fails, it is saved
	disabled with the error.

	Requires ``decision.admin``.

	Args:
		provider: ``AI Provider`` docname.
		model_name: Catalog model name (e.g. ``"jev-1.13-free"``).
		**kwargs: Reserved for future parameters (ignored for now).

	Returns:
		``{
			"deployment": <Decision Deployment docname>,
			"ai_model": <AI Model docname>,
			"probe": {"status", "latency_ms", "error_code"}
		}``.

	Raises:
		frappe.PermissionError: missing ``decision.admin``.
		frappe.ValidationError: unresolvable provider or catalog entry, missing provider key.
	"""
	from huf.ai.decision import catalog
	from huf.patches.v1.seed_decision_system_one import (
		_seed_classes,
		_seed_families,
		_seed_model,
		_seed_ai_model,
		_seed_deployment,
	)

	_require("decision.admin")

	# Get the provider row
	provider_doc = frappe.get_doc("AI Provider", provider)
	provider_brand = provider_doc.provider_brand
	if not provider_brand:
		frappe.throw(_("Provider {0} has no brand configured").format(provider))

	# Look up the catalog entry
	entry = catalog.get_entry(provider_brand, model_name)
	if entry is None:
		frappe.throw(
			_("No catalog entry for provider {0} / model {1}").format(provider_brand, model_name)
		)

	# Check that the provider has a key
	if not provider_doc.api_key:
		frappe.throw(_("Provider {0} has no API key. Add one first.").format(provider))

	# Idempotently create/reuse the Class/Family/Model hierarchy
	class_names = _seed_classes()
	family_names = _seed_families(class_names)
	decision_model_name = _seed_model(family_names)

	# Idempotently create/reuse the AI Model row
	ai_model_name = _seed_ai_model(provider)

	# Idempotently create the Deployment row
	deployment_name = _seed_deployment(decision_model_name, ai_model_name, provider)

	# Run a test probe on the deployment
	probe_result = test_deployment(deployment_name)

	# Update the deployment's enabled status based on the probe
	deployment_doc = frappe.get_doc("Decision Deployment", deployment_name)
	if probe_result["status"] == "success":
		deployment_doc.enabled = 1
	else:
		deployment_doc.enabled = 0
	deployment_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"deployment": deployment_name,
		"ai_model": ai_model_name,
		"probe": probe_result,
	}


@frappe.whitelist()
def test_deployment(deployment: str) -> dict:
	"""Test a Decision Deployment with one tiny judge probe (PLAN.md §3.3 step 4).

	Sends a minimal judge question through the resolved backend and records the result
	in the deployment's ``health_status`` and ``last_healthcheck`` fields. Requires
	``decision.admin``.

	Args:
		deployment: ``Decision Deployment`` docname (``deployment_key``).

	Returns:
		``{"status", "latency_ms", "error_code"}``:
		- status: "success" or "failed"
		- latency_ms: wall-clock time in milliseconds
		- error_code: ``None`` on success, or a ``DecisionErrorCode.value`` string on failure.
			Never includes the raw provider error or any key material.

	Raises:
		frappe.PermissionError: missing ``decision.admin``.
		frappe.ValidationError: deployment not found.
	"""
	_require("decision.admin")

	# Get the deployment to find its model
	deployment_doc = frappe.get_doc("Decision Deployment", deployment)
	decision_model = deployment_doc.decision_model

	started = time.monotonic()

	try:
		# Invalidate the cache to ensure fresh chain load
		invalidate_deployment_chain_cache()

		# Load the deployment chain, pinned to just this deployment
		chain = load_chain(
			decision_model=decision_model,
			pinned_deployment=deployment,
			deadline=time.monotonic() + 5.0,  # 5s timeout for the probe
			bypass_health_filter=True,  # this call IS the health check; never let a
			# previous failure permanently exclude the deployment from being re-tested
		)

		if not chain.candidates:
			# No valid deployment candidate (e.g., no key, transport error)
			error_code = "DEPLOYMENT_UNAVAILABLE"
			status = "failed"
			latency_ms = (time.monotonic() - started) * 1000
		else:
			# Build a minimal judge question for probing
			probe_policy = validate_policy_data(
				{
					"policy_id": "__probe__",
					"questions": [
						{
							"id": "probe",
							"kind": "judge",
							"instructions": "This is a probe question. Return true.",
							"positive_criteria": "Always true.",
							"negative_criteria": "Never applies.",
						}
					],
					"store_state": False,
					# A policy must bind at least one piece of provider-visible state; the
					# probe question doesn't need any, so bind a fixed placeholder.
					"state_bindings": [{"name": "probe_context", "path": "probe"}],
				}
			)

			request = DecisionRequest(
				policy=probe_policy,
				identity=chain.requested_identity,
				surface="admin_test",
				state={"probe": "connection test"},
				candidates=(),
				candidate_source=None,
				candidate_resolver_id=None,
				# Leave modalities at its dataclass default (frozenset({"text"})); passing
				# None here crashes prepare_state's `request.modalities | detected_modalities`.
			)

			# Run through the runtime
			runtime = DecisionRuntime()
			response = runtime.evaluate_deployment_chain(
				request,
				chain,
				deadline=time.monotonic() + 5.0,
			)

			latency_ms = (time.monotonic() - started) * 1000

			if response.status == DecisionStatus.SUCCESS:
				status = "success"
				error_code = None
			else:
				status = "failed"
				error_code = response.error_code

		# Update the deployment's health status
		health_status = "healthy" if status == "success" else "unhealthy"
		frappe.db.set_value(
			"Decision Deployment",
			deployment,
			{
				"health_status": health_status,
				"last_healthcheck": frappe.utils.now_datetime(),
			},
			update_modified=True,
		)
		frappe.db.commit()

		return {
			"status": status,
			"latency_ms": int(latency_ms),
			"error_code": error_code,
		}

	except Exception as exc:
		# Log the error but don't leak it to the caller
		frappe.logger("huf").exception(f"Decision deployment {deployment} test failed")
		latency_ms = (time.monotonic() - started) * 1000

		# Mark as unhealthy
		frappe.db.set_value(
			"Decision Deployment",
			deployment,
			{
				"health_status": "unhealthy",
				"last_healthcheck": frappe.utils.now_datetime(),
			},
			update_modified=True,
		)
		frappe.db.commit()

		return {
			"status": "failed",
			"latency_ms": int(latency_ms),
			"error_code": "INTERNAL_ERROR",
		}


# -- Binding stats & observability -------------------------------------------------------


@frappe.whitelist()
def get_binding_stats(agent: str) -> dict:
	"""Return last-7-day statistics for each Agent Decision Binding (PLAN.md §3.14).

	Aggregates Decision Call counts, latency, and fallback rates for each binding row
	over the past 7 days, broken down by surface/policy/mode. Used by the Agent
	observability / analytics view (not yet in this PR, deferred to analytics phase).

	Requires ``agent.edit`` capability on the Agent *plus* ``frappe.has_permission("read")``
	on the Agent document (D4: standard Agent ACL applies; agent.edit is the capability
	gate, per-agent read check is the row-level gate).

	Args:
		agent: ``Agent`` docname.

	Returns:
		``{
			"agent": <docname>,
			"bindings": [
				{
					"binding_id": <child table hash>,
					"surface": <surface name>,
					"policy": <policy docname>,
					"mode": <Off|Shadow|Advise|Enforce>,
					"enabled": <bool>,
					"stats": {
						"calls": <7-day count>,
						"fallback_rate": <0.0-1.0 or null if no calls>,
						"p95_latency_ms": <milliseconds or null if no calls>,
						"shadow_agreement": null,
						"advise_followed_rate": null,
					}
				},
				...
			]
		}``.

	Raises:
		frappe.PermissionError: missing ``agent.edit`` or the user cannot read the Agent.
		frappe.DoesNotExistError: Agent not found.
	"""
	_require("agent.edit")

	# Fetch and permission-check the Agent document
	agent_doc = frappe.get_doc("Agent", agent)
	agent_doc.check_permission("read")

	# Compute the 7-day cutoff
	now_dt = frappe.utils.now_datetime()
	cutoff_dt = now_dt - timedelta(days=7)

	bindings_stats = []

	# Import evaluation module for shadow_agreement/advise_followed_rate metrics (T10.01)
	from huf.ai.decision import evaluation

	# Iterate through each binding and compute its stats
	for binding in agent_doc.decision_bindings or []:
		# Query Decision Call records for this binding's surface/policy combo
		calls = frappe.get_list(
			"Decision Call",
			filters={
				"agent": agent,
				"surface": binding.surface,
				"policy": binding.policy,
				"started_at": [">=", cutoff_dt],
			},
			fields=["name", "latency_ms", "fallback_action"],
			order_by="started_at asc",
		)

		# Calculate statistics
		call_count = len(calls)
		fallback_count = sum(1 for call in calls if call.fallback_action)
		fallback_rate = (fallback_count / call_count) if call_count > 0 else None

		# Compute p95 latency from the sample
		p95_latency_ms = None
		if call_count > 0:
			latencies = sorted([call["latency_ms"] for call in calls if call["latency_ms"]])
			if latencies:
				# p95: 95th percentile using nearest rank method.
				# For n items, p95 index = ceil(0.95 * n) - 1
				p95_idx = min(len(latencies) - 1, math.ceil(0.95 * len(latencies)) - 1)
				p95_latency_ms = latencies[p95_idx]

		# Get shadow_agreement rate for Shadow/Enforce modes on measurable surfaces (T10.01)
		shadow_agreement = None
		if binding.surface in evaluation.MEASURABLE_SURFACES:
			try:
				shadow_result = evaluation.get_shadow_agreement(
					policy=binding.policy,
					agent=agent,
					surface=binding.surface,
					from_date=cutoff_dt,
					to_date=now_dt,
				)
				# Extract the agreement rate for this surface from by_surface
				if shadow_result.get("by_surface"):
					for surface_data in shadow_result["by_surface"]:
						if surface_data.get("surface") == binding.surface:
							shadow_agreement = surface_data.get("matched")
							break
			except (frappe.ValidationError, ValueError, KeyError):
				# If evaluation fails, leave as None with reason below
				pass

		# Get advise_followed_rate for Advise mode on measurable surfaces (T10.01)
		advise_followed_rate = None
		if binding.mode == "Advise" and binding.surface in evaluation.MEASURABLE_SURFACES:
			try:
				advise_result = evaluation.get_followed_advice(
					policy=binding.policy,
					agent=agent,
					surface=binding.surface,
					from_date=cutoff_dt,
					to_date=now_dt,
				)
				# Extract the followed-advice rate for this surface from by_surface
				if advise_result.get("by_surface"):
					for surface_data in advise_result["by_surface"]:
						if surface_data.get("surface") == binding.surface:
							advise_followed_rate = surface_data.get("matched")
							break
			except (frappe.ValidationError, ValueError, KeyError):
				# If evaluation fails, leave as None
				pass

		binding_stat = {
			"binding_id": binding.name,
			"surface": binding.surface,
			"policy": binding.policy,
			"mode": binding.mode,
			"enabled": binding.enabled,
			"stats": {
				"calls": call_count,
				"fallback_rate": fallback_rate,
				"p95_latency_ms": p95_latency_ms,
				"shadow_agreement": shadow_agreement if binding.surface in evaluation.MEASURABLE_SURFACES else None,
				"advise_followed_rate": advise_followed_rate if binding.mode == "Advise" and binding.surface in evaluation.MEASURABLE_SURFACES else None,
			},
		}
		bindings_stats.append(binding_stat)

	return {
		"agent": agent,
		"bindings": bindings_stats,
	}


# -- Evaluation (T10.01, huf.ai.decision.evaluation) ----------------------------------------
#
# All four gated by decision.run (same as every other read here) plus D5 row-level filtering,
# inherited automatically because huf.ai.decision.evaluation reads Decision Call exclusively
# through frappe.get_list/frappe.get_doc (get_permission_query_conditions / has_permission from
# huf.huf.doctype.decision_call.decision_call), never a raw SQL query. See
# huf.ai.decision.evaluation's module docstring for what "agreement" and "followed_advice" can
# and cannot measure today (shadow_of is never populated by any caller; only Model Routing and
# Tool Selection have a correlatable actual-outcome field) -- that limitation is load-bearing
# for any UI (T10.03) or later PR built on top of these endpoints.


@frappe.whitelist()
def get_policy_metrics(
	policy: str,
	policy_version: str | None = None,
	surface: str | None = None,
	from_date: Any = None,
	to_date: Any = None,
) -> dict:
	"""Per-policy/version reliability and usage metrics for a time window (IP §19.3, PLAN.md §3.13).

	Requires ``decision.run``. Thin, capability-checked wrapper around
	``huf.ai.decision.evaluation.get_policy_metrics`` -- see that function's docstring for the
	exact metric list, grouping-by-version behavior, and the null-vs-zero convention for rate
	fields with no denominator.

	Args:
		policy: ``Decision Policy`` docname (required).
		policy_version: Narrow to one ``Decision Policy Version``; omit to get every version in
			the window, grouped, plus an ``overall`` aggregate.
		surface: Narrow to one ``Decision Call.surface``.
		from_date / to_date: Window bounds (anything ``frappe.utils.get_datetime`` accepts).
			Defaults to the last 7 days.

	Returns:
		``{policy, policy_version, surface, from_date, to_date, sample_size, sample_capped,
		overall, by_version}`` -- see ``evaluation.get_policy_metrics``.
	"""
	_require("decision.run")

	from huf.ai.decision import evaluation

	return evaluation.get_policy_metrics(
		policy,
		policy_version=policy_version,
		surface=surface,
		from_date=from_date,
		to_date=to_date,
	)


@frappe.whitelist()
def get_shadow_agreement(
	policy: str | None = None,
	agent: str | None = None,
	agent_run: str | None = None,
	surface: str | None = None,
	from_date: Any = None,
	to_date: Any = None,
) -> dict:
	"""Shadow agreement per surface: Shadow Decision Call top candidate vs actual outcome
	(PLAN.md §3.13, IP §19.3). Information only -- never affects live behavior (Shadow mode
	itself already guarantees that; this only reads history).

	Requires ``decision.run``. "Per binding" is expressed as filtering by
	``policy``/``agent``/``agent_run``/``surface`` (a binding is the tuple (agent, surface,
	policy); see ``evaluation.get_shadow_agreement`` for why). All filters are optional and
	combine as AND; passing none aggregates across every Shadow call the caller can see (D5).

	Returns:
		``{mode, policy, agent, agent_run, surface, from_date, to_date, sample_size,
		sample_capped, measurable_surfaces, by_surface, not_measurable}`` -- see
		``evaluation.get_shadow_agreement`` / its module docstring for the exact meaning of
		``measurable_surfaces`` and why some surfaces always land in ``not_measurable``.
	"""
	_require("decision.run")

	from huf.ai.decision import evaluation

	return evaluation.get_shadow_agreement(
		policy=policy,
		agent=agent,
		agent_run=agent_run,
		surface=surface,
		from_date=from_date,
		to_date=to_date,
	)


@frappe.whitelist()
def get_followed_advice(
	policy: str | None = None,
	agent: str | None = None,
	agent_run: str | None = None,
	surface: str | None = None,
	from_date: Any = None,
	to_date: Any = None,
) -> dict:
	"""Followed-advice rate per surface: Advise Decision Call top-suggested candidate vs what was
	actually used afterward (PLAN.md §3.13, IP §19.3). Information only.

	Requires ``decision.run``. Same filter/aggregation shape as ``get_shadow_agreement`` (see
	above), but for ``mode="Advise"`` calls. See ``evaluation.get_followed_advice`` for which
	surfaces are Advise-eligible (``binding.ADVISE_SURFACES``) versus actually measurable
	(``evaluation.MEASURABLE_SURFACES``) -- today only Tool Selection is both.

	Returns:
		Same shape as ``get_shadow_agreement``, with ``mode="Advise"``.
	"""
	_require("decision.run")

	from huf.ai.decision import evaluation

	return evaluation.get_followed_advice(
		policy=policy,
		agent=agent,
		agent_run=agent_run,
		surface=surface,
		from_date=from_date,
		to_date=to_date,
	)


@frappe.whitelist()
def replay_policy(
	decision_call: str,
	target_policy_version: str,
	candidate_source: str | None = None,
	candidate_resolver_id: str | None = None,
	candidates: Any = None,
) -> dict:
	"""Rerun a stored Decision Call's request against a different (newer) published policy
	version (PLAN.md §3.13, IP §19.2 "Replay harness"). Thin, capability-checked wrapper around
	``huf.ai.decision.evaluation.replay_policy`` -- see that function's docstring for exactly
	what is reconstructed from the stored call (state_snapshot, candidate_ids_json) versus what
	is lost (candidate descriptions, candidate_source, question_snapshot) and how the replay is
	marked in Decision Call history (``surface="Replay:<original surface>"``, ``origin_type=
	"Playground"``) rather than counted as a new production call for the real binding.

	Requires ``decision.run`` (this runs ``service.run_policy`` -- the normal gate for running
	any decision) plus D5 read access to the original ``decision_call`` (enforced inside
	``evaluation.replay_policy`` via ``doc.check_permission("read")``).

	Args:
		decision_call: The stored ``Decision Call`` docname to replay.
		target_policy_version: ``Decision Policy Version`` docname to run against (must belong
			to the same ``Decision Policy`` as the original call, Published or Retired).
		candidate_source: Optional override for the request's declared candidate provenance
			(a ``huf.ai.decision.types.CandidateSource`` value) -- not persisted on the original
			call, so required here whenever the target version has a ``select`` question.
		candidate_resolver_id: Optional, passed straight through to ``service.run_policy``
			alongside ``candidate_source`` -- required whenever ``candidate_source`` is given
			and is not ``"policy_options"``.
		candidates: Optional override for the candidate/option list (JSON string or list of
			``{"id", "description"}`` mappings) -- defaults to the original call's
			``candidate_ids_json`` with empty descriptions.

	Returns:
		``{original_decision_call, original_policy_version, target_policy_version,
		replay_decision_call, result, limitations}`` where ``result`` mirrors ``run_decision``'s
		``{status, decision_call, fallback_action, response}`` shape (serialized through the
		same ``_serialize_service_result`` helper, so raw backend metadata stays
		``decision.admin``-gated exactly as it is for ``run_decision``).

	Raises:
		frappe.DoesNotExistError: unknown ``decision_call`` or ``target_policy_version``.
		frappe.PermissionError: missing ``decision.run``, or caller cannot read the original
			``Decision Call`` (D5).
		frappe.ValidationError: no ``state_snapshot`` to replay, or ``target_policy_version``
			does not belong to the same policy / is not Published/Retired.
		ValueError: propagated from ``service.run_policy`` for any other bad call shape.
	"""
	_require("decision.run")

	from huf.ai.decision import evaluation

	decoded_candidates = _json_arg(candidates)

	outcome = evaluation.replay_policy(
		decision_call,
		target_policy_version,
		candidate_source=candidate_source,
		candidate_resolver_id=candidate_resolver_id,
		candidates=decoded_candidates,
	)

	service_result = outcome.pop("service_result")
	outcome["replay_decision_call"] = service_result.decision_call
	outcome["result"] = _serialize_service_result(service_result, include_raw=_is_admin())
	return outcome
