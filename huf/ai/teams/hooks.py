"""Teams provider hooks, registered under the Gateway provider name ``Microsoft Teams``.

Only ``ingest_update`` is registered: it is the one hook whose ``None`` return means "carry on". Call
sites for most other hooks treat a registered hook's return value as authoritative (``reply_target``
must be a tuple, ``media_save`` a list, ...), so a blanket no-op registration would break the generic
defaults. Later work packages register additional hooks here as they implement them.
"""

from __future__ import annotations

import logging
from typing import Any

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.teams import activity as activity_mod
from huf.ai.teams import refs

PROVIDER = "Microsoft Teams"
logger = logging.getLogger("huf.teams.hooks")


def _ignored(kind: str) -> dict[str, Any]:
	return {"success": True, "ignored": kind}


def _save_reference(gateway, credentials, activity: dict[str, Any]) -> bool:
	"""Persist the conversation reference; False when the serviceUrl is rejected (nothing stored)."""
	reference = refs.reference_from_activity(activity)
	# Channel threads share one reference, keyed by the base channel id (no ``;messageid=`` anchor).
	reference["conversation_id"] = reference["conversation_id"].partition(";messageid=")[0]
	try:
		refs.save_reference(
			str(getattr(gateway, "name", "") or ""),
			str(credentials.get("app_id") or ""),
			reference["conversation_id"],
			reference,
		)
	except ValueError:
		logger.warning("Teams activity dropped: unacceptable serviceUrl or conversation id")
		return False
	except Exception:
		# A cache outage must not drop the user's message; the reference is rebuilt from events later.
		logger.exception("Teams conversation reference could not be stored")
	return True


def ingest_update(gateway, adapter, request) -> Any:
	"""Called as ``(gateway, adapter, request)`` by gateway_webhook AFTER ``verify_inbound`` succeeded
	(the provider_hooks docstring lists another order). A non-None return becomes the HTTP response and
	skips normalize/ingest; ``None`` continues to ``normalize_inbound``.
	"""
	credentials = adapter._credentials()
	try:
		activity = activity_mod.load_activity(request)
	except ValueError:
		logger.warning("Teams activity ignored: invalid payload")
		return _ignored("invalid")

	if str(activity.get("type") or "").lower() == "message":
		outcome = activity_mod.build_event(activity, credentials)
		if isinstance(outcome, str):
			logger.info("Teams message ignored: %s", outcome)
			if outcome == "empty" and not _save_reference(gateway, credentials, activity):
				return _ignored("service_url")
			return _ignored(outcome)
		if not _save_reference(gateway, credentials, activity):
			return _ignored("service_url")
		return None

	kind = activity_mod.ignore_kind(activity)
	if activity_mod.bot_added(activity):
		if not activity_mod.tenant_allowed(activity, credentials):
			logger.info("Teams %s ignored: tenant not allowed", kind)
			return _ignored("tenant")
		if not _save_reference(gateway, credentials, activity):
			return _ignored("service_url")
	return _ignored(kind)


provider_hooks.register(PROVIDER, "ingest_update", ingest_update)
