"""Load a deployment chain for a canonical Decision Model from Frappe rows.

``load_chain`` is the only place that turns ``Decision Deployment`` rows into a
runnable :class:`~huf.ai.decision.deployment.DeploymentChain`. It:

1. Reads enabled ``Decision Deployment`` rows for one ``Decision Model``, joined against
   ``AI Model`` and ``AI Provider`` (PLAN.md §4.6), ordered default-first then by priority.
2. Skips rows that are ``unhealthy`` or still inside their post-429 cool-down window
   (PLAN.md §3.19 -- ``degraded`` health for 60s after ``last_healthcheck``).
3. Resolves each row's semantic adapter (``adapter_override`` or the model family's
   ``adapter_id``, PLAN.md D3), computes effective capabilities as the AND of the family's
   defaults and the deployment's capability flags, builds a wire transport
   (``huf.ai.decision.transports.build_transport``) and instantiates the backend
   (``huf.ai.decision.registry.resolve_backend``).
4. Delegates ordering/eligibility to the existing, tested
   ``huf.ai.decision.deployment.resolve_deployment_chain`` rather than re-implementing it.

Caching (D-none specific, but see PLAN.md §4.6): only the *row list* -- plain dict/JSON
values queried from the database -- is cached in ``frappe.cache()`` for 30 seconds, keyed
per ``decision_model``. Nothing derived (backends, transports, provider API keys) is ever
cached; ``load_chain`` builds a fresh transport/backend for every call from the cached rows,
so a provider key rotation or deployment edit is live on the next call regardless of the
cache TTL (see ``invalidate_deployment_chain_cache`` and the ``on_update``/``on_trash``
hooks wired in ``huf/hooks.py`` for ``Decision Deployment``, ``AI Model`` and ``AI Provider``).
"""

from __future__ import annotations

import json
import time
from typing import Any

import frappe

from huf.ai.decision.deployment import DeploymentCandidate, DeploymentChain, resolve_deployment_chain
from huf.ai.decision.errors import DecisionError
from huf.ai.decision.registry import resolve_backend
from huf.ai.decision.transports import build_transport
from huf.ai.decision.types import DecisionCapabilities, DecisionIdentity, DeploymentSpec, QuestionKind

#: Row-list cache TTL (PLAN.md §4.6: "Cache the ordered row list ... for 30 s").
_ROW_CACHE_TTL_SECONDS = 30

#: Post-429 cool-down window (PLAN.md §3.19: "deployment gets a short cool-down (health
#: `degraded`, 60 s) so the next calls skip it").
_COOLDOWN_SECONDS = 60

_HEALTH_UNHEALTHY = "unhealthy"
_HEALTH_COOLDOWN = "degraded"

#: Bumped by ``invalidate_deployment_chain_cache`` to make every previously-cached row list
#: unreachable without needing to know every key that was ever written (they simply expire
#: within ``_ROW_CACHE_TTL_SECONDS`` on their own).
_EPOCH_CACHE_KEY = "huf_decision_deployment_chain_epoch"

_ROW_FIELDS = (
	"name",
	"deployment_key",
	"deployment_name",
	"decision_model",
	"ai_model",
	"provider",
	"provider_model_id",
	"wire_protocol",
	"endpoint_path",
	"adapter_override",
	"latency_budget_ms",
	"is_default_for_model",
	"priority",
	"supports_select",
	"supports_judge",
	"supports_score",
	"supports_parallel_questions",
	"supports_probabilities",
	"supports_confidence",
	"input_modalities",
	"context_limit_override",
	"state_limit_override",
	"provider_rate_limits_json",
	"provider_metadata_json",
	"health_status",
	"last_healthcheck",
)

_QUESTION_KIND_BY_FLAG = {
	"supports_select": QuestionKind.SELECT,
	"supports_judge": QuestionKind.JUDGE,
	"supports_score": QuestionKind.SCORE,
}


