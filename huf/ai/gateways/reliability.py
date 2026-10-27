"""Gateway reliability hooks: failure/rejection notices and the Slack ack reaction.

Handlers are registered at import time (listed in ``_registered.MODULES`` by the
coordinator). Nothing here may ever raise into, or alter, a run.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import frappe

from huf.ai.gateways import hooks

NOTICE_TTL_SEC = 24 * 3600
ACK_REACTION = "hourglass_flowing_sand"
_TS_RE = re.compile(r"^\d+\.\d+$")

FAILURE_TEXT = "Sorry, something went wrong while handling your message. Reference: {ref}"
UNROUTED_TEXT = "I'm not set up to handle this here. Reference: {ref}"


def _claim(kind: str, event_name: str) -> bool:
	"""Return True the first time (kind, event) is seen; marks it in the cache. Fails closed."""
	try:
		key = f"huf:gw_notice:{kind}:{event_name}"
		cache = frappe.cache()
		if cache.get_value(key):
			return False
		cache.set_value(key, 1, expires_in_sec=NOTICE_TTL_SEC)
		return True
	except Exception:
		return False


def _send_notice(gateway, event, text: str) -> None:
	from huf.ai.gateway_webhook import send_gateway_reply

	target = SimpleNamespace(
		conversation_id=getattr(event, "conversation_id", None),
		thread_id=getattr(event, "thread_id", None),
	)
	if not target.conversation_id:
		return
	send_gateway_reply(gateway, target, text)


def _notify(kind: str, gateway, event, text: str) -> None:
	try:
		name = str(getattr(event, "name", "") or "")
		if not name or not _claim(kind, name):
			return
		_send_notice(gateway, event, text)
	except Exception:
		pass


def on_run_failure(gateway, event, kind, error) -> None:
	# ``error`` is deliberately ignored: no internal error text reaches the user.
	_notify("failure", gateway, event, FAILURE_TEXT.format(ref=getattr(event, "name", "")))


def on_event_rejected(gateway, event, status, reason) -> None:
	reason = str(reason or "")
	if reason.startswith(hooks.USER_VISIBLE_PREFIX):
		text = reason[len(hooks.USER_VISIBLE_PREFIX):].strip()
		if text:
			_notify("rejected", gateway, event, text)
	elif status == "Unrouted":
		_notify("rejected", gateway, event, UNROUTED_TEXT.format(ref=getattr(event, "name", "")))


# ---- Slack ack reaction -------------------------------------------------
def parse_slack_message_ref(provider_event_id) -> tuple[str, str] | None:
	channel, sep, ts = str(provider_event_id or "").partition(":")
	if not sep or not channel or not _TS_RE.match(ts):
		return None
	return channel, ts


def _react(gateway, event, add: bool) -> None:
	try:
		ref = parse_slack_message_ref(getattr(event, "provider_event_id", None))
		if not ref:
			return
		from huf.ai.gateways.slack_context import get_slack_api

		api = get_slack_api(gateway)
		(api.add_reaction if add else api.remove_reaction)(ref[0], ref[1], ACK_REACTION)
	except Exception:
		pass


def slack_on_run_start(gateway, event, kind) -> None:
	_react(gateway, event, True)


def slack_on_run_end(gateway, event, kind, *_rest) -> None:
	_react(gateway, event, False)


hooks.register(hooks.ON_RUN_FAILURE, on_run_failure, priority=200)
hooks.register(hooks.ON_EVENT_REJECTED, on_event_rejected, priority=200)
hooks.register(hooks.ON_RUN_START, slack_on_run_start, provider="slack")
hooks.register(hooks.ON_RUN_SUCCESS, slack_on_run_end, provider="slack")
hooks.register(hooks.ON_RUN_FAILURE, slack_on_run_end, provider="slack", priority=50)
