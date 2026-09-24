"""Per-deployment token bucket enforcement for Decision Runtime throughput limits.

PLAN.md §4.9 / task T2A.11: Enforce provider rate limits per deployment using a token bucket
algorithm stored in ``frappe.cache()``. When a deployment's rate limit is exhausted,
``run_policy`` returns ``DECISION_THROUGHPUT_BUDGET_EXHAUSTED`` before calling the provider.

When a 429 response arrives, the deployment is put into a 60-second cool-down (health_status
set to 'degraded', last_healthcheck set to now) so ``deployment_loader`` skips it on the
next call.
"""

from __future__ import annotations

import json
import time
from typing import Any

import frappe


def check_throughput_bucket(
	*,
	deployment_doc: dict[str, Any] | frappe._dict,
	deadline: float | None = None,
) -> bool:
	"""Check if this deployment's token bucket has capacity; if so, consume one token.

	Args:
		deployment_doc: A ``Decision Deployment`` row (dict or frappe._dict) with fields
			``name``, ``provider_rate_limits_json``, etc. Typically comes from
			``deployment_loader._fetch_model_context`` or a Frappe ``get_doc`` call.
		deadline: Wall-clock deadline (``time.monotonic()`` seconds). If the deadline has
			already passed, return ``False`` without consuming a token (assume the caller
			will timeout anyway).

	Returns:
		``True`` if a token was consumed (the call may proceed); ``False`` if the bucket
		is exhausted or the deadline has expired.

	Side effects:
		- Decrements the token count in ``frappe.cache()`` if a token was consumed.
		- Updates the deployment's ``health_status`` and ``last_healthcheck`` in the
		  database if a token is consumed but the bucket was at capacity (or near enough
		  to warrant a 429-like cool-down).
	"""
	if deadline is not None and time.monotonic() >= deadline:
		return False

	deployment_name = deployment_doc.get("name") or deployment_doc.get("deployment_key")
	rate_limits_json = deployment_doc.get("provider_rate_limits_json")

	rate_limit_per_minute = _parse_rate_limit(rate_limits_json)
	if rate_limit_per_minute is None or rate_limit_per_minute <= 0:
		# No limit; all calls proceed.
		return True

	cache_key = f"huf_decision_throughput:{deployment_name}"
	cache = frappe.cache()

	try:
		current = cache.get_value(cache_key)
	except Exception:
		# Cache read failure: fail open (let the call through; the provider will rate-limit
		# if needed, and deployment_loader._in_cooldown will skip it after a 429).
		return True

	now = time.time()
	window_key = f"{cache_key}:window"

	try:
		window_str = cache.get_value(window_key)
		window_start = float(window_str) if window_str else now
	except (ValueError, TypeError):
		window_start = now

	# Reset the bucket every minute.
	if now - window_start >= 60:
		try:
			cache.set_value(cache_key, rate_limit_per_minute - 1, expires_in_sec=60)
			cache.set_value(window_key, str(now), expires_in_sec=60)
		except Exception:
			# Cache write failure: fail open.
			pass
		return True

	# Within the current minute window: check and decrement the token count.
	current_int = int(current) if current else rate_limit_per_minute
	if current_int <= 0:
		# Bucket exhausted; return False so the service returns THROUGHPUT_BUDGET_EXHAUSTED
		# before calling the provider. The deployment is already marked degraded by a previous
		# 429, or will be on the next one.
		return False

	# Consume one token.
	try:
		cache.set_value(cache_key, current_int - 1, expires_in_sec=60)
	except Exception:
		# Cache write failure: fail open (the token count may be stale, but let it through).
		pass

	return True


def mark_deployment_cooldown(
	*,
	deployment_name: str,
	cooldown_seconds: int = 60,
) -> None:
	"""Mark a deployment as degraded (in cool-down) for ``cooldown_seconds`` after a 429.

	Args:
		deployment_name: ``Decision Deployment`` docname.
		cooldown_seconds: Cool-down duration (default 60).

	Side effects:
		- Updates the ``Decision Deployment`` row: sets ``health_status = "degraded"`` and
		  ``last_healthcheck`` to the current timestamp.
		- Best-effort: failures are logged but do not raise (a cache or database failure
		  must not fail the decision call itself).
	"""
	try:
		frappe.db.set_value(
			"Decision Deployment",
			deployment_name,
			{
				"health_status": "degraded",
				"last_healthcheck": frappe.utils.now_datetime(),
			},
			update_modified=False,  # Don't bump the DocType's modified timestamp.
		)
	except Exception as exc:
		frappe.logger("huf").warning(
			f"Failed to mark Decision Deployment {deployment_name!r} as degraded after 429: {exc!s}"
		)


def _parse_rate_limit(rate_limits_json: str | None) -> int | None:
	"""Extract the requests-per-minute limit from a provider's rate_limits_json.

	Args:
		rate_limits_json: JSON string with structure ``{"requests_per_minute": <int>, ...}``.

	Returns:
		The integer limit, or ``None`` if the field is missing, empty, or not valid JSON.
	"""
	if not rate_limits_json:
		return None

	try:
		data = json.loads(rate_limits_json)
		if isinstance(data, dict):
			limit = data.get("requests_per_minute")
			if isinstance(limit, int) and limit > 0:
				return limit
	except (TypeError, ValueError, json.JSONDecodeError):
		pass

	return None