def load_chain(
	*,
	decision_model: str,
	pinned_deployment: str | None = None,
	deadline: float | None = None,
	bypass_health_filter: bool = False,
) -> DeploymentChain:
	"""Resolve the deployment chain for one canonical ``Decision Model``.

	Args:
		decision_model: ``Decision Model`` docname (its ``model_key``), matching
			``Decision Deployment.decision_model``.
		pinned_deployment: If given, narrow to that single ``Decision Deployment`` docname
			(``deployment_key``) regardless of priority/default, with
			``selection_source == "pinned"`` on the returned chain.
		deadline: Monotonic timestamp (``time.monotonic()`` seconds) budget passed through to
			transport construction so an already-expired caller deadline is not spent trying
			to build every candidate's transport. ``None`` means "no deadline yet known";
			transports fall back to their own defaults (provider ``timeout_seconds`` etc.).
		bypass_health_filter: Skip the unhealthy/cool-down exclusion. Only meant for an
			explicit health probe (``api.test_deployment``) pinned to one deployment: without
			this, a deployment marked unhealthy by a *previous* failed probe can never be
			re-tested through the normal path, since the probe itself calls this function and
			would exclude the very row it is trying to re-check. Never set this for a normal
			policy-serving call -- production traffic must still honor health/cool-down.

	Returns:
		A :class:`~huf.ai.decision.deployment.DeploymentChain`. Never raises for "no rows" /
		"no healthy rows" / "deployment has no usable key" -- those simply produce an empty
		chain (``candidates == ()``), which is the caller's (``service.run_policy``) signal to
		apply the policy fallback (PLAN.md §3.19).
	"""
	context = _load_model_context(decision_model)
	requested_identity = context["identity"]
	rows = context["rows"]

	if pinned_deployment:
		rows = [row for row in rows if row["deployment_key"] == pinned_deployment]

	candidates = []
	for rank, row in enumerate(rows):
		if not bypass_health_filter and _in_cooldown(row):
			continue
		candidate = _build_candidate(
			row,
			requested_identity=requested_identity,
			family_adapter_id=context["family_adapter_id"],
			family_capabilities=context["family_capabilities"],
			rank=rank,
			deadline=deadline,
		)
		if candidate is not None:
			candidates.append(candidate)

	chain = resolve_deployment_chain(
		requested_identity, tuple(candidates), bypass_health_filter=bypass_health_filter
	)
	if pinned_deployment:
		chain = DeploymentChain(
			requested_identity=chain.requested_identity,
			candidates=chain.candidates,
			selection_source="pinned",
		)
	return chain


def invalidate_deployment_chain_cache(doc=None, method=None) -> None:
	"""Doc-event hook: bump the cache epoch so every cached row list goes stale immediately.

	Wired in ``huf/hooks.py`` as ``on_update``/``on_trash`` for ``Decision Deployment``,
	``AI Model`` and ``AI Provider``. A change to any of those can affect any number of
	``Decision Model``s' chains (an ``AI Model``/``AI Provider`` edit does not carry the
	affected ``decision_model`` keys with it), so rather than tracking every cache key ever
	written, this bumps a single epoch counter: the next ``load_chain`` call for any model
	computes a cache key that has never been written and falls through to the database. Stale
	rows at the old epoch are never read again and simply expire within
	``_ROW_CACHE_TTL_SECONDS``.

	Best-effort: a cache failure here must never fail the triggering document save/delete.
	"""
	try:
		cache = frappe.cache()
		current = cache.get_value(_EPOCH_CACHE_KEY)
		cache.set_value(_EPOCH_CACHE_KEY, (int(current) if current else 0) + 1)
	except Exception as exc:
		frappe.logger("huf").debug(f"Decision deployment chain cache invalidation failed: {exc!s}")


def _current_epoch() -> int:
	try:
		value = frappe.cache().get_value(_EPOCH_CACHE_KEY)
	except Exception:
		return 0
	return int(value) if value else 0


def _row_cache_key(decision_model: str) -> str:
	return f"huf_decision_deployment_chain:{_current_epoch()}:{decision_model}"


def _load_model_context(decision_model: str) -> dict[str, Any]:
	"""Return (and cache) the requested identity, family adapter/capabilities, and rows."""
	cache_key = _row_cache_key(decision_model)
	try:
		# expires=True: this key was written with expires_in_sec, so a Redis-side expiry (or a
		# not-yet-written key) must not be memoized as "None forever" in frappe.local.cache --
		# without it, RedisWrapper.get_value() would cache a miss in-process and never notice
		# a value written moments later (see frappe/utils/redis_wrapper.py get_value()).
		cached = frappe.cache().get_value(cache_key, expires=True)
	except Exception:
		cached = None

	if cached is None:
		cached = _fetch_model_context(decision_model)
		try:
			frappe.cache().set_value(cache_key, cached, expires_in_sec=_ROW_CACHE_TTL_SECONDS)
		except Exception as exc:
			frappe.logger("huf").debug(f"Decision deployment chain cache write failed: {exc!s}")

	identity = DecisionIdentity(
		model_class=cached.get("model_class"),
		model_family=cached.get("family_name"),
		canonical_model=cached.get("model_name") or decision_model,
		canonical_version=cached.get("canonical_version"),
	)
	return {
		"identity": identity,
		"family_adapter_id": cached.get("family_adapter_id"),
		"family_capabilities": _family_capabilities(cached.get("default_capabilities_json")),
		"rows": cached.get("rows") or [],
	}


