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
ROOM_NOT_APPROVED_REASON = "Room or sender is not approved for this gateway"
ROOM_NOT_APPROVED_TEXT = (
	"I'm not enabled in this channel yet. Ask a Huf admin to approve this channel (and you) for this gateway."
)
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


def _notice_thread(channel, thread_ts, message_ts=None):
	"""A top-level message's own ts is its "thread": an ephemeral posted there is hidden in a thread view.

	Direct messages (channel ids starting with D) and replies to a top-level message get the notice at
	top level instead; only a notice for a message inside a real thread stays in that thread.
	"""
	if str(channel or "").startswith("D"):
		return None
	if thread_ts and message_ts and str(thread_ts) == str(message_ts):
		return None
	return thread_ts or None


def _event_message_ts(event):
	ref = parse_slack_message_ref(getattr(event, "provider_event_id", None))
	return ref[1] if ref else None


def _send_private_slack(gateway, event, text: str) -> None:
	"""Slack notices go only to the sender: ephemeral in the same channel/thread, else a DM.

	If neither works nothing is sent: a notice (it may carry a one-time link) must never land
	in the channel or thread where others can read it.
	"""
	sender = str(getattr(event, "sender_id", "") or "")
	channel = getattr(event, "conversation_id", None)
	if not sender:
		return
	from huf.ai.gateways.slack.context import get_slack_api

	api = get_slack_api(gateway)
	if channel:
		try:
			api.post_ephemeral(
				channel, sender, text=text,
				thread_ts=_notice_thread(channel, getattr(event, "thread_id", None), _event_message_ts(event)),
			)
			return
		except Exception:
			pass
	try:
		dm = api.conversations_open([sender])
		if dm:
			api.post_message(dm, text=text)
	except Exception:
		pass


def _send_notice(gateway, event, text: str) -> None:
	if str(getattr(gateway, "provider", "") or "").lower() == "slack":
		_send_private_slack(gateway, event, text)
		return
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
	elif (
		status == "Rejected"
		and reason == ROOM_NOT_APPROVED_REASON
		and str(getattr(gateway, "provider", "") or "").lower() == "slack"
		and str(getattr(event, "conversation_id", "") or "")[:1] in ("C", "G")
	):
		# Once per channel per day, privately to the sender, so a first @mention is not met with silence.
		_notify("room_unapproved", gateway, SimpleNamespace(name=str(event.conversation_id), sender_id=event.sender_id,
			conversation_id=event.conversation_id, thread_id=getattr(event, "thread_id", None),
			provider_event_id=getattr(event, "provider_event_id", None)), ROOM_NOT_APPROVED_TEXT)
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
		from huf.ai.gateways.slack.context import get_slack_api

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
