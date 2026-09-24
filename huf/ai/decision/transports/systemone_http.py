"""HTTP transport for the ``systemone`` wire protocol.

Builds a ``JevTransport``-shaped callable (``huf/ai/decision/backends/jev.py``) for a
``Decision Deployment`` whose ``wire_protocol`` is ``"systemone"`` (OpenCode Zen / Jev System
One and any other provider that speaks the same ``/v1/systemone``-style wire). This is the
production replacement for ``jev.py``'s dev-only ``opencode_zen_transport_from_env`` — same
request shape and return contract, driven by the ``Decision Deployment`` / ``AI Provider``
records instead of an environment variable (PLAN.md §4.4).
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import frappe

from huf.ai.decision import catalog
from huf.ai.provider_security import validate_api_base_url

#: Protocol default endpoint path when neither the deployment nor the catalog entry sets one
#: (matches jev.py's current hardcoded constant, PLAN.md §4.4).
_DEFAULT_ENDPOINT_PATH = "/v1/systemone"

#: Used only when neither the caller's timeout budget nor the provider's timeout_seconds
#: resolves to a usable (positive) value.
_FALLBACK_TIMEOUT_SECONDS = 30.0

_DEFAULT_MAX_RETRIES = 2
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 8.0

_USER_AGENT = "HUF-Decision-Runtime/1.0"


def build_transport(deployment_doc, *, timeout: float, deadline: float | None = None, opener=None):
	"""Build a systemone-wire HTTP transport for one Decision Deployment.

	Args:
		deployment_doc: A ``Decision Deployment`` document (or duck-typed equivalent) with
			``provider`` (AI Provider name, fetched from ``ai_model.provider``),
			``provider_model_id`` (fetched from ``ai_model.model_name``), ``endpoint_path``,
			``latency_budget_ms`` and ``provider_metadata_json``.
		timeout: Caller's remaining budget in seconds (e.g. the enforce deadline). The request
			timeout actually used is ``min(timeout, latency_budget_ms/1000, provider.timeout_seconds)``
			over whichever of those are set (PLAN.md §4.4).
		deadline: Monotonic timestamp (``time.monotonic()`` seconds) representing an absolute
			deadline. When set, the transport will not start retries that would end after the
			deadline, and each attempt's socket timeout is clipped to the remaining time.
			``None`` (default) means no deadline constraint; retries proceed normally.
		opener: Test seam — replaces ``urllib.request.urlopen``. Signature
			``opener(request, timeout) -> response`` (context-manager with ``.status``/``.read()``).

	Returns:
		A transport callable ``(payload) -> (status_code, response_body)`` matching
		``huf.ai.decision.backends.jev.JevTransport``. Never logs or returns the API key.

	Raises:
		ValueError: no resolvable base URL (neither ``AI Provider.api_base_url`` nor a catalog
			default for the provider's brand), or no API key configured on the provider.
		frappe.ValidationError: the resolved URL fails ``validate_api_base_url`` (SSRF-style
			checks; private hosts are only allowed when ``AI Provider.is_local_llm`` is set).
	"""
	provider_doc = frappe.get_doc("AI Provider", deployment_doc.provider)

	full_url = _resolve_url(provider_doc, deployment_doc)
	validate_api_base_url(full_url, allow_private=bool(getattr(provider_doc, "is_local_llm", False)))

	api_key = provider_doc.get_password("api_key", raise_exception=False)
	if not api_key:
		raise ValueError(f"AI Provider {provider_doc.name!r} has no API key configured")

	effective_timeout = _resolve_timeout(provider_doc, deployment_doc, timeout)
	max_retries = _resolve_max_retries(deployment_doc)
	request_opener = opener or urlopen

	def transport(payload: Mapping[str, Any]) -> "tuple[int, Mapping[str, Any]]":
		attempt = 0
		while True:
			# Calculate remaining time budget for this attempt
			remaining_time = _remaining_time(deadline, effective_timeout)
			attempt_timeout = remaining_time if deadline is not None else effective_timeout

			request = Request(
				full_url,
				data=json.dumps(payload).encode("utf-8"),
				headers={
					"Authorization": f"Bearer {api_key}",
					"Content-Type": "application/json",
					"User-Agent": _USER_AGENT,
				},
				method="POST",
			)
			try:
				with request_opener(request, timeout=attempt_timeout) as response:
					status = int(response.status)
					raw_body = response.read()
			except HTTPError as exc:
				status = int(exc.code)
				if status >= 500 and attempt < max_retries:
					backoff = _backoff_delay(attempt + 1)
					# Only proceed with retry if there's time remaining (including the backoff)
					if deadline is None or _remaining_time(deadline) > backoff:
						attempt += 1
						time.sleep(backoff)
						continue
				# 4xx (including 429), exhausted 5xx retries, or no time for backoff: return as-is
				# 429 backoff/cool-down is the deployment loader's job (PLAN.md §3.19), not this transport's.
				return status, {}
			except TimeoutError as exc:
				raise TimeoutError("systemone transport timed out") from exc
			except URLError as exc:
				if isinstance(exc.reason, TimeoutError):
					raise TimeoutError("systemone transport timed out") from exc
				raise ConnectionError("systemone transport unavailable") from exc

			return status, _decode_body(raw_body)

	return transport


def _resolve_url(provider_doc, deployment_doc) -> str:
	entry = catalog.get_entry(
		getattr(provider_doc, "provider_brand", None),
		getattr(deployment_doc, "provider_model_id", None),
	)
	base_url = (
		getattr(provider_doc, "api_base_url", None)
		or (entry.base_url if entry else None)
		or catalog.brand_default_base_url(getattr(provider_doc, "provider_brand", None))
	)
	if not base_url:
		raise ValueError(
			f"AI Provider {getattr(provider_doc, 'name', '?')!r} has no API Base URL and no "
			f"catalog default for brand {getattr(provider_doc, 'provider_brand', None)!r}"
		)
	endpoint_path = getattr(deployment_doc, "endpoint_path", None) or (
		entry.endpoint_path if entry else _DEFAULT_ENDPOINT_PATH
	)
	if not endpoint_path.startswith("/"):
		endpoint_path = f"/{endpoint_path}"
	return f"{base_url.rstrip('/')}{endpoint_path}"


def _resolve_timeout(provider_doc, deployment_doc, timeout: float) -> float:
	candidates = [timeout]
	latency_budget_ms = getattr(deployment_doc, "latency_budget_ms", None)
	if latency_budget_ms:
		candidates.append(latency_budget_ms / 1000.0)
	provider_timeout = getattr(provider_doc, "timeout_seconds", None)
	if provider_timeout:
		candidates.append(provider_timeout)
	positive = [value for value in candidates if value and value > 0]
	if not positive:
		return _FALLBACK_TIMEOUT_SECONDS
	return min(positive)


def _remaining_time(deadline: float | None, fallback: float | None = None) -> float:
	"""Calculate remaining time from a deadline (``time.monotonic()`` seconds).

	Args:
		deadline: Monotonic timestamp representing an absolute deadline, or ``None``.
		fallback: Value to return if ``deadline`` is ``None`` (default: ``None``).

	Returns:
		Remaining seconds until the deadline, or ``fallback`` if deadline is ``None``.
		Never returns a negative value; clamps to 0 if the deadline has passed.
	"""
	if deadline is None:
		return fallback if fallback is not None else float('inf')
	remaining = deadline - time.monotonic()
	return max(0.0, remaining)


def _resolve_max_retries(deployment_doc) -> int:
	metadata_raw = getattr(deployment_doc, "provider_metadata_json", None)
	if not metadata_raw:
		return _DEFAULT_MAX_RETRIES
	try:
		metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
	except (TypeError, ValueError):
		return _DEFAULT_MAX_RETRIES
	if not isinstance(metadata, Mapping):
		return _DEFAULT_MAX_RETRIES
	max_retries = metadata.get("max_retries")
	if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
		return _DEFAULT_MAX_RETRIES
	return max_retries


def _backoff_delay(attempt: int) -> float:
	return min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)


def _decode_body(raw_body: bytes) -> Mapping[str, Any]:
	try:
		body = json.loads(raw_body.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return {}
	return body if isinstance(body, Mapping) else {}