def _fetch_model_context(decision_model: str) -> dict[str, Any]:
	"""Query the database once for the model/family/class identity plus every enabled row.

	Only plain values (strings, ints, JSON text) are returned -- nothing derived, no
	documents, no secrets -- so this is exactly what gets cached (PLAN.md §4.6: "row list ...
	no secrets cached").
	"""
	model_row = frappe.db.sql(
		"""
		SELECT
			dm.name AS model_name,
			dm.canonical_version AS canonical_version,
			dmf.name AS family_name,
			dmf.adapter_id AS family_adapter_id,
			dmf.default_capabilities_json AS default_capabilities_json,
			dmc.class_name AS model_class
		FROM `tabDecision Model` dm
		LEFT JOIN `tabDecision Model Family` dmf ON dmf.name = dm.family
		LEFT JOIN `tabDecision Model Class` dmc ON dmc.name = dmf.model_class
		WHERE dm.name = %s
		""",
		(decision_model,),
		as_dict=True,
	)

	if not model_row:
		return {"rows": []}

	context = dict(model_row[0])

	field_list = ", ".join(f"dd.{field}" for field in _ROW_FIELDS)
	rows = frappe.db.sql(
		f"""
		SELECT {field_list}
		FROM `tabDecision Deployment` dd
		INNER JOIN `tabAI Model` am ON am.name = dd.ai_model
		INNER JOIN `tabAI Provider` ap ON ap.name = dd.provider
		WHERE dd.decision_model = %s AND dd.enabled = 1
		ORDER BY dd.is_default_for_model DESC, dd.priority ASC, dd.name ASC
		""",
		(decision_model,),
		as_dict=True,
	)
	context["rows"] = rows
	return context


def _in_cooldown(row: dict[str, Any]) -> bool:
	"""True if this row must be skipped: unhealthy, or degraded and still cooling down."""
	health_status = row.get("health_status")
	if health_status == _HEALTH_UNHEALTHY:
		return True
	if health_status != _HEALTH_COOLDOWN:
		return False

	last_healthcheck = row.get("last_healthcheck")
	if not last_healthcheck:
		# Degraded with no recorded check time: fail safe by treating it as still cooling
		# down rather than retrying a deployment we have no timestamp evidence has recovered.
		return True
	try:
		checked_at = frappe.utils.get_datetime(last_healthcheck)
		elapsed = (frappe.utils.now_datetime() - checked_at).total_seconds()
	except Exception:
		# Unparseable timestamp: don't let bad data permanently blacklist a deployment.
		return False
	return elapsed < _COOLDOWN_SECONDS


def _family_capabilities(default_capabilities_json: str | None) -> DecisionCapabilities:
	"""Parse ``Decision Model Family.default_capabilities_json`` into a ``DecisionCapabilities``.

	Missing/blank/invalid JSON falls back to the most permissive defaults (all primitives,
	parallel questions on, text input only) -- the deployment's own ``supports_*`` flags are
	what actually narrow capabilities in practice (``_effective_capabilities``).
	"""
	data: dict[str, Any] = {}
	if default_capabilities_json:
		try:
			parsed = json.loads(default_capabilities_json)
			if isinstance(parsed, dict):
				data = parsed
		except (TypeError, ValueError):
			data = {}

	primitives_raw = data.get("primitives")
	if isinstance(primitives_raw, list) and primitives_raw:
		primitives = frozenset(
			QuestionKind(value) for value in primitives_raw if value in {kind.value for kind in QuestionKind}
		)
	else:
		primitives = frozenset(QuestionKind)
	if not primitives:
		primitives = frozenset(QuestionKind)

	input_modalities_raw = data.get("input_modalities")
	input_modalities = (
		frozenset(input_modalities_raw)
		if isinstance(input_modalities_raw, list) and input_modalities_raw
		else frozenset({"text"})
	)

	return DecisionCapabilities(
		primitives=primitives,
		parallel_questions=bool(data.get("parallel_questions", True)),
		probabilities=bool(data.get("probabilities", False)),
		confidence=bool(data.get("confidence", False)),
		input_modalities=input_modalities,
		max_state_bytes=data.get("max_state_bytes"),
		max_candidates_per_select=data.get("max_candidates_per_select"),
	)


