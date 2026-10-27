"""Slack help command and optional thumbs up/down feedback.

Help: a ``pre_ingest_filter`` answers "help" style messages straight away (no agent run)
with a summary built from the gateway's own configuration. It works before an account is
linked and never creates tokens or shows internal ids.

Feedback: when ``Gateway.show_feedback_buttons`` is on, an ``on_run_success`` handler posts
a small "Was this helpful?" follow-up with two buttons. The click writes an
``Agent Run Feedback`` record as the clicker's mapped user, only if they asked the question.
Nothing here ever raises into the gateway pipeline.
"""

from __future__ import annotations

import re

import frappe

from huf.ai.gateways.slack import blocks as bk
from huf.ai.gateways import hooks as gw_hooks
from huf.ai.gateways import slack_interactivity as ia

FEEDBACK_KIND = "feedback:"
HELP_PHRASES = {"help", "/help", "what can you do"}
MAX_TARGETS = 8
DESCRIPTION_LIMIT = 160
DEDUPE_SECONDS = 10
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(\|[^>]*)?>")
_TRAILING_RE = re.compile(r"[\s?!.]+$")

MSG_THANKS = "Thanks for the feedback"
MSG_NOT_ASKER = "Only the person who asked can rate this answer."
MSG_SAVE_FAILED = "Sorry, I could not save your feedback."


def _log(title: str) -> None:
	try:
		frappe.log_error(frappe.get_traceback(), title[:140])
	except Exception:
		pass


# --------------------------------------------------------------------------- help
def is_help_text(text) -> bool:
	t = _MENTION_RE.sub(" ", str(text or "")).strip().lower()
	if t == "?":
		return True
	return _TRAILING_RE.sub("", t).strip() in HELP_PHRASES


def _short(text) -> str:
	text = " ".join(str(text or "").split())
	return text if len(text) <= DESCRIPTION_LIMIT else text[: DESCRIPTION_LIMIT - 1].rstrip() + "…"


def _linked_user(gateway, sender: str):
	if not sender:
		return None
	try:
		return frappe.db.get_value(
			"Gateway Identity Link",
			{"gateway": gateway.name, "external_id": sender, "state": "Linked"},
			"user",
		)
	except Exception:
		return None


def _can_see(doctype: str, name: str, user) -> bool:
	if not user:
		return True  # not linked yet: the gateway's own targets are all that can be offered
	try:
		return bool(frappe.has_permission(doctype, "read", name, user=user))
	except Exception:
		return False


def _describe(target_type, agent, flow, binding_description, user):
	"""Return ``(name, description)`` for a visible, enabled target, else None."""
	if target_type == "Agent" and agent:
		row = frappe.db.get_value("Agent", agent, ["agent_name", "disabled", "description"], as_dict=True)
		if not row or row.get("disabled") or not _can_see("Agent", agent, user):
			return None
		return str(row.get("agent_name") or agent), binding_description or row.get("description")
	if target_type == "Flow" and flow:
		row = frappe.db.get_value("Flow Definition", flow, ["flow_name", "status"], as_dict=True)
		if not row or str(row.get("status") or "").lower() in ("disabled", "archived", "inactive"):
			return None
		if not _can_see("Flow Definition", flow, user):
			return None
		return str(row.get("flow_name") or flow), binding_description
	return None


def reachable_targets(gateway, user=None) -> list[tuple[str, str]]:
	"""Distinct ``(name, description)`` the gateway can route to: bindings by priority, then default."""
	found: list[tuple[str, str]] = []
	seen: set[str] = set()

	def add(target_type, agent, flow, desc):
		item = _describe(target_type, agent, flow, desc, user)
		if item and item[0] not in seen:
			seen.add(item[0])
			found.append((item[0], _short(item[1])))

	bindings = frappe.get_all(
		"Gateway Binding",
		filters={"gateway": gateway.name, "is_enabled": 1},
		fields=["target_type", "agent", "flow", "description"],
		order_by="priority asc, creation asc",
	)
	for b in bindings or []:
		add(b.get("target_type"), b.get("agent"), b.get("flow"), b.get("description"))
	add(getattr(gateway, "default_target_type", None), getattr(gateway, "default_agent", None),
		getattr(gateway, "default_flow", None), None)
	return found


