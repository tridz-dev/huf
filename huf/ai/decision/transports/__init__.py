"""Transport dispatch for Decision Deployment wire protocols.

A "transport" is a callable matching the ``JevTransport`` protocol
(``huf/ai/decision/backends/jev.py``): ``(payload: Mapping) -> (status: int, body: Mapping)``.
Which transport a deployment gets depends on its ``wire_protocol`` field (PLAN.md §4.4); the
semantic adapter (Jev/System One, Structured LLM, ...) is a separate, family-level concern
(PLAN.md D3) and is not decided here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

#: The transport callable contract every wire protocol builder must satisfy, matching
#: ``huf.ai.decision.backends.jev.JevTransport``.
Transport = Callable[[Mapping[str, Any]], "tuple[int, Mapping[str, Any]]"]

WIRE_PROTOCOL_SYSTEMONE = "systemone"
WIRE_PROTOCOL_OPENAI_CHAT_JSON = "openai_chat_json"


def build_transport(deployment_doc, *, timeout: float) -> Transport:
	"""Build the provider transport for a Decision Deployment, dispatched on ``wire_protocol``.

	Args:
		deployment_doc: A ``Decision Deployment`` document (or duck-typed equivalent) with at
			least ``wire_protocol``, ``provider`` (AI Provider name), ``provider_model_id``,
			``endpoint_path``, ``latency_budget_ms`` and ``provider_metadata_json``.
		timeout: Caller's remaining budget in seconds (e.g. from the enforce deadline). The
			systemone transport narrows this further against the deployment's
			``latency_budget_ms`` and the provider's ``timeout_seconds``.

	Returns:
		A ``Transport`` callable: ``(payload) -> (status_code, response_body)``. Never logs or
		returns the provider API key.

	Raises:
		ValueError: unknown/missing ``wire_protocol``, or a systemone deployment that cannot be
			resolved to a usable base URL or API key (caller should treat this the same as a
			build-time deployment failure — skip it, per PLAN.md §3.19 "No key on provider").
		NotImplementedError: ``wire_protocol == "openai_chat_json"`` — no transport exists yet
			(PR 11 was cancelled; vendors do not expose Jev over an OpenAI-style chat wire).
	"""
	wire_protocol = getattr(deployment_doc, "wire_protocol", None)

	if wire_protocol == WIRE_PROTOCOL_SYSTEMONE:
		from huf.ai.decision.transports import systemone_http

		return systemone_http.build_transport(deployment_doc, timeout=timeout)

	if wire_protocol == WIRE_PROTOCOL_OPENAI_CHAT_JSON:
		raise NotImplementedError(
			"wire_protocol 'openai_chat_json' has no transport (PR 11 was cancelled: no vendor "
			"exposes Jev/System One over an OpenAI-style chat wire). Use wire_protocol "
			"'systemone', or configure a provider/deployment that speaks it."
		)

	raise ValueError(f"Unknown Decision Deployment wire_protocol: {wire_protocol!r}")