def _effective_capabilities(family: DecisionCapabilities, row: dict[str, Any]) -> DecisionCapabilities:
	"""AND the family's default capabilities with this deployment's capability flags."""
	primitives = frozenset(
		kind for flag, kind in _QUESTION_KIND_BY_FLAG.items() if row.get(flag) and kind in family.primitives
	)
	if not primitives:
		primitives = frozenset()

	input_modalities_raw = row.get("input_modalities")
	deployment_modalities = None
	if input_modalities_raw:
		try:
			parsed = json.loads(input_modalities_raw)
			if isinstance(parsed, list) and parsed:
				deployment_modalities = frozenset(parsed)
		except (TypeError, ValueError):
			deployment_modalities = None
	input_modalities = (family.input_modalities & deployment_modalities) if deployment_modalities else family.input_modalities

	max_state_bytes = _min_of(family.max_state_bytes, row.get("state_limit_override"))

	return DecisionCapabilities(
		primitives=primitives,
		parallel_questions=family.parallel_questions and bool(row.get("supports_parallel_questions")),
		probabilities=family.probabilities and bool(row.get("supports_probabilities")),
		confidence=family.confidence and bool(row.get("supports_confidence")),
		input_modalities=input_modalities,
		max_state_bytes=max_state_bytes,
		max_candidates_per_select=family.max_candidates_per_select,
	)


def _min_of(*values: int | None) -> int | None:
	present = [value for value in values if value]
	return min(present) if present else None


def _resolve_timeout(deadline: float | None) -> float:
	"""Remaining budget in seconds for transport construction.

	``build_transport`` further narrows this against the deployment's ``latency_budget_ms``
	and the provider's ``timeout_seconds`` (PLAN.md §4.4), so an overly generous fallback here
	is harmless when ``deadline`` is unknown.
	"""
	if deadline is None:
		return 30.0
	return max(deadline - time.monotonic(), 0.01)


def _build_candidate(
	row: dict[str, Any],
	*,
	requested_identity: DecisionIdentity,
	family_adapter_id: str | None,
	family_capabilities: DecisionCapabilities,
	rank: int,
	deadline: float | None,
) -> DeploymentCandidate | None:
	"""Build one live ``DeploymentCandidate`` (transport + backend already wired), or ``None``.

	``rank`` (the row's index in the already default-first-then-priority-ordered row list) is
	used as the candidate's ``priority`` so ``resolve_deployment_chain``'s own
	``(priority, deployment)`` sort preserves that order exactly -- it has no notion of
	``is_default_for_model`` itself (PLAN.md §4.5/§4.6 delegate ordering to it, but its sort
	key alone would put a low-priority non-default row ahead of a higher-priority default
	one).
	"""
	adapter_id = row.get("adapter_override") or family_adapter_id
	if not adapter_id:
		frappe.logger("huf").debug(f"Decision deployment {row.get('deployment_key')!r} has no resolvable adapter id")
		return None

	identity = DecisionIdentity(
		model_class=requested_identity.model_class,
		model_family=requested_identity.model_family,
		canonical_model=requested_identity.canonical_model,
		canonical_version=requested_identity.canonical_version,
		provider=row.get("provider"),
		deployment=row.get("deployment_key"),
		provider_model_id=row.get("provider_model_id"),
	)
	spec = DeploymentSpec(
		identity=identity,
		effective_capabilities=_effective_capabilities(family_capabilities, row),
		wire_protocol=row.get("wire_protocol") or "systemone",
		endpoint_path=row.get("endpoint_path"),
		latency_budget_ms=row.get("latency_budget_ms") or None,
	)

	try:
		transport = build_transport(frappe._dict(row), timeout=_resolve_timeout(deadline), deadline=deadline)
	except (ValueError, NotImplementedError) as exc:
		frappe.logger("huf").debug(f"Decision deployment {row.get('deployment_key')!r} transport unavailable: {exc!s}")
		return None

	try:
		backend = resolve_backend(adapter_id, deployment=spec, transport=transport)
	except DecisionError as exc:
		frappe.logger("huf").debug(f"Decision deployment {row.get('deployment_key')!r} backend unavailable: {exc!s}")
		return None

	return DeploymentCandidate(
		identity=identity,
		backend=backend,
		enabled=True,
		priority=rank,
		health_status=row.get("health_status") or "healthy",
	)