def build_help(gateway, user=None) -> bk.Rendered:
	targets = reachable_targets(gateway, user)
	lines = ["*Here is how I can help*"]
	if targets:
		lines.append("You can ask:")
		for name, desc in targets[:MAX_TARGETS]:
			lines.append(f"• *{bk.escape_mrkdwn(name)}*" + (f" - {bk.escape_mrkdwn(desc)}" if desc else ""))
		if len(targets) > MAX_TARGETS:
			lines.append(f"...and {len(targets) - MAX_TARGETS} more.")
	else:
		lines.append("Nothing is set up to answer questions here yet. Please ask an administrator.")
	lines.append("")
	lines.append("*How to ask:* mention me in a channel, or send me a direct message.")
	lines.append("*Your account:* if I ask you to connect your Huf account, send me any message "
		"and open the link in my reply.")
	if getattr(gateway, "show_feedback_buttons", 0):
		lines.append("*Feedback:* after an answer I may ask whether it helped. A quick thumbs up or down "
			"helps us improve.")
	text = "\n".join(lines)
	return bk.Rendered([bk.section_block(text, escape=False)], text.replace("*", ""))


def _duplicate(gateway, context) -> bool:
	"""Slack sends a message and an app_mention for one mention: answer only once."""
	try:
		key = "huf_slack_help:{}:{}:{}:{}".format(
			gateway.name, context.get("conversation_id"), context.get("thread_id"), context.get("sender_id"))
		cache = frappe.cache()
		if cache.get_value(key):
			return True
		cache.set_value(key, 1, expires_in_sec=DEDUPE_SECONDS)
	except Exception:
		pass
	return False


def pre_ingest_filter(gateway, context) -> bool:
	"""Return False (drop) after answering a help message; True lets everything else pass."""
	try:
		if not isinstance(context, dict) or not getattr(gateway, "is_enabled", 1):
			return True
		if not is_help_text(context.get("message_text")):
			return True
		if context.get("is_room") and not context.get("mentioned"):
			return True  # chatter in a channel that was not addressed to us
		channel = str(context.get("conversation_id") or "")
		if not channel:
			return True
		from huf.ai.gateways.slack.context import get_slack_api

		try:
			api = get_slack_api(gateway)
		except Exception:
			return True  # no way to answer; let the normal pipeline decide
		if _duplicate(gateway, context):
			return False
		rendered = build_help(gateway, _linked_user(gateway, str(context.get("sender_id") or "")))
		thread = str(context.get("thread_id") or "") or None
		try:
			api.post_message(channel, text=rendered.fallback, blocks=rendered.blocks, thread_ts=thread)
		except Exception:
			_log("Slack help reply failed")
		return False
	except Exception:
		_log("Slack help filter failed")
		return True


# --------------------------------------------------------------------------- feedback
def on_run_success(gateway, event, kind, response) -> None:
	"""Post the thumbs prompt in the asker's thread. Never raises."""
	try:
		if kind != "agent" or not getattr(gateway, "show_feedback_buttons", 0):
			return
		run = getattr(event, "agent_run", None)
		channel = str(getattr(event, "conversation_id", "") or "")
		sender = str(getattr(event, "sender_id", "") or "")
		if not run or not channel or not sender:
			return
		from huf.ai.gateways.slack.context import get_slack_api

		api = get_slack_api(gateway)
		session = ia.create_action_session(
			gateway, FEEDBACK_KIND, {"agent_run": run, "gateway_event": event.name},
			intended_slack_user=sender, channel=channel,
		)
		blocks = [
			bk.section_block("Was this helpful?", escape=False),
			bk.actions_block(
				bk.button("\U0001F44D", session, choice="up"),
				bk.button("\U0001F44E", session, choice="down"),
			),
		]
		thread = str(getattr(event, "thread_id", "") or "") or None
		resp = api.post_message(channel, text="Was this helpful?", blocks=blocks, thread_ts=thread)
		ts = resp.get("ts") if isinstance(resp, dict) else None
		if ts:
			frappe.db.set_value("Gateway Action Session", session, "message_ts", ts, update_modified=False)
	except Exception:
		_log("Slack feedback prompt failed")


def _message_for_run(run: str):
	try:
		return frappe.db.get_value(
			"Agent Message", {"agent_run": run, "role": "agent"}, "name", order_by="creation desc")
	except Exception:
		return None


def handle_feedback(gateway, session, actor_user, payload) -> dict:
	"""Action handler for ``feedback:`` sessions. Returns the status text; never raises."""
	try:
		data = (session or {}).get("payload") or {}
		run = str(data.get("agent_run") or "")
		event_name = str(data.get("gateway_event") or "")
		choice = (session or {}).get("choice")
		if choice not in ("up", "down") or not run:
			return {"text": ia.MSG_UNKNOWN}
		clicker = str(((payload or {}).get("user") or {}).get("id") or "")
		asker = frappe.db.get_value("Gateway Event", event_name, "sender_id") if event_name else None
		if not asker or clicker != str(asker):
			return {"text": MSG_NOT_ASKER}
		agent = frappe.db.get_value("Agent Run", run, "agent")
		values = {
			"doctype": "Agent Run Feedback",
			"feedback": "Thumbs Up" if choice == "up" else "Thumbs Down",
			"agent": agent,
			"agent_message": _message_for_run(run),
		}
		previous = frappe.session.user
		try:
			frappe.set_user(actor_user)
			frappe.get_doc(values).insert()
		finally:
			frappe.set_user(previous)
		return {"text": MSG_THANKS, "blocks": bk.status_line(MSG_THANKS, icon="✅").blocks}
	except Exception:
		_log("Slack feedback save failed")
		return {"text": MSG_SAVE_FAILED}


REACTION_UP = {"+1", "thumbsup", "thumbsup_all"}
REACTION_DOWN = {"-1", "thumbsdown"}


def _reaction_choice(name: str):
	base = str(name or "").split("::", 1)[0]  # skin-tone variants look like "+1::skin-tone-3"
	if base in REACTION_UP:
		return "up"
	if base in REACTION_DOWN:
		return "down"
	return None


def handle_reaction(gateway, payload) -> bool:
	"""A 👍/👎 reaction on one of the bot's answers counts as feedback from a linked asker.

	Slack gives only the message timestamp, so the answer is matched to the asker's most recent
	finished run in that conversation. Never raises; returns True when feedback was saved.
	"""
	try:
		event = (payload or {}).get("event") or {}
		choice = _reaction_choice(event.get("reaction"))
		item = event.get("item") or {}
		reactor = str(event.get("user") or "")
		channel = str(item.get("channel") or "")
		bot = str((((payload or {}).get("authorizations") or [{}])[0] or {}).get("user_id") or "")
		if not choice or item.get("type") != "message" or not reactor or not channel:
			return False
		if bot and str(event.get("item_user") or "") != bot:
			return False  # only reactions on the bot's own messages
		team = str((payload or {}).get("team_id") or "")
		link = frappe.get_all("Gateway Identity Link", filters={"gateway": gateway.name, "team_id": team,
			"external_id": reactor, "state": "Linked"}, fields=["user"], limit_page_length=1)
		if not link:
			return False
		key = f"huf:gw_reaction:{gateway.name}:{reactor}:{item.get('ts')}"
		if frappe.cache().get_value(key):
			return False
		runs = frappe.get_all("Gateway Event", filters={"gateway": gateway.name, "conversation_id": channel,
			"sender_id": reactor, "status": "Succeeded", "agent_run": ["is", "set"]},
			fields=["agent_run"], order_by="creation desc", limit_page_length=1)
		if not runs:
			return False
		run = runs[0]["agent_run"]
		values = {"doctype": "Agent Run Feedback", "feedback": "Thumbs Up" if choice == "up" else "Thumbs Down",
			"agent": frappe.db.get_value("Agent Run", run, "agent"), "agent_message": _message_for_run(run)}
		previous = frappe.session.user
		try:
			frappe.set_user(link[0]["user"])
			frappe.get_doc(values).insert()
		finally:
			frappe.set_user(previous)
		frappe.cache().set_value(key, 1, expires_in_sec=24 * 3600)
		try:
			from huf.ai.gateways.slack.context import get_slack_api

			get_slack_api(gateway).post_ephemeral(channel, reactor, text=MSG_THANKS)
		except Exception:
			pass
		return True
	except Exception:
		_log("Slack reaction feedback failed")
		return False


gw_hooks.register(gw_hooks.PRE_INGEST_FILTER, pre_ingest_filter, provider="slack", priority=50)
gw_hooks.register(gw_hooks.ON_RUN_SUCCESS, on_run_success, provider="slack")
ia.register_action_handler(FEEDBACK_KIND, handle_feedback)
